"""Domain models for listening, research, and reference-guided composition."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, computed_field


ConfidenceLabel = Literal["low", "medium", "high"]
InstrumentFamily = Literal["drums", "bass", "guitar", "piano"]
TransferMode = Literal[
    "similar",
    "literal",
    "timbre_only",
    "pattern_only",
    "energy_only",
    "avoid_copying",
    "clarify",
]
EvidenceClaimType = Literal[
    "tempo",
    "key",
    "meter",
    "chord_progression",
    "section",
    "lyrics",
    "tab",
    "credit",
    "metadata",
    "instrumentation",
    "groove",
    "timbre",
    "trait",
    "audio_estimate",
    "other",
]
ExtractionMethod = Literal[
    "site_parser",
    "browser_rendered_page",
    "api",
    "audio_analyzer",
    "manual_fixture",
    "inference",
]


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


class TimeRange(BaseModel):
    start_seconds: Optional[float] = Field(default=None, ge=0.0)
    end_seconds: Optional[float] = Field(default=None, ge=0.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source: Optional[str] = None


class EvidenceClaim(BaseModel):
    """A source-backed musical claim, stored as evidence rather than truth."""

    claim_id: str
    claim_type: EvidenceClaimType
    value: str
    normalized_value: Optional[str] = None
    section_name: Optional[str] = None
    time_range: Optional[TimeRange] = None
    source_name: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    extraction_method: ExtractionMethod
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    snippet: str = Field(default="", max_length=280)
    notes: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def confidence_label(self) -> ConfidenceLabel:
        return confidence_label(self.confidence)


class EvidenceConflict(BaseModel):
    conflict_id: str
    claim_type: EvidenceClaimType
    description: str
    claims: list[EvidenceClaim] = Field(default_factory=list)
    resolution: Optional[str] = None


class MissingData(BaseModel):
    field: str
    reason: str
    needed_evidence: str = ""


class SongIdentity(BaseModel):
    title: str
    artist: Optional[str] = None
    album: Optional[str] = None
    year: Optional[int] = None
    version: Optional[str] = None
    candidate_matches: list[str] = Field(default_factory=list)


class SongSectionProfile(BaseModel):
    name: str
    order: int
    start_seconds: Optional[float] = Field(default=None, ge=0.0)
    end_seconds: Optional[float] = Field(default=None, ge=0.0)
    timestamp_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    timestamp_source: Optional[str] = None
    lyric_claims: list[EvidenceClaim] = Field(default_factory=list)
    chord_claims: list[EvidenceClaim] = Field(default_factory=list)
    key_claims: list[EvidenceClaim] = Field(default_factory=list)
    instrument_claims: list[EvidenceClaim] = Field(default_factory=list)
    energy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    density: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notable_instruments: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class InstrumentTrait(BaseModel):
    instrument: str
    role: str
    traits: dict[str, str] = Field(default_factory=dict)
    source_claim_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @computed_field
    @property
    def confidence_label(self) -> ConfidenceLabel:
        return confidence_label(self.confidence)


class InstrumentTimbreProfile(BaseModel):
    instrument_name: str = ""
    source_label: str = ""
    midi_program: int = Field(default=0, ge=0, le=127)
    midi_range: tuple[int, int] = (0, 127)
    technique: Optional[str] = None
    is_drum: bool = False
    playback_note: str = "General MIDI playback approximates this timbre."


class InstrumentPatternProfile(BaseModel):
    density: Literal["low", "medium", "high"] = "medium"
    subdivision: str = ""
    accent_beats: list[float] = Field(default_factory=list, max_length=16)
    contour: str = ""
    fill_frequency: str = ""
    section_variations: dict[str, str] = Field(default_factory=dict)


class ReferenceNoteSeed(BaseModel):
    bar: int = Field(ge=0)
    start_beat: float = Field(ge=0.0)
    duration_beats: float = Field(gt=0.0)
    pitch: Optional[int] = Field(default=None, ge=0, le=127)
    velocity: int = Field(default=96, ge=1, le=127)
    source_mode: Literal["songsterr", "audio", "inferred"] = "songsterr"
    section_name: Optional[str] = None


class ReferenceNotePack(BaseModel):
    pack_id: str
    instrument_family: InstrumentFamily
    section_name: str = ""
    start_bar: int = Field(default=0, ge=0)
    bar_count: int = Field(default=1, ge=1)
    notes: list[ReferenceNoteSeed] = Field(default_factory=list, max_length=128)


class ReferenceRhythmPattern(BaseModel):
    pattern_id: str
    section_name: str = ""
    density: Literal["low", "medium", "high"] = "medium"
    accent_beats: list[float] = Field(default_factory=list, max_length=16)
    durations: list[float] = Field(default_factory=list, max_length=16)
    subdivision: str = ""


class ReferencePitchPattern(BaseModel):
    pattern_id: str
    section_name: str = ""
    register: list[int] = Field(default_factory=list, max_length=2)
    pitch_classes: list[int] = Field(default_factory=list, max_length=12)
    intervals: list[int] = Field(default_factory=list, max_length=32)
    contour: str = ""


class ReferenceMotif(BaseModel):
    motif_id: str
    section_name: str = ""
    start_bar: int = Field(default=0, ge=0)
    bar_count: int = Field(default=1, ge=1)
    repetitions: int = Field(default=1, ge=1)
    rhythm_signature: str = ""
    interval_signature: str = ""


class ReferenceHarmonicContext(BaseModel):
    key: Optional[str] = None
    chord_progression: list[str] = Field(default_factory=list, max_length=32)
    roman_progression: list[str] = Field(default_factory=list, max_length=32)
    harmonic_rhythm: str = ""


class MusicalMemoryProfile(BaseModel):
    summary: str = ""
    note_packs: list[ReferenceNotePack] = Field(default_factory=list, max_length=16)
    rhythm_patterns: list[ReferenceRhythmPattern] = Field(default_factory=list, max_length=16)
    pitch_patterns: list[ReferencePitchPattern] = Field(default_factory=list, max_length=16)
    harmonic_context: ReferenceHarmonicContext = Field(default_factory=ReferenceHarmonicContext)
    motifs: list[ReferenceMotif] = Field(default_factory=list, max_length=16)


class ReferenceInstrumentProfile(BaseModel):
    source_reference_id: str
    source_profile_id: str = ""
    instrument_family: InstrumentFamily
    track_name: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    timbre: InstrumentTimbreProfile = Field(default_factory=InstrumentTimbreProfile)
    pattern: InstrumentPatternProfile = Field(default_factory=InstrumentPatternProfile)
    symbolic_seed: list[ReferenceNoteSeed] = Field(default_factory=list, max_length=64)
    musical_memory: MusicalMemoryProfile = Field(default_factory=MusicalMemoryProfile)
    evidence: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


class ReferenceTransferItem(BaseModel):
    instrument_family: InstrumentFamily
    reference_id: str
    transfer_mode: TransferMode = "similar"
    section_name: Optional[str] = None
    fidelity: float = Field(default=0.65, ge=0.0, le=1.0)
    constraints: list[str] = Field(default_factory=list)


class ReferenceTransferIntent(BaseModel):
    items: list[ReferenceTransferItem] = Field(default_factory=list)
    clarification: Optional[str] = None


class SongKnowledgeProfile(BaseModel):
    """Traceable known-song profile built from web and optional audio evidence."""

    profile_id: str
    identity: SongIdentity
    credits: dict[str, list[EvidenceClaim]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_claims: list[EvidenceClaim] = Field(default_factory=list)
    sections: list[SongSectionProfile] = Field(default_factory=list)
    traits: list[InstrumentTrait] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    missing_data: list[MissingData] = Field(default_factory=list)
    confidence_summary: dict[str, str] = Field(default_factory=dict)
    audio: Optional["AudioProfile"] = None


class CompositionBrief(BaseModel):
    """Structured contract passed from chat/profile tools into composition."""

    brief_id: str
    user_request: str
    global_constraints: dict[str, Any] = Field(default_factory=dict)
    references_used: list[str] = Field(default_factory=list)
    transfer_policy: dict[str, list[str]] = Field(default_factory=dict)
    harmonic_guidance: dict[str, Any] = Field(default_factory=dict)
    rhythmic_guidance: dict[str, Any] = Field(default_factory=dict)
    form_guidance: dict[str, Any] = Field(default_factory=dict)
    instrumentation: dict[str, Any] = Field(default_factory=dict)
    instrument_requests: dict[str, dict[str, Any]] = Field(default_factory=dict)
    timbre_traits: dict[str, Any] = Field(default_factory=dict)
    forbidden_traits: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


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


class TimbreProfile(BaseModel):
    """Compact spectral summary of one stem (deep-music-analysis Track 2).

    Labels are coarse on purpose — they feed chat chips and evidence-grounded
    answers, not a spectral display. Raw values stay bounded scalars."""

    brightness: Literal["dark", "warm", "bright"] = "warm"
    noisiness: Literal["tonal", "mixed", "noisy"] = "mixed"
    band_balance: Literal["low-heavy", "mid-heavy", "high-heavy", "balanced"] = "balanced"
    centroid_hz: Optional[float] = None
    flatness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    band_split: list[float] = Field(default_factory=list, max_length=3)
    interpretation: str = Field(default="", max_length=280)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RhythmProfile(BaseModel):
    """Groove summary of one stem (deep-music-analysis Track 5)."""

    feel: Literal["straight", "swung"] = "straight"
    swing_ratio: Optional[float] = Field(default=None, ge=0.5, le=4.0)
    syncopation: float = Field(default=0.0, ge=0.0, le=1.0)
    density: Literal["sparse", "moderate", "busy"] = "moderate"
    onsets_per_bar: Optional[float] = Field(default=None, ge=0.0)
    interpretation: str = Field(default="", max_length=280)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DynamicsPoint(BaseModel):
    bar: int
    level: float = Field(ge=0.0, le=1.0)


class DynamicsEvent(BaseModel):
    kind: Literal["build", "drop"]
    start_bar: int
    end_bar: int


class StemDynamics(BaseModel):
    """Bar-keyed loudness curve with build/drop callouts (Track 4)."""

    points: list[DynamicsPoint] = Field(default_factory=list, max_length=64)
    events: list[DynamicsEvent] = Field(default_factory=list, max_length=12)
    interpretation: str = Field(default="", max_length=280)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class MelodyEvent(BaseModel):
    """One bounded, representative event from an audio transcription.

    This deliberately carries musical timing rather than model-specific output
    arrays, so it remains useful to chat and future symbolic tools.
    """

    bar: int = Field(ge=0)
    start_beat: float = Field(ge=0.0)
    duration_beats: float = Field(gt=0.0)
    pitch: int = Field(ge=0, le=127)


class MelodyProfile(BaseModel):
    """Compact, provisional melodic evidence extracted from local audio."""

    note_count: int = Field(ge=0)
    pitch_low: Optional[int] = Field(default=None, ge=0, le=127)
    pitch_high: Optional[int] = Field(default=None, ge=0, le=127)
    contour: Literal["rising", "falling", "static", "mixed", "unknown"] = "unknown"
    representative_events: list[MelodyEvent] = Field(default_factory=list, max_length=32)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StemProfile(BaseModel):
    name: str
    artifact_uri: Optional[str] = None
    role: Literal["percussion", "bass", "vocal", "harmony", "mix", "other"] = "other"
    available: bool = True
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    timbre: Optional[TimbreProfile] = None
    rhythm: Optional[RhythmProfile] = None
    dynamics: Optional[StemDynamics] = None


class ArrangementCell(BaseModel):
    """One stem's presence within one section of the arrangement timeline."""

    stem: str
    activity: float = Field(default=0.0, ge=0.0, le=1.0)
    level: Literal["silent", "low", "medium", "high"] = "silent"


