"""`BandSpec` — the planner's structured-output schema.

Kept intentionally close to `SongState` so `compose_band` is a straight-line
materialisation. Two differences:

  - Roster items carry a `patch` literal from the closed vocabulary in
    `domain.patch` (so the planner cannot invent a program number). The
    numeric `midi_program` / `synth_preset` are derived at compose-band time.
  - A per-instrument `notes` list is inlined on each roster entry — the
    planner emits one flat structure instead of a separate `parts` dict.
    `compose_band` splits it back out.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from music_assistant.domain.patch import Patch


class SectionPlan(BaseModel):
    name: str
    start_bar: int = Field(ge=0)
    end_bar: int = Field(ge=0)
    energy: Literal["low", "medium", "high"] = "medium"


class ChordSpanPlan(BaseModel):
    bar: int = Field(ge=0)
    chord: str


class NotePlan(BaseModel):
    bar: int = Field(ge=0)
    start_beat: float = Field(ge=0.0)
    pitch: Optional[int] = Field(default=None, ge=0, le=127)
    dur: float = Field(default=1.0, gt=0.0)
    velocity: int = Field(default=96, ge=1, le=127)


class InstrumentPlan(BaseModel):
    id: str
    instrument: str
    patch: Patch
    role: str = ""
    is_drum: bool = False
    playing_style: str = ""
    notes: list[NotePlan] = Field(default_factory=list)


class BandSpec(BaseModel):
    """Fully-specified plan emitted by the LLM in one structured-output call."""

    genre: str
    key: str = "C major"
    tempo_bpm: float = Field(default=120.0, gt=20.0, lt=300.0)
    time_signature_numerator: int = Field(default=4, ge=1, le=12)
    time_signature_denominator: int = Field(default=4, ge=1, le=16)
    num_bars: int = Field(default=16, ge=4, le=128)
    sections: list[SectionPlan] = Field(default_factory=list)
    chord_progression: list[ChordSpanPlan] = Field(default_factory=list)
    instruments: list[InstrumentPlan] = Field(default_factory=list)
