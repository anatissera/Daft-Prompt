"""HTTP and SSE contracts for the FastAPI interface."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from music_assistant.application.chat_music import ChatRequest, ChatResponse
from music_assistant.domain.reference_profile import ReferenceProfile
from music_assistant.domain.song_state import Header, RosterItem, SongState

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
    "ResearchRequest",
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


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1)


AnalysisProgressType = Literal[
    "accepted",
    "searching_sources",
    "fetching_pages",
    "extracting_claims",
    "fusing_evidence",
    "research_keepalive",
]


class AnalysisProgressEvent(BaseModel):
    type: AnalysisProgressType
    message: str
    status: Literal["started", "completed"] = "started"
    elapsed_seconds: float | None = Field(default=None, ge=0.0)
    cache_hit: bool | None = None


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
