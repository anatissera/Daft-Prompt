"""Canonical `SongState` schema shared across the composition pipeline."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Section(BaseModel):
    name: str
    start_bar: int
    end_bar: int
    energy: Literal["low", "medium", "high"] = "medium"


class ChordSpan(BaseModel):
    bar: int
    chord: str


class CompositionGroup(BaseModel):
    name: str
    instrument_ids: list[str]
    max_negotiation_rounds: int = Field(1, ge=0, le=2)


class Header(BaseModel):
    """Immutable global plan set by the director."""

    genre: str
    key: str
    tempo_bpm: float
    time_signature: tuple[int, int] = (4, 4)
    num_bars: int
    sections: list[Section] = Field(default_factory=list)
    chord_progression: list[ChordSpan] = Field(default_factory=list)
    # Director's commitment to the rhythmic idiom of the requested style.
    # Free-text 3-6 sentences that the per-instrument agent reads before
    # composing notes. Empty for older Songs (backwards-compatible default).
    rhythmic_feel: str = ""


from .patch import Patch, SynthPreset  # re-exported for backward compat


class RosterItem(BaseModel):
    id: str
    instrument: str
    # `patch` is the single source of truth for timbre — chosen semantically
    # by the director from the closed vocabulary in `domain.patch`. The
    # numeric `midi_program` and `synth_preset` fields below are DERIVED from
    # `patch` at `arrangement_to_song` time. They stay on the roster so the
    # frontend and MIDI writer don't need the mapping table.
    patch: Optional[Patch] = None
    midi_program: int = 0
    role: str = ""
    playing_style: str = ""
    is_drum: bool = False
    synth_preset: Optional[SynthPreset] = None


class Note(BaseModel):
    bar: int
    start_beat: float
    pitch: Optional[int] = None
    dur: float = 1.0
    velocity: int = 96


class Part(BaseModel):
    instrument_id: str
    version: int = 1
    notes: list[Note] = Field(default_factory=list)
    notes_summary: str = ""
    self_notes: str = ""


class NegotiationRequest(BaseModel):
    id: str
    from_: str = Field(alias="from")
    to: str
    round: int = 0
    bars: list[int] = Field(default_factory=list)
    request: str = ""
    rationale: str = ""
    status: Literal["pending", "resolved", "declined"] = "pending"
    resolution: str = ""

    model_config = {"populate_by_name": True}


class SongState(BaseModel):
    request: str
    header: Header
    roster: list[RosterItem] = Field(default_factory=list)
    parts: dict[str, Part] = Field(default_factory=dict)
    negotiation_requests: list[NegotiationRequest] = Field(default_factory=list)
    composition_groups: list[CompositionGroup] = Field(default_factory=list)
    round: int = 0
    converged: bool = False
    errors: list[str] = Field(default_factory=list)
