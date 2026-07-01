"""Instrument agent — composes one part.

Phase 4: single pass via `compose_part` (non-negotiation graph).
Phase 5: full negotiation via `run_instrument_turn`, called once per round per
         addressed instrument. The `batch_peer_ids` parameter scopes negotiation
         requests to instruments within the same composition group.
"""

from __future__ import annotations

from typing import Optional

from langsmith import get_current_run_tree, traceable
from pydantic import BaseModel, Field

from ..config import get_settings
from ..infrastructure.llm import LLMError
from ..music.theory import beats_per_bar, chord_tone_names
from ..music.validators import ValidationIssue, errors_only, validate_song
from ..skills._tables import DRUM_PATTERNS, DRUM_PATTERN_ALIASES
from ..skills.edits import EditFailure, NoteEdit, apply_edits
from ..skills.rhythm import drum_pattern
from ..domain.song_state import (
    ChordSpan,
    Header,
    NegotiationRequest,
    Note,
    Part,
    RosterItem,
    Section,
    SongState,
)

MAX_REPAIRS = 1
STRUCTURED_OUTPUT_RETRIES = 1


class InstrumentOutput(BaseModel):
    notes: list[Note] = Field(description="this instrument's notes for the whole song")
    notes_summary: str = Field(
        description="1-2 sentence compact summary peers can read instead of the full note list"
    )
    self_notes: str = Field(default="", description="optional notes to self for later revision")


def _chord_map_text(chord_progression: list[ChordSpan]) -> str:
    """Compact chord map: collapse contiguous bars sharing a chord into a range,
    render one line per range, and list each chord's tones only once at the end.

    Old form was "bar N: Chord (chord tones: X, Y, Z)" per bar — for an 8-bar
    song that is ~16 lines × 5 instruments × N rounds of prefill. The bar-range
    form is typically 3-5 lines plus a compact tone appendix, which cuts the
    prompt by 60-80% without losing information the model actually needs.
    """
    if not chord_progression:
        return "(no chord map provided)"
    ordered = sorted(chord_progression, key=lambda x: x.bar)
    ranges: list[tuple[int, int, str]] = []
    start, prev_chord = ordered[0].bar, ordered[0].chord
    prev_bar = start
    for cs in ordered[1:]:
        if cs.chord == prev_chord and cs.bar == prev_bar + 1:
            prev_bar = cs.bar
            continue
        ranges.append((start, prev_bar, prev_chord))
        start, prev_chord, prev_bar = cs.bar, cs.chord, cs.bar
    ranges.append((start, prev_bar, prev_chord))

    map_lines = [
        f"  bars {a}-{b}: {c}" if a != b else f"  bar {a}: {c}"
        for a, b, c in ranges
    ]
    seen: dict[str, tuple[str, ...]] = {}
    for _, _, chord in ranges:
        if chord in seen:
            continue
        tones = chord_tone_names(chord)
        if tones:
            seen[chord] = tuple(tones)
    tone_appendix = (
        "\n  chord tones: "
        + "; ".join(f"{ch}=[{','.join(ts)}]" for ch, ts in seen.items())
    ) if seen else ""
    return (
        "Chord map (land sustained notes on chord tones; passing tones OK):\n"
        + "\n".join(map_lines)
        + tone_appendix
    )


def _section_map_text(sections: list[Section]) -> str:
    """Sections as a single line: `verse[0-3, mid] | chorus[4-7, high]`."""
    if not sections:
        return "(no section map provided)"
    parts = [f"{s.name}[{s.start_bar}-{s.end_bar}, {s.energy}]" for s in sections]
    return "Sections: " + " | ".join(parts)


def _peer_context(roster: list[RosterItem], self_id: str, peer_summaries: dict[str, str]) -> str:
    lines = [
        f"- {r.id} ({r.instrument}, {r.role}): {peer_summaries.get(r.id, 'not composed yet')}"
        for r in roster
        if r.id != self_id
    ]
    return "\n".join(lines) or "(no other instruments)"


