"""Director agent — reasons an arrangement (header + roster) from a style string.

This is the first LLM node. It does NOT compose notes (that's the instrument agents
in Phase 4); it decides key/tempo/meter/form and the *reasoned* instrumentation
(not a hardcoded genre->instrument table). Output is constrained by structured
output so it maps cleanly onto `SongState.header` + `SongState.roster`.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..domain.song_state import ChordSpan, Header, RosterItem, Section, SongState

MIN_ROSTER = 3
MAX_ROSTER = 8
MIN_BARS = 4
MAX_BARS = 32


# ---- Director output schema (what the LLM must return) --------------------

class ArrangementInstrument(BaseModel):
    id: str = Field(description="short unique id, e.g. 'bass', 'lead_synth'")
    instrument: str = Field(description="human name, e.g. 'electric_bass'")
    midi_program: int = Field(0, ge=0, le=127, description="General MIDI program")
    midi_low: int = Field(0, ge=0, le=127)
    midi_high: int = Field(127, ge=0, le=127)
    role: str = Field(description="this instrument's musical role in the arrangement")
    is_drum: bool = False


class ArrangementSection(BaseModel):
    name: str
    start_bar: int = Field(ge=0)
    end_bar: int = Field(ge=0)


class DirectorOutput(BaseModel):
    genre: str
    key: str = Field(description="e.g. 'F# minor', 'C major'")
    tempo_bpm: float = Field(gt=0)
    time_sig_numerator: int = Field(4, gt=0)
    time_sig_denominator: int = Field(4, gt=0)
    num_bars: int = Field(gt=0, description=f"between {MIN_BARS} and {MAX_BARS} bars")
    sections: list[ArrangementSection] = Field(default_factory=list)
    instruments: list[ArrangementInstrument] = Field(
        description=f"between {MIN_ROSTER} and {MAX_ROSTER} instruments"
    )


_SYSTEM = (
    "You are the musical director of an ensemble. Given a style description, decide "
    "the key, tempo, time signature, number of bars, a section/form map, and the "
    f"instrumentation — choose {MIN_ROSTER}-{MAX_ROSTER} instruments and {MIN_BARS}-{MAX_BARS} bars that genuinely "
    "fit the style (reason about it; do not use a fixed genre table). For each "
    "instrument give a General MIDI program, a sensible MIDI pitch range, and its "
    "role. Mark drum/percussion kits with is_drum=true."
)


def _prompt(style: str) -> list[tuple[str, str]]:
    return [("system", _SYSTEM), ("human", f"Style: {style}")]


def _clamp_roster(items: list[ArrangementInstrument]) -> list[ArrangementInstrument]:
    return items[:MAX_ROSTER]


def _clamp_num_bars(value: int) -> int:
    return max(MIN_BARS, min(MAX_BARS, value))


def _clamp_sections(sections: list[ArrangementSection], num_bars: int) -> list[Section]:
    clamped = []
    for section in sections:
        start = max(0, min(section.start_bar, num_bars - 1))
        end = max(start + 1, min(section.end_bar, num_bars))
        clamped.append(Section(name=section.name, start_bar=start, end_bar=end))
    return clamped


def arrangement_to_song(style: str, out: DirectorOutput) -> SongState:
    num_bars = _clamp_num_bars(out.num_bars)
    header = Header(
        genre=out.genre,
        key=out.key,
        tempo_bpm=out.tempo_bpm,
        time_signature=(out.time_sig_numerator, out.time_sig_denominator),
        num_bars=num_bars,
        sections=_clamp_sections(out.sections, num_bars),
        chord_progression=[],  # filled by later phases if needed
    )
    roster = [
        RosterItem(
            id=i.id,
            instrument=i.instrument,
            midi_program=i.midi_program,
            midi_range=(min(i.midi_low, i.midi_high), max(i.midi_low, i.midi_high)),
            role=i.role,
            is_drum=i.is_drum,
        )
        for i in _clamp_roster(out.instruments)
    ]
    return SongState(request=style, header=header, roster=roster, parts={})


def run_director(style: str, llm=None) -> SongState:
    """Run the director. Pass `llm` (a chat model) to inject a fake in tests;
    otherwise a provider model is built from settings."""
    if llm is None:
        from music_assistant.infrastructure.gemini.llm import make_llm

        llm = make_llm("director")
    structured = llm.with_structured_output(DirectorOutput)
    out: DirectorOutput = structured.invoke(_prompt(style))
    return arrangement_to_song(style, out)
