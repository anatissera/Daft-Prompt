"""Port for source-specific known-song research connectors."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from music_assistant.domain.audio_profile import EvidenceClaim


FetchStatus = Literal[
    "fetched",
    "blocked",
    "empty",
    "js_rendered",
    "unsupported",
    "error",
]


class ResolvedSongQuery(BaseModel):
    title: str
    artist: str | None = None
    album: str | None = None
    year: int | None = None
    version: str | None = None
    source_url: str | None = None


class ConnectorFailure(BaseModel):
    source_name: str
    url: str | None = None
    status: FetchStatus
    reason: str


class ConnectorResult(BaseModel):
    source_name: str
    query: ResolvedSongQuery
    fetch_status: FetchStatus
    claims: list[EvidenceClaim] = Field(default_factory=list)
    failures: list[ConnectorFailure] = Field(default_factory=list)


class SongSourceConnector(Protocol):
    source_name: str

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        ...