def _song_system_prompt(header: Header) -> str:
    """Song-level system prompt — identical across every instrument and every
    round of a compose. Structured this way so Gemini 2.5's implicit cache and
    llama-server's prompt cache hit on the shared prefix instead of paying full
    prefill on every LLM call. Instrument-specific content moves to the first
    human turn so it does not perturb the cached system_instruction.
    """
    bpb = beats_per_bar(header.time_signature)
    return (
        f"/no_think You are one player in a {header.genre} ensemble.\n"
        f"Key {header.key}, {header.tempo_bpm} BPM, "
        f"{header.time_signature[0]}/{header.time_signature[1]} ({bpb} beats/bar), "
        f"{header.num_bars} bars (0..{header.num_bars - 1}).\n"
        f"{_section_map_text(header.sections)}\n"
        f"{_chord_map_text(header.chord_progression)}\n\n"
        "Output your part as notes (bar, start_beat 0-indexed in bar, MIDI pitch "
        "null=rest, dur in beats, velocity 0-127). Match section energy for dynamics. "
        "Stay in your range and bar bounds. Add a short notes_summary. Structured "
        "output only — no prose."
    )


def _instrument_intro(roster_item: RosterItem) -> str:
    """Per-instrument context — lives in the first human turn (see
    `_song_system_prompt`) so it doesn't invalidate the shared system-prompt cache."""
    drum_note = (
        " (percussion — pitch is a GM drum key; range/key checks don't apply)"
        if roster_item.is_drum
        else ""
    )
    style_line = (
        f"\nPlaying style: {roster_item.playing_style}" if roster_item.playing_style else ""
    )
    return (
        f"You play {roster_item.instrument} ({roster_item.role}). "
        f"Range MIDI {roster_item.midi_range[0]}-{roster_item.midi_range[1]}{drum_note}."
        f"{style_line}"
    )


def _repair_prompt(issues: list[ValidationIssue]) -> str:
    bullets = "\n".join(f"- {i.message}" for i in issues)
    return (
        "Your part had validation errors — return a complete, corrected part "
        f"(not a diff) that fixes:\n{bullets}"
    )


