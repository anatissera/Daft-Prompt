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


class AnalysisNote(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "info"


class TempoCandidate(BaseModel):
    bpm: float
    confidence: float = Field(ge=0.0, le=1.0)
    relation: Literal["primary", "half_time", "double_time", "alternate"] = "primary"


class TempoProfile(BaseModel):
    primary_bpm: Optional[float] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    candidates: list[TempoCandidate] = Field(default_factory=list, max_length=6)
    beat_grid_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bar_grid_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class MeterProfile(BaseModel):
    time_signature: tuple[int, int] = (4, 4)
    source: Literal["assumed", "estimated"] = "assumed"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class KeyCandidate(BaseModel):
    key: str
    mode: Literal["major", "minor", "unknown"]
    confidence: float = Field(ge=0.0, le=1.0)


class KeyProfile(BaseModel):
    primary: Optional[KeyCandidate] = None
    candidates: list[KeyCandidate] = Field(default_factory=list, max_length=8)
    relative_key_ambiguity: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ChordCandidate(BaseModel):
    root: str
    quality: Literal["major", "minor", "diminished", "unknown"]
    label: str
    confidence: float = Field(ge=0.0, le=1.0)


class ChordSpan(BaseModel):
    start_bar: int
    end_bar: int
    start_beat: float = 1.0
    end_beat: float = 1.0
    start_seconds: float
    end_seconds: float
    candidates: list[ChordCandidate] = Field(default_factory=list, max_length=5)
    chosen: Optional[ChordCandidate] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ProgressionEstimate(BaseModel):
    start_bar: int
    end_bar: int
    chords: list[str] = Field(default_factory=list, max_length=16)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    repetitions: int = 1


class HarmonicProfile(BaseModel):
    key: KeyProfile = Field(default_factory=KeyProfile)
    chord_spans: list[ChordSpan] = Field(default_factory=list, max_length=512)
    progressions: list[ProgressionEstimate] = Field(default_factory=list, max_length=32)
    harmonic_rhythm_label: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StructuralSection(BaseModel):
    label: str
    start_bar: int
    end_bar: int
    start_seconds: float
    end_seconds: float
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    main_progression: list[str] = Field(default_factory=list, max_length=16)


class StructureProfile(BaseModel):
    sections: list[StructuralSection] = Field(default_factory=list, max_length=64)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StemProfile(BaseModel):
    name: str
    artifact_uri: Optional[str] = None
    role: Literal["percussion", "bass", "vocal", "harmony", "mix", "other"] = "other"
    available: bool = True
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
    tempo: Optional[TempoProfile] = None
    meter: MeterProfile = Field(default_factory=MeterProfile)
    harmony: Optional[HarmonicProfile] = None
    structure: Optional[StructureProfile] = None
    analysis_notes: list[AnalysisNote] = Field(default_factory=list)


class ReferenceProfile(BaseModel):
    reference_id: str
    source: ReferenceSource
    audio: Optional[AudioProfile] = None
    summary: str = ""


class ExplanationAnswer(BaseModel):
    reference_id: str
    answer: str
    evidence: list[str] = Field(default_factory=list)
