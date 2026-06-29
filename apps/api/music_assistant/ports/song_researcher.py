"""Ports and DTOs for research-only song analysis."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from music_assistant.domain.reference_profile import ReferenceProfile


class ResearchClaim(BaseModel):
    type: str
    value: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    snippet: str = Field(default="", max_length=280)


class ResearchPage(BaseModel):
    url: str
    site: str
    title: str = ""
    claims: list[ResearchClaim] = Field(default_factory=list)


class SongResearcher(Protocol):
    def research(self, query: str) -> ReferenceProfile:
        ...
