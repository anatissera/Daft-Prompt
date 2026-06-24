"""Domain models for future listening/reference-analysis workflows."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ReferenceSource(BaseModel):
    reference_id: str
    kind: Literal["upload", "direct_url", "youtube", "metadata", "local"]
    label: str
    uri: str
    authorized: bool = False
    permission_error: Optional[str] = None


class SectionProfile(BaseModel):
    name: str
    start_seconds: float
    end_seconds: float
    confidence: float = 1.0


class StemProfile(BaseModel):
    name: str
    artifact_uri: Optional[str] = None
    confidence: float = 0.0


class AudioProfile(BaseModel):
    duration_seconds: float
    tempo_bpm: Optional[float] = None
    key: Optional[str] = None
    confidence: float = 0.0
    sections: list[SectionProfile] = Field(default_factory=list)
    stems: list[StemProfile] = Field(default_factory=list)


class ReferenceProfile(BaseModel):
    reference_id: str
    source: ReferenceSource
    audio: Optional[AudioProfile] = None
    summary: str = ""


class ExplanationAnswer(BaseModel):
    reference_id: str
    answer: str
    evidence: list[str] = Field(default_factory=list)
