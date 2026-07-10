"""Instrument agent — composes one part.

Phase 4: single pass via `compose_part` (non-negotiation graph).
Phase 5: full negotiation via `run_instrument_turn`, called once per round per
         addressed instrument. The `batch_peer_ids` parameter scopes negotiation
         requests to instruments within the same composition group.
"""

from __future__ import annotations

import logging
from typing import Optional

from langsmith import get_current_run_tree, traceable
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

from ..config import get_settings
from ..corpus.retrieve import (
    GroovePattern,
    LakhExample,
    retrieve_groove,
    retrieve_style_examples,
)
from ..infrastructure.llm import LLMError
from ..music.theory import beats_per_bar, chord_tone_names
from ..music.validators import ValidationIssue, errors_only, validate_song
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

MAX_REPAIRS = 2
STRUCTURED_OUTPUT_RETRIES = 1


class InstrumentOutput(BaseModel):
    notes: list[Note] = Field(description="this instrument's notes for the whole song")
    notes_summary: str = Field(
        description="1-2 sentence compact summary peers can read instead of the full note list"
    )
    self_notes: str = Field(default="", description="optional notes to self for later revision")


class MinimalInstrumentOutput(BaseModel):
    """Stripped-down schema used as a retry when the rich InstrumentOutput
    can't be parsed (M3 truncates JSON on long outputs, Gemini emits None,
    etc.). Same note payload, no summary/self_notes overhead — lets the LLM
    focus its output budget on notes."""

    notes: list[Note] = Field(description="this instrument's notes for this call")


def _chord_map_text(chord_progression: list[ChordSpan]) -> str:
    if not chord_progression:
        return "(no chord map provided)"
    lines = []
    for cs in sorted(chord_progression, key=lambda x: x.bar):
        tones = chord_tone_names(cs.chord)
        suffix = f"  (chord tones: {', '.join(tones)})" if tones else ""
        lines.append(f"  bar {cs.bar}: {cs.chord}{suffix}")
    return (
        "Chord map — land sustained/structural notes on the listed chord tones; "
        "passing tones between them are fine, but avoid resting on notes outside both "
        "the chord and the key:\n" + "\n".join(lines)
    )


def _section_map_text(sections: list[Section]) -> str:
    if not sections:
        return "(no section map provided)"
    lines = [
        f"  {s.name:<14} bars {s.start_bar}-{s.end_bar}  energy: {s.energy}"
        for s in sections
    ]
    return "Song form:\n" + "\n".join(lines)


def _groove_reference_text(groove: Optional[GroovePattern]) -> str:
    """Format a retrieved drum groove as a compact per-channel grid the model
    can adapt (not copy). Empty string when nothing was retrieved so the prompt
    stays unchanged in fallback."""
    if not groove or not groove.pattern_by_channel:
        return ""
    lines = [
        f"Reference groove for this style ({groove.style}, ~{groove.bpm:.0f} bpm, "
        f"{groove.type}) — adapt in feel and idiom, do not copy verbatim:"
    ]
    for channel, grid in groove.pattern_by_channel.items():
        # collapse very long grids so many bars still fit on one line
        display = grid if len(grid) <= 64 else (grid[:64] + "...")
        lines.append(f"  {channel:<12} {display}")
    return "\n".join(lines)


