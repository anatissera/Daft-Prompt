"""HTTP and SSE contracts for the FastAPI interface."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from llm_band.application.chat_music import ChatRequest, ChatResponse
from llm_band.domain.audio_profile import ReferenceProfile
from llm_band.domain.song_state import Header, RosterItem, SongState

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "ComposeRequest",
    "ComposeResponse",
    "Artifacts",
    "DirectorEvent",
    "AgentPassEvent",
    "ConvergenceEvent",
    "ErrorEvent",
    "DoneEvent",
    "ComposeEvent",
    "AnalysisProgressEvent",
    "AnalysisDoneEvent",
    "AnalysisErrorEvent",
    "AnalysisEvent",
    "event_payload",
    "sse_data",
]


class ComposeRequest(BaseModel):
    style: str = "demo"


class Artifacts(BaseModel):
    midi: str
    musicxml: str


class ComposeResponse(BaseModel):
    job_id: str
    source: Literal["director", "canned"]
    song: SongState
    artifacts: Artifacts


class DirectorEvent(BaseModel):
    type: Literal["director"] = "director"
    source: Literal["director", "canned"]
    header: Header
    roster: list[RosterItem] = Field(default_factory=list)


class AgentPassEvent(BaseModel):
    type: Literal["agent_pass"] = "agent_pass"
    round: int
    instrument_id: str
    notes_summary: str
    new_requests: list[dict[str, Any]] = Field(default_factory=list)
    resolved_requests: list[dict[str, Any]] = Field(default_factory=list)


class ConvergenceEvent(BaseModel):
    type: Literal["convergence"] = "convergence"
    round: int
    converged: bool
    resolved_requests: list[dict[str, Any]] = Field(default_factory=list)


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    provider: str | None = None
    model: str | None = None
    partial: bool = False


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    job_id: str
    source: Literal["director", "canned"]
    song: SongState
    artifacts: Artifacts


ComposeEvent = DirectorEvent | AgentPassEvent | ConvergenceEvent | ErrorEvent | DoneEvent


AnalysisProgressType = Literal[
    "accepted",
    "separating_stems",
    "building_harmonic_source",
    "estimating_tempo_grid",
    "estimating_key",
    "estimating_chords",
    "detecting_structure",
    "analysis_keepalive",
]


class AnalysisProgressEvent(BaseModel):
    type: AnalysisProgressType
    message: str


class AnalysisDoneEvent(BaseModel):
    type: Literal["done"] = "done"
    message: str = "Analysis ready."
    profile: ReferenceProfile


class AnalysisErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


AnalysisEvent = AnalysisProgressEvent | AnalysisDoneEvent | AnalysisErrorEvent


def event_payload(event: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(event, BaseModel):
        return event.model_dump(by_alias=True, mode="json")
    return event


def sse_data(event: BaseModel | dict[str, Any]) -> str:
    return f"data: {json.dumps(event_payload(event))}\n\n"
