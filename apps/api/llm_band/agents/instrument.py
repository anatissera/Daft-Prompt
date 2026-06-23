"""Instrument agent — composes one part (Phase 4: a single pass, no negotiation yet).

Constrained by the immutable header, this instrument's role/range, and (once peers
have composed — relevant from Phase 5's negotiation rounds onward) their compact
`notes_summary` strings, never their full note lists (token cost). Reuses `Note`
directly as the structured-output schema so there is one schema for the LLM
contract and the canonical SongState (see PRD gotcha: schema drift).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..music.theory import beats_per_bar
from ..music.validators import ValidationIssue, errors_only, validate_song
from ..schema import Header, Note, Part, RosterItem, SongState

MAX_REPAIRS = 2


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
    """
    if llm is None:
        from ..llm import make_llm

        llm = make_llm("instrument")
    structured = llm.with_structured_output(InstrumentOutput)

    messages = [
        ("system", _system_prompt(header, roster_item)),
        ("human", f"Other instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"),
    ]
    out: InstrumentOutput = structured.invoke(messages)
    part = _to_part(roster_item, out)

    for _ in range(MAX_REPAIRS):
        issues = _validate_part(header, roster_item, part)
        if not issues:
            break
        messages = messages + [
            ("ai", f"My part: {out.notes_summary}"),
            ("human", _repair_prompt(issues)),
        ]
        out = structured.invoke(messages)
        part = _to_part(roster_item, out)

    return part
