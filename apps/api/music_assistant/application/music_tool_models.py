"""Pydantic contracts for explicit musical chat tools."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from music_assistant.domain.audio_profile import ExplanationAnswer
from music_assistant.domain.song_state import SongState


MusicToolName = Literal[
    "research_song",
    "get_song_profile",
    "get_chords",
    "get_sections",
    "get_instruments",
    "get_instrument_summary",
    "get_tab_excerpt",
    "get_conflicts",
    "get_missing_data",
    "request_composition",
    "clarify",
    "off_topic",
    "answer_profile",
    "compose",
    "compose_from_reference",
]


class ChatAgentDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tool: MusicToolName = Field(alias="action")
    query: Optional[str] = None
    reference_id: Optional[str] = None
    section_name: Optional[str] = None
    instrument: Optional[str] = None
    start_measure: Optional[int] = None
    measure_count: Optional[int] = None
    composition_request: Optional[str] = None
    clarification: Optional[str] = None


class ResearchSongToolInput(BaseModel):
    query: str = Field(min_length=1)


class SongReferenceToolInput(BaseModel):
    reference_id: str = Field(min_length=1)


class AnswerProfileToolInput(SongReferenceToolInput):
    question: str = Field(min_length=1)


class ChordsToolInput(SongReferenceToolInput):
    section_name: Optional[str] = None


class SectionsToolInput(SongReferenceToolInput):
    pass


class InstrumentsToolInput(SongReferenceToolInput):
    instrument: Optional[str] = None


class InstrumentSummaryToolInput(SongReferenceToolInput):
    instrument: str = Field(min_length=1)


class TabExcerptToolInput(SongReferenceToolInput):
    instrument: str = Field(min_length=1)
    start_measure: int = Field(default=0, ge=0)
    measure_count: int = Field(default=4, ge=1, le=8)


class CompositionRequestToolInput(BaseModel):
    composition_request: str = Field(min_length=1)
    reference_id: Optional[str] = None
    reference_ids: list[str] = Field(default_factory=list)


class ToolOutput(BaseModel):
    tool: str
    reference_id: Optional[str] = None
    answer: str = ""
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    intent: Literal["answer_reference", "compose", "compose_from_reference", "clarify", "off_topic"] = "answer_reference"


class ResearchSongToolOutput(ToolOutput):
    tool: str = "research_song"
    evidence_count: int = 0
    instrument_profile_summary: list[dict] = Field(default_factory=list)


class ProfileToolOutput(ToolOutput):
    tool: str = "get_song_profile"
    title: str = ""
    artist: Optional[str] = None
    sources: list[str] = Field(default_factory=list)
    songsterr_tab_index: dict = Field(default_factory=dict)
    instrument_profile_summary: list[dict] = Field(default_factory=list)


class AnswerToolOutput(ToolOutput):
    explanation: Optional[ExplanationAnswer] = None


class TrackIndexItem(BaseModel):
    instrument: str
    name: str
    part_id: int


class InstrumentsToolOutput(ToolOutput):
    tool: str = "get_instruments"
    loaded: bool = False
    instruments: list[str] = Field(default_factory=list)
    tracks: list[TrackIndexItem] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    warnings_count: int = 0


class TabExcerptMeasure(BaseModel):
    index: int
    marker: Optional[str] = None
    note_events: int = 0
    durations: list[str] = Field(default_factory=list)
    events: list["TabExcerptEvent"] = Field(default_factory=list)


class TabExcerptEvent(BaseModel):
    """Small, render-safe symbolic event for an in-chat tab excerpt.

    Keep this intentionally separate from Songsterr's raw payload. The client
    needs timing and playable string/fret positions, not provider internals.
    """

    beat_index: float
    duration: str = ""
    string: Optional[float] = None
    fret: Optional[int] = None
    pitch: Optional[int] = Field(default=None, ge=0, le=127)
    rest: bool = False
    tie: bool = False
    ghost: bool = False


class TabExcerptToolOutput(ToolOutput):
    tool: str = "get_tab_excerpt"
    instrument: str = ""
    track_name: str = ""
    tuning: list[str] = Field(default_factory=list)
    measures: list[TabExcerptMeasure] = Field(default_factory=list)


class CompositionToolOutput(ToolOutput):
    tool: str = "request_composition"
    intent: Literal["compose", "compose_from_reference"] = "compose"
    song: Optional[SongState] = None
    source: Optional[str] = None
    reference_transfer_intent: dict | None = None
    instrument_requests_summary: list[dict] = Field(default_factory=list)
    literal_applications: list[dict] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