def _melodic_reference_text(
    example: Optional[LakhExample], roster_item: RosterItem
) -> str:
    """Format a role-matched few-shot from a corpus track. Compact by design:
    progression + role hint + typical density, not raw notes. Empty when there is
    no example or the instrument's role has no matching corpus entry."""
    if example is None or not example.progression:
        return ""
    role_hint = ""
    for role in example.roles:
        if role in roster_item.instrument.lower() or role in roster_item.role.lower():
            density = example.density_by_role.get(role)
            if density is not None:
                role_hint = f" Peers in this style average ~{density:.1f} notes/bar for {role}."
            break
    prog = " | ".join(example.progression[:8])
    return (
        f"How this style typically sits (from a same-genre reference track "
        f"in {example.key}, ~{example.tempo:.0f} bpm): progression {prog}.{role_hint}"
    )


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
    playing_style_block = (
        f"\nPlaying style: {roster_item.playing_style}" if roster_item.playing_style else ""
    )
    # The director committed to a concrete groove for the whole ensemble. Inject
    # it verbatim so every per-instrument agent composes notes that fit the same
    # rhythmic idiom, instead of each one defaulting to generic pop quarter-notes.
    rhythmic_feel_block = (
        f"\n\nEnsemble rhythmic feel (director's commitment for the whole song — your notes "
        f"must sit inside this groove; if the block below names your role explicitly, follow "
        f"that guidance literally):\n{header.rhythmic_feel}"
        if header.rhythmic_feel
        else ""
    )
    reference_block = _style_reference_block(header, roster_item)
    register_note = "" if roster_item.is_drum else (
        "\n\nRegister: YOU decide the MIDI pitch range for this part. Read your "
        "playing_style + role + the genre and pick the register a real player of "
        "this instrument would use for THIS idiom. Examples: metal rhythm guitar "
        'chugging "low E string" → notes around MIDI 28-40; a soprano choir line → '
        "60-84; a sub bass → 24-36; a jazz walking bass → 28-52; a violin melody → "
        "55-96. Do NOT default to a textbook mid-register (~55-80) — that is "
        "usually wrong for rhythm/bass/lead specialisation. Match the described "
        "technique."
    )
    return (
        f"/no_think You are the {roster_item.instrument} player ({roster_item.role}) in a "
        f"{header.genre} ensemble.\n\n"
        f"Hard constraints:\n"
        f"- key: {header.key}, tempo: {header.tempo_bpm} BPM, "
        f"time signature {header.time_signature[0]}/{header.time_signature[1]} "
        f"({bpb} beats/bar)\n"
        f"- song length: {header.num_bars} bars (bar indices 0..{header.num_bars - 1})"
        f"{drum_note}"
        f"{register_note}\n\n"
        f"{_section_map_text(header.sections)}\n\n"
        f"{_chord_map_text(header.chord_progression)}"
        f"{rhythmic_feel_block}"
        f"{playing_style_block}"
        f"{reference_block}\n\n"
        "Compose your full part for the whole song: a list of notes with absolute bar "
        "+ start_beat (0-indexed within the bar), MIDI pitch (null = rest), duration in "
        "beats, and velocity (0-127). Shape your dynamics to the section energy levels "
        "(low = quieter/sparser, high = louder/fuller). Stay within bar/beat bounds. "
        "Also return a short notes_summary other musicians can read. "
        "Respond directly with the structured output only. Do not think out loud or write any reasoning."
    )


def _style_reference_block(header: Header, roster_item: RosterItem) -> str:
    """Retrieve a per-instrument style reference (drum groove or melodic hint)
    and format it into a prompt block. Fails silent on any retrieval error so a
    corpus outage never blocks composition."""
    try:
        if roster_item.is_drum:
            groove = retrieve_groove(header.genre, header.tempo_bpm, energy="medium")
            text = _groove_reference_text(groove)
        else:
            examples = retrieve_style_examples(header.genre, energy="medium", n=1)
            text = _melodic_reference_text(examples[0] if examples else None, roster_item)
    except Exception:
        return ""
    return f"\n\n{text}" if text else ""


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
        "\nYou may also ask another instrument for a specific accommodation (e.g. "
        "leave space in a bar for a fill, change a note to fit a chord). Phrase each "
        "as: which instrument (by roster id), which bar(s), what you're asking, and why. "
        "Only raise a request if it meaningfully improves the arrangement — don't "
        "manufacture requests for their own sake." + scope
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


def _section_scope_block(section: Section) -> str:
    """Restrict this LLM call to a single section's bar range. The full song
    context (chord map, sections, rhythmic_feel) is still in the system prompt
    — this only says 'for THIS call, only write notes for bars X..Y'. Slicing
    the output like this drops the per-call token budget so M3-family models
    stop truncating JSON mid-note on long songs (the root cause of the '0
    agent passes' bug on 32-bar dubstep runs)."""
    return (
        f"\n\nCOMPOSITION SLICE for this call: emit notes ONLY for bars "
        f"{section.start_bar} to {section.end_bar - 1} inclusive "
        f"(section '{section.name}', energy {section.energy}). Any note "
        f"outside this range will be dropped. The other bars will be "
        f"composed in separate calls, so trust the section boundary and "
        f"don't try to cover the whole song here."
    )


def _clip_notes_to_range(notes: list[Note], start_bar: int, end_bar: int) -> list[Note]:
    """Belt-and-braces: even after the slice instruction, models sometimes
    emit stray notes outside the requested range. Drop them so concatenation
    doesn't double up bars between calls."""
    return [n for n in notes if start_bar <= n.bar < end_bar]


