"""Domain models for future listening/reference-analysis workflows."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field


ConfidenceLabel = Literal["low", "medium", "high"]


class ReferenceSource(BaseModel):
    reference_id: str
    kind: Literal["upload", "direct_url", "youtube", "metadata", "local"]
    label: str
    uri: str
    authorized: bool = False
    permission_error: Optional[str] = None


def confidence_label(confidence: float) -> ConfidenceLabel:
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


class ChordEstimate(BaseModel):
    start_seconds: float
    end_seconds: float
    chords: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    is_probable: bool = True

    @computed_field
    @property
    def confidence_label(self) -> ConfidenceLabel:
        return confidence_label(self.confidence)

    @computed_field
    @property
    def label(self) -> str:
        progression = " - ".join(self.chords) if self.chords else "unknown chords"
        prefix = "Probably" if self.is_probable else "Estimated"
        return f"{prefix} {progression}"


class EnergyPoint(BaseModel):
    time_seconds: float
    energy: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SectionProfile(BaseModel):
    name: str
    start_seconds: float
    end_seconds: float
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    energy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    energy_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    chord_estimates: list[ChordEstimate] = Field(default_factory=list)


class StemProfile(BaseModel):
    name: str
    artifact_uri: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class AudioProfile(BaseModel):
    duration_seconds: float
    tempo_bpm: Optional[float] = None
    tempo_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    key: Optional[str] = None
    key_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    energy_curve: list[EnergyPoint] = Field(default_factory=list)
    chord_estimates: list[ChordEstimate] = Field(default_factory=list)
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
