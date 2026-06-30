"""Instrument agent — composes one part.

Phase 4: a single pass, no negotiation. Phase 5 adds `run_instrument_turn`, used
in each negotiation round to revise a part, resolve pending requests addressed to
this instrument, and optionally raise new ones.

Constrained by the immutable header, this instrument's role/range, and peers'
compact `notes_summary` strings, never their full note lists (token cost). Reuses
`Note` directly as the structured-output schema so there is one schema for the
LLM contract and the canonical SongState (avoid schema drift).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..config import get_settings
from ..infrastructure.llm import LLMError
from ..music.theory import beats_per_bar
from ..music.validators import ValidationIssue, errors_only, validate_song
from ..domain.song_state import Header, NegotiationRequest, Note, Part, RosterItem, SongState
from ..skills._tables import DRUM_PATTERNS, DRUM_PATTERN_ALIASES
from ..skills.edits import EditFailure, NoteEdit, apply_edits
from ..skills.rhythm import drum_pattern

MAX_REPAIRS = 2
STRUCTURED_OUTPUT_RETRIES = 1


class InstrumentOutput(BaseModel):
    notes: list[Note] = Field(description="this instrument's notes for the whole song")
    notes_summary: str = Field(
        description="1-2 sentence compact summary peers can read instead of the full note list"
    )
    self_notes: str = Field(default="", description="optional notes to self for later revision")


def _peer_context(roster: list[RosterItem], self_id: str, peer_summaries: dict[str, str]) -> str:
    lines = [
        f"- {r.id} ({r.instrument}, {r.role}): {peer_summaries.get(r.id, 'not composed yet')}"
        for r in roster
        if r.id != self_id
    ]
    return "\n".join(lines) or "(no other instruments)"


def _system_prompt(header: Header, roster_item: RosterItem) -> str:
    bpb = beats_per_bar(header.time_signature)
    drum_note = (
        " (percussion kit — pitch is a GM drum key, not a melodic pitch; range/key checks don't apply)"
        if roster_item.is_drum
        else ""
    )
    return (
        f"You are the {roster_item.instrument} player ({roster_item.role}) in a "
        f"{header.genre} ensemble. Hard constraints:\n"
        f"- key: {header.key}, tempo: {header.tempo_bpm} BPM, "
        f"time signature {header.time_signature[0]}/{header.time_signature[1]} "
        f"({bpb} beats/bar)\n"
        f"- song length: {header.num_bars} bars (bar indices 0..{header.num_bars - 1})\n"
        f"- your MIDI pitch range: {roster_item.midi_range[0]}-{roster_item.midi_range[1]}{drum_note}\n"
        "Compose your full part for the whole song: a list of notes with absolute bar "
        "+ start_beat (0-indexed within the bar), MIDI pitch (null = rest), duration in "
        "beats, and velocity (0-127). Stay within your range and the bar/beat bounds. "
        "Also return a short notes_summary other musicians can read instead of your full "
        "note list."
    )


def _repair_prompt(issues: list[ValidationIssue]) -> str:
    bullets = "\n".join(f"- {i.message}" for i in issues)
    return (
        "Your part had validation errors — return a complete, corrected part "
        f"(not a diff) that fixes:\n{bullets}"
    )


def _validate_part(header: Header, roster_item: RosterItem, part: Part) -> list[ValidationIssue]:
    temp = SongState(request="", header=header, roster=[roster_item], parts={roster_item.id: part})
    return errors_only(validate_song(temp))


def _to_part(roster_item: RosterItem, out: InstrumentOutput) -> Part:
    return Part(
        instrument_id=roster_item.id,
        notes=out.notes,
        notes_summary=out.notes_summary,
        self_notes=out.self_notes,
    )


def _resolve_drum_style(header: Header, roster_item: RosterItem) -> str:
    """Pick a `drum_pattern` style key from the roster item's role and the header's
    genre. Role wins (so the director can override per-song with "drums — boom_bap");
    otherwise the genre is matched directly, then aliased, then defaulted to
    `rock_basic` — the same fallback `drum_pattern` itself uses.
    """
    haystacks = [roster_item.role.lower(), header.genre.lower()]
    for hay in haystacks:
        for name in DRUM_PATTERNS:
            if name in hay:
                return name
        for alias, target in DRUM_PATTERN_ALIASES.items():
            if alias in hay:
                return target
    return "rock_basic"


def _drum_part(header: Header, roster_item: RosterItem) -> Part:
    """Build a drum part verbatim from `drum_pattern` — no LLM call.

    `notes_summary` names the pattern so peer instruments still get useful context
    in negotiation rounds. `self_notes` records that the part is skill-derived so
    a future revision pass can tell it apart from an LLM-generated part.
    """
    style = _resolve_drum_style(header, roster_item)
    notes = drum_pattern(style, header.time_signature, header.num_bars)
    return Part(
        instrument_id=roster_item.id,
        notes=notes,
        notes_summary=f"{style} pattern, {header.num_bars} bars",
        self_notes=f"skill:drum_pattern[{style}]",
    )


def _fallback_part(roster_item: RosterItem, reason: str = "model did not return structured output") -> Part:
    return Part(
        instrument_id=roster_item.id,
        notes=[],
        notes_summary=f"fallback: {reason}",
        self_notes=reason,
    )


def _invoke_structured(structured, messages, schema_name: str):
    last_error = None
    retries = max(0, get_settings().llm_max_retries)
    for attempt in range(retries + 1):
        try:
            out = structured.invoke(messages)
        except LLMError:
            raise
        except Exception as exc:
            last_error = exc
            out = None
        if out is not None:
            return out
        if attempt < retries:
            messages = messages + [
                (
                    "human",
                    f"Return only a valid {schema_name} object matching the requested structured schema. Do not return prose.",
                )
            ]
    if last_error is not None:
        return None
    return None


def compose_part(
    header: Header,
    roster_item: RosterItem,
    roster: list[RosterItem],
    peer_summaries: dict[str, str],
    llm=None,
) -> Part:
    """Compose one instrument's part, with a bounded repair loop on validation failure.

    Never raises: an issue still unresolved after `MAX_REPAIRS` retries ships as-is —
    `validate_song` on the full song surfaces it in `song.errors` rather than crashing
    the run.

    Drum parts (`roster_item.is_drum`) skip the LLM entirely and ship a deterministic
    `drum_pattern` — generating drum hits note-by-note buys no quality over a curated
    pattern table and costs a full turn per round.
    """
    if roster_item.is_drum:
        return _drum_part(header, roster_item)
    if llm is None:
        from llm_band.infrastructure.gemini.llm import make_llm

        llm = make_llm("instrument")
    structured = llm.with_structured_output(InstrumentOutput)

    messages = [
        ("system", _system_prompt(header, roster_item)),
        ("human", f"Other instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"),
    ]
    out = _invoke_structured(structured, messages, "InstrumentOutput")
    if out is None:
        return _fallback_part(roster_item)
    part = _to_part(roster_item, out)

    for _ in range(MAX_REPAIRS):
        issues = _validate_part(header, roster_item, part)
        if not issues:
            break
        messages = messages + [
            ("ai", f"My part: {out.notes_summary}"),
            ("human", _repair_prompt(issues)),
        ]
        out = _invoke_structured(structured, messages, "InstrumentOutput")
        if out is None:
            return _fallback_part(roster_item)
        part = _to_part(roster_item, out)

    return part


# ---- Phase 5: negotiation turn ---------------------------------------------

class RequestResolution(BaseModel):
    request_id: str = Field(description="id of a pending request addressed to you")
    accepted: bool
    resolution: str = Field(description="short note on what you did (or why you declined)")


class NewRequest(BaseModel):
    to: str = Field(description="roster id of the instrument you're asking")
    bars: list[int] = Field(default_factory=list)
    request: str
    rationale: str


class InstrumentTurnOutput(InstrumentOutput):
    request_resolutions: list[RequestResolution] = Field(default_factory=list)
    new_requests: list[NewRequest] = Field(default_factory=list)


class InstrumentRevisionOutput(BaseModel):
    """Diff-based output used by negotiation rounds (round > 0).

    Avoids re-emitting the full note list every revision — typically a handful of
    edits vs ~100 notes per part. See `apply_edits` for the materialization
    semantics and `_compact_part_text` for what the agent sees as input.
    """

    edits: list[NoteEdit] = Field(
        default_factory=list,
        description="add/replace/remove edits against your current part; each anchors to (bar, start_beat)",
    )
    notes_summary: str = Field(description="updated 1-2 sentence summary peers can read")
    self_notes: str = Field(default="", description="optional notes to self for later revision")
    request_resolutions: list[RequestResolution] = Field(default_factory=list)
    new_requests: list[NewRequest] = Field(default_factory=list)


def _pending_context(pending: list[NegotiationRequest]) -> str:
    if not pending:
        return "(no pending requests addressed to you)"
    lines = [
        f"- [{r.id}] from {r.from_}, bars {r.bars}: {r.request} (why: {r.rationale})"
        for r in pending
    ]
    return "Pending requests addressed to you — accept (and patch your part) or decline each:\n" + "\n".join(lines)


def _compact_part_text(part: Part) -> str:
    """One line per note — the cheapest legible form the agent can address by
    `(bar, start_beat)` when emitting edits. Cheaper as input than re-emitting
    the same notes through structured output."""
    if not part.notes:
        return "(empty part)"
    lines = []
    for n in part.notes:
        pitch = "rest" if n.pitch is None else n.pitch
        lines.append(
            f"bar={n.bar} beat={n.start_beat:g} pitch={pitch} dur={n.dur:g} vel={n.velocity}"
        )
    return "\n".join(lines)


def _edit_failure_prompt(failures: list[EditFailure]) -> str:
    bullets = "\n".join(f"- {f.edit.op} bar={f.edit.bar} beat={f.edit.start_beat:g}: {f.reason}" for f in failures)
    return (
        "Some of your edits could not be applied:\n"
        f"{bullets}\n"
        "Return a corrected list of edits (not a diff of the diff) that achieves "
        "the same musical intent."
    )


def _revision_etiquette() -> str:
    return (
        "\nYou are revising an existing part. Output only the edits needed — "
        "add to insert a new note at (bar, start_beat), replace to overwrite an "
        "existing note at (bar, start_beat), remove to delete it. Leave notes "
        "you want unchanged out of the edits list entirely. Anchor each edit by "
        "the (bar, start_beat) shown in the current part."
    )


def _negotiation_etiquette() -> str:
    return (
        "\nYou may also ask another instrument for a specific accommodation (e.g. "
        "leave space in a bar for a fill, change a note to fit a chord). Phrase each "
        "as: which instrument (by roster id), which bar(s), what you're asking, and why. "
        "Only raise a request if it meaningfully improves the arrangement — don't "
        "manufacture requests for their own sake."
    )


def run_instrument_turn(
    header: Header,
    roster_item: RosterItem,
    roster: list[RosterItem],
    peer_summaries: dict[str, str],
    pending: list[NegotiationRequest],
    existing_part: Optional[Part],
    llm=None,
) -> tuple[Part, list[RequestResolution], list[NewRequest]]:
    """One negotiation-round turn: revise (or, on round 0, compose) this instrument's
    part, resolve requests addressed to it, and optionally raise new ones.

    Same never-crash contract as `compose_part` — repair failures ship as-is and
    surface later via `validate_song`.

    Drum parts skip the LLM (see `compose_part`) and additionally do not
    participate in negotiation: their part is regenerated verbatim and they emit
    no resolutions or new requests. A pending request addressed to the drums is
    declined here so the arbiter sees it as resolved rather than stuck pending.
    """
    if roster_item.is_drum:
        part = _drum_part(header, roster_item)
        declined = [
            RequestResolution(
                request_id=r.id, accepted=False,
                resolution="drums use a deterministic pattern this round",
            )
            for r in pending
        ]
        return part, declined, []
    if llm is None:
        from llm_band.infrastructure.gemini.llm import make_llm

        llm = make_llm("instrument")

    if existing_part is None:
        return _compose_turn_full(
            header, roster_item, roster, peer_summaries, pending, llm,
        )
    return _compose_turn_revision(
        header, roster_item, roster, peer_summaries, pending, existing_part, llm,
    )


def _compose_turn_full(
    header: Header,
    roster_item: RosterItem,
    roster: list[RosterItem],
    peer_summaries: dict[str, str],
    pending: list[NegotiationRequest],
    llm,
) -> tuple[Part, list[RequestResolution], list[NewRequest]]:
    structured = llm.with_structured_output(InstrumentTurnOutput)
    messages = [
        ("system", _system_prompt(header, roster_item) + _negotiation_etiquette()),
        ("human", f"Other instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"),
        ("human", _pending_context(pending)),
    ]
    out = _invoke_structured(structured, messages, "InstrumentTurnOutput")
    if out is None:
        return _fallback_part(roster_item), [], []
    part = _to_part(roster_item, out)

    for _ in range(MAX_REPAIRS):
        issues = _validate_part(header, roster_item, part)
        if not issues:
            break
        messages = messages + [
            ("ai", f"My part: {out.notes_summary}"),
            ("human", _repair_prompt(issues)),
        ]
        out = _invoke_structured(structured, messages, "InstrumentTurnOutput")
        if out is None:
            return _fallback_part(roster_item), [], []
        part = _to_part(roster_item, out)

    return part, out.request_resolutions, out.new_requests


def _compose_turn_revision(
    header: Header,
    roster_item: RosterItem,
    roster: list[RosterItem],
    peer_summaries: dict[str, str],
    pending: list[NegotiationRequest],
    existing_part: Part,
    llm,
) -> tuple[Part, list[RequestResolution], list[NewRequest]]:
    """Diff-based revision: ask the LLM for a small list of NoteEdits against
    `existing_part`, apply them via `apply_edits`, and run the same repair loop
    on edit-application failures + validation issues."""
    structured = llm.with_structured_output(InstrumentRevisionOutput)
    messages = [
        ("system", _system_prompt(header, roster_item) + _revision_etiquette() + _negotiation_etiquette()),
        ("human", f"Other instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"),
        ("human", f"Your current part:\n{_compact_part_text(existing_part)}"),
        ("human", _pending_context(pending)),
    ]

    out = _invoke_structured(structured, messages, "InstrumentRevisionOutput")
    if out is None:
        # fall back to the existing part rather than wiping it — a missing
        # diff means "no change" is the safest interpretation
        return existing_part.model_copy(), [], []
    part, failures = apply_edits(existing_part, out.edits, num_bars=header.num_bars)
    part = part.model_copy(update={
        "notes_summary": out.notes_summary or existing_part.notes_summary,
        "self_notes": out.self_notes,
    })

    for _ in range(MAX_REPAIRS):
        issues = _validate_part(header, roster_item, part)
        if not failures and not issues:
            break
        followups = []
        if failures:
            followups.append(("human", _edit_failure_prompt(failures)))
        if issues:
            followups.append(("human", _repair_prompt(issues)))
        messages = messages + [("ai", f"My edits: {out.notes_summary}")] + followups
        out = _invoke_structured(structured, messages, "InstrumentRevisionOutput")
        if out is None:
            return part, [], []
        # repair edits are applied to the *original* part again, not stacked on
        # the previous repair attempt — otherwise the agent has to reason about
        # what its own broken diff already did, which it can't.
        part, failures = apply_edits(existing_part, out.edits, num_bars=header.num_bars)
        part = part.model_copy(update={
            "notes_summary": out.notes_summary or existing_part.notes_summary,
            "self_notes": out.self_notes,
        })

    return part, out.request_resolutions, out.new_requests