def _compose_section(
    header: Header,
    section: Section,
    roster_item: RosterItem,
    peer_context_text: str,
    llm,
) -> list[Note]:
    """Compose one section's notes. Tries rich InstrumentOutput first, falls
    back to MinimalInstrumentOutput (schema B), then to the LLM-seeded
    fill (see fallback_fill.llm_seeded_section). Returns notes clipped to
    this section's bar range."""
    system = _system_prompt(header, roster_item) + _section_scope_block(section)
    base_messages = [
        ("system", system),
        ("human", peer_context_text),
    ]

    rich = llm.with_structured_output(InstrumentOutput)
    out = _invoke_structured(rich, base_messages, "InstrumentOutput")
    if out is not None and out.notes:
        return _clip_notes_to_range(out.notes, section.start_bar, section.end_bar)

    # Retry with a minimal schema. Some providers succeed here because the
    # smaller schema removes the summary/self_notes overhead from the JSON
    # they need to emit.
    minimal = llm.with_structured_output(MinimalInstrumentOutput)
    min_out = _invoke_structured(minimal, base_messages, "MinimalInstrumentOutput")
    if min_out is not None and min_out.notes:
        return _clip_notes_to_range(min_out.notes, section.start_bar, section.end_bar)

    # Last resort: LLM-seeded fill uses the director's committed
    # rhythmic_feel + this instrument's playing_style to produce a short
    # loopable pattern. Only when this ALSO fails does the deterministic
    # `fallback_fill.deterministic_fill` kick in (handled by the caller).
    from ..band_agent.tools.fallback_fill import llm_seeded_section
    seeded = llm_seeded_section(header, section, roster_item, llm)
    if seeded:
        return _clip_notes_to_range(seeded, section.start_bar, section.end_bar)

    return []


def _sections_for_compose(header: Header) -> list[Section]:
    """Return the section list to iterate over. If the director gave us no
    sections, treat the whole song as one implicit section — that keeps
    single-section behaviour working with the same section-scoped call path."""
    if header.sections:
        return list(header.sections)
    return [Section(name="all", start_bar=0, end_bar=header.num_bars, energy="medium")]


@traceable(run_type="chain", name="instrument:compose")
def compose_part(
    header: Header,
    roster_item: RosterItem,
    roster: list[RosterItem],
    peer_summaries: dict[str, str],
    llm=None,
) -> Part:
    """Compose one instrument's part by iterating over the song's sections and
    concatenating each section's notes. Splitting the ask drops the per-call
    output budget so LLMs stop truncating on long songs (32-bar dubstep runs
    were returning 0 notes because a single-call output was too large for M3
    to complete). Each section falls through rich schema → minimal schema →
    LLM-seeded pattern → deterministic (`fallback_fill.deterministic_fill`)
    independently, so one bad section doesn't kill the whole part.

    Used by the non-negotiation graph (Phase 4 / `run_instruments`).
    """
    run = get_current_run_tree()
    if run is not None:
        run.name = roster_item.instrument
    if llm is None:
        from music_assistant.infrastructure.gemini.llm import make_llm
        llm = make_llm("instrument")

    peer_ctx_text = f"Other instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"
    all_notes: list[Note] = []
    for section in _sections_for_compose(header):
        section_notes = _compose_section(
            header=header,
            section=section,
            roster_item=roster_item,
            peer_context_text=peer_ctx_text,
            llm=llm,
        )
        if not section_notes:
            # Every LLM-based path failed for this section. Fall back to the
            # deterministic per-bar generator, scoped to this section only,
            # so we still ship a musical result instead of silence.
            from ..band_agent.tools.fallback_fill import deterministic_section
            section_notes = deterministic_section(header, section, roster_item)
        all_notes.extend(section_notes)

    part = Part(
        instrument_id=roster_item.id,
        notes=all_notes,
        notes_summary=f"{roster_item.role} across {len(_sections_for_compose(header))} section(s)",
        self_notes="",
    )

    # Validation repair loop (single-shot, kept intentionally cheap). We no
    # longer send it back to the LLM per section — validation issues are rare
    # after section-scoped composition, and the repair prompt against a
    # rich-schema full-song ask is what used to consume the token budget
    # models struggle with. Section-clipping already enforces bar bounds.
    issues = _validate_part(header, roster_item, part)
    if issues:
        log.info(
            "instrument part validated with %d issue(s) post-section-compose: id=%s",
            len(issues), roster_item.id,
        )

    if not any(n.pitch is not None for n in part.notes):
        log.warning(
            "instrument produced empty part after all fallbacks: id=%s instrument=%r role=%r",
            roster_item.id, roster_item.instrument, roster_item.role,
        )
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
    """
    run = get_current_run_tree()
    if run is not None:
        run.name = roster_item.instrument
    if llm is None:
        from music_assistant.infrastructure.gemini.llm import make_llm
        llm = make_llm("instrument")
    structured = llm.with_structured_output(InstrumentTurnOutput)

    messages = [
        ("system", _system_prompt(header, roster_item) + _negotiation_etiquette(batch_peer_ids)),
        ("human", f"Other instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"),
    ]
    if existing_part is not None:
        messages.append(("ai", f"My current part: {existing_part.notes_summary}"))
    messages.append(("human", _pending_context(pending)))

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

    if not any(n.pitch is not None for n in part.notes):
        log.warning(
            "instrument produced empty part after repair (turn): id=%s instrument=%r role=%r",
            roster_item.id, roster_item.instrument, roster_item.role,
        )
    return part, out.request_resolutions, out.new_requests
