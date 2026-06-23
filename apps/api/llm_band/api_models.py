"""HTTP and SSE contracts for the FastAPI layer."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from .schema import Header, RosterItem, SongState


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


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    job_id: str
    source: Literal["director", "canned"]
    song: SongState
    artifacts: Artifacts


ComposeEvent = DirectorEvent | AgentPassEvent | ConvergenceEvent | DoneEvent


def event_payload(event: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(event, BaseModel):
        return event.model_dump(by_alias=True, mode="json")
    return event


def sse_data(event: BaseModel | dict[str, Any]) -> str:
    return f"data: {json.dumps(event_payload(event))}\n\n"