class ArrangementColumn(BaseModel):
    section: str
    start_bar: int
    end_bar: int
    cells: list[ArrangementCell] = Field(default_factory=list, max_length=8)


class EnsembleProfile(BaseModel):
    """Bar-aligned arrangement timeline (deep-music-analysis Track 6): which
    stems play in which section, how loud, and what changes between sections.
    Voice-leading stays deferred until per-stem transcription (Track 1) exists."""

    columns: list[ArrangementColumn] = Field(default_factory=list, max_length=64)
    callouts: list[str] = Field(default_factory=list, max_length=12)
    interpretation: str = Field(default="", max_length=280)
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
    mix_timbre: Optional[TimbreProfile] = None
    ensemble: Optional[EnsembleProfile] = None
    melody: Optional[MelodyProfile] = None
    analysis_notes: list[AnalysisNote] = Field(default_factory=list)


class ResearchEvidence(BaseModel):
    """One musical claim extracted from a public web page during song research."""

    url: str
    site: str
    claim_type: str
    value: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    snippet: str = Field(default="", max_length=280)


class ReferenceProfile(BaseModel):
    reference_id: str
    source: ReferenceSource
    audio: Optional[AudioProfile] = None
    summary: str = ""
    research_evidence: list[ResearchEvidence] = Field(default_factory=list)
    knowledge: Optional[SongKnowledgeProfile] = None


class ExplanationAnswer(BaseModel):
    reference_id: str
    answer: str
    evidence: list[str] = Field(default_factory=list)