def _negotiation_etiquette(batch_peer_ids: list[str]) -> str:
    scope = (
        f" You may only raise requests to instruments in your current composition group: "
        f"{', '.join(batch_peer_ids)}. Do not address instruments outside this group."
        if batch_peer_ids
        else ""
    )
    return (
        "\nYou may also ask a peer for a specific accommodation (leave space, change a "
        "note). Format: to (id), bars, request, why. Only raise if it meaningfully helps."
        + scope
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
    """Pick a `drum_pattern` style key from the roster item's role and the
    header's genre. Role wins (so the director can override per-song with
    "drums — boom_bap"); otherwise the genre is matched directly, then aliased,
    then defaulted to `rock_basic`.
    """
    playing_style = (roster_item.playing_style or "").lower()
    haystacks = [roster_item.role.lower(), playing_style, header.genre.lower()]
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

    Bypasses one full LLM turn per round the drums would have participated in.
    `notes_summary` names the pattern so peer instruments still get useful
    context; `self_notes` records the skill origin so a later revision pass can
    tell a skill-derived part apart from an LLM-generated one.
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


@traceable(run_type="chain", name="instrument:compose")
def compose_part(
    header: Header,
    roster_item: RosterItem,
    roster: list[RosterItem],
    peer_summaries: dict[str, str],
    llm=None,
) -> Part:
    """Compose one instrument's part, with a bounded repair loop on validation failure.

    Used by the non-negotiation graph (Phase 4 / `run_instruments`).

    Drum parts skip the LLM entirely and ship a deterministic `drum_pattern` —
    note-by-note drum generation buys no quality over a curated pattern table
    and costs a full turn per round.
    """
    run = get_current_run_tree()
    if run is not None:
        run.name = roster_item.instrument
    if roster_item.is_drum:
        return _drum_part(header, roster_item)
    if llm is None:
        from music_assistant.infrastructure.gemini.llm import make_llm
        llm = make_llm("instrument")
    structured = llm.with_structured_output(InstrumentOutput)

    messages = [
        ("system", _song_system_prompt(header)),
        ("human", _instrument_intro(roster_item)
                    + f"\n\nOther instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"),
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
    """Diff-based output used by negotiation rounds > 0 for efficiency.

    Round > 0 turns currently re-emit the entire ~100-note part every revision;
    switching to a small edit list (add/replace/remove) is the dominant output-
    token win. The agent reads its current part in a compact one-line-per-note
    text form as input, then emits only the deltas.
    """

    edits: list[NoteEdit] = Field(
        default_factory=list,
        description="add/replace/remove edits against your current part; each anchors to (bar, start_beat)",
    )
    notes_summary: str = Field(description="updated 1-2 sentence summary peers can read")
    self_notes: str = Field(default="", description="optional notes to self for later revision")
    request_resolutions: list[RequestResolution] = Field(default_factory=list)
    new_requests: list[NewRequest] = Field(default_factory=list)


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
    bullets = "\n".join(
        f"- {f.edit.op} bar={f.edit.bar} beat={f.edit.start_beat:g}: {f.reason}"
        for f in failures
    )
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


def _pending_context(pending: list[NegotiationRequest]) -> str:
    if not pending:
        return "(no pending requests addressed to you)"
    lines = [
        f"- [{r.id}] from {r.from_}, bars {r.bars}: {r.request} (why: {r.rationale})"
        for r in pending
    ]
    return "Pending requests addressed to you — accept (and patch your part) or decline each:\n" + "\n".join(lines)


@traceable(run_type="chain", name="instrument:turn")
def run_instrument_turn(
    header: Header,
    roster_item: RosterItem,
    roster: list[RosterItem],
    peer_summaries: dict[str, str],
    batch_peer_ids: list[str],
    pending: list[NegotiationRequest],
    existing_part: Optional[Part],
    llm=None,
) -> tuple[Part, list[RequestResolution], list[NewRequest]]:
    """One negotiation-round turn: revise (or compose on round 0) this instrument's
    part, resolve requests addressed to it, and optionally raise new ones.

    `batch_peer_ids` lists the other roster ids in this composition group — the
    negotiation etiquette block tells the model to only raise requests to those ids.

    Drums skip the LLM entirely (see `compose_part`) and do not participate in
    negotiation — pending requests addressed to the drums are declined so the
    arbiter sees them resolved rather than stuck pending.

    Round-0 turns (no `existing_part`) use `InstrumentTurnOutput` — the full
    note list. Round >0 turns switch to `InstrumentRevisionOutput`, emitting a
    diff against the current part. See `_compose_turn_revision`.
    """
    run = get_current_run_tree()
    if run is not None:
        run.name = roster_item.instrument
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
        from music_assistant.infrastructure.gemini.llm import make_llm
        llm = make_llm("instrument")

    if existing_part is None:
        return _compose_turn_full(
            header, roster_item, roster, peer_summaries, batch_peer_ids, pending, llm,
        )
    return _compose_turn_revision(
        header, roster_item, roster, peer_summaries, batch_peer_ids, pending, existing_part, llm,
    )


def _compose_turn_full(
    header: Header,
    roster_item: RosterItem,
    roster: list[RosterItem],
    peer_summaries: dict[str, str],
    batch_peer_ids: list[str],
    pending: list[NegotiationRequest],
    llm,
) -> tuple[Part, list[RequestResolution], list[NewRequest]]:
    """Fresh compose / round-0 turn: full-note-list structured output."""
    structured = llm.with_structured_output(InstrumentTurnOutput)
    messages = [
        ("system", _song_system_prompt(header)),
        ("human", _instrument_intro(roster_item) + _negotiation_etiquette(batch_peer_ids)
                    + f"\n\nOther instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"),
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
    batch_peer_ids: list[str],
    pending: list[NegotiationRequest],
    existing_part: Part,
    llm,
) -> tuple[Part, list[RequestResolution], list[NewRequest]]:
    """Diff-based revision: LLM returns a small `list[NoteEdit]` instead of the
    full ~100-note part, cutting output tokens by 80-95% on the common case
    where only a handful of notes change.

    Repair loop covers both edit-application failures (unmatched targets,
    occupied slots) and downstream validation issues — corrective edits are
    reapplied to the *original* part each iteration rather than stacked on the
    previous broken diff, so the model doesn't have to reason about what its
    own bad output already did.
    """
    structured = llm.with_structured_output(InstrumentRevisionOutput)
    messages = [
        ("system", _song_system_prompt(header)),
        ("human", _instrument_intro(roster_item)
                    + _revision_etiquette() + _negotiation_etiquette(batch_peer_ids)
                    + f"\n\nOther instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"),
        ("human", f"Your current part:\n{_compact_part_text(existing_part)}"),
        ("human", _pending_context(pending)),
    ]

    out = _invoke_structured(structured, messages, "InstrumentRevisionOutput")
    if out is None:
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
        part, failures = apply_edits(existing_part, out.edits, num_bars=header.num_bars)
        part = part.model_copy(update={
            "notes_summary": out.notes_summary or existing_part.notes_summary,
            "self_notes": out.self_notes,
        })

    return part, out.request_resolutions, out.new_requests
