"""Contract tests for the deep harmonic reference-analysis profile."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from music_assistant.domain.audio_profile import (
    AnalysisNote,
    AudioProfile,
    ChordCandidate,
    ChordEstimate,
    ChordSpan,
    HarmonicProfile,
    KeyCandidate,
    KeyProfile,
    MeterProfile,
    ProgressionEstimate,
    ReferenceProfile,
    ReferenceSource,
    SectionProfile,
    StemProfile,
    StructuralSection,
    StructureProfile,
    TempoCandidate,
    TempoProfile,
)


def _source() -> ReferenceSource:
    return ReferenceSource(
        reference_id="ref_deep",
        kind="upload",
        label="deep harmonic fixture.wav",
        uri="/tmp/deep-harmonic-fixture.wav",
        authorized=True,
    )


def _candidate(label: str, root: str, quality: str, confidence: float) -> ChordCandidate:
    return ChordCandidate(
        root=root,
        quality=quality,
        label=label,
        confidence=confidence,
    )


def test_reference_profile_serializes_legacy_and_deep_harmonic_fields():
    chord_spans = [
        ChordSpan(
            start_bar=1,
            end_bar=2,
            start_seconds=0.0,
            end_seconds=2.0,
            candidates=[
                _candidate("Am", "A", "minor", 0.82),
                _candidate("C", "C", "major", 0.48),
            ],
            chosen=_candidate("Am", "A", "minor", 0.82),
            confidence=0.82,
        ),
        ChordSpan(
            start_bar=2,
            end_bar=3,
            start_seconds=2.0,
            end_seconds=4.0,
            candidates=[_candidate("F", "F", "major", 0.78)],
            chosen=_candidate("F", "F", "major", 0.78),
            confidence=0.78,
        ),
        ChordSpan(
            start_bar=3,
            end_bar=4,
            start_seconds=4.0,
            end_seconds=6.0,
            candidates=[_candidate("C", "C", "major", 0.8)],
            chosen=_candidate("C", "C", "major", 0.8),
            confidence=0.8,
        ),
        ChordSpan(
            start_bar=4,
            end_bar=5,
            start_seconds=6.0,
            end_seconds=8.0,
            candidates=[_candidate("G", "G", "major", 0.76)],
            chosen=_candidate("G", "G", "major", 0.76),
            confidence=0.76,
        ),
    ]
    profile = ReferenceProfile(
        reference_id="ref_deep",
        source=_source(),
        audio=AudioProfile(
            duration_seconds=48.0,
            tempo_bpm=118.0,
            tempo_confidence=0.84,
            key="A minor",
            key_confidence=0.72,
            confidence=0.74,
            overall_confidence=0.74,
            chord_estimates=[
                ChordEstimate(
                    start_seconds=0.0,
                    end_seconds=8.0,
                    chords=["Am", "F", "C", "G"],
                    confidence=0.7,
                )
            ],
            sections=[
                SectionProfile(
                    name="A",
                    start_seconds=0.0,
                    end_seconds=16.0,
                    confidence=0.72,
                    chord_estimates=[
                        ChordEstimate(
                            start_seconds=0.0,
                            end_seconds=8.0,
                            chords=["Am", "F", "C", "G"],
                            confidence=0.7,
                        )
                    ],
                )
            ],
            stems=[
                StemProfile(name="drums", role="percussion", confidence=0.9),
                StemProfile(name="bass", role="bass", confidence=0.88),
                StemProfile(name="vocals", role="vocal", confidence=0.83),
                StemProfile(name="other", role="harmony", confidence=0.86),
            ],
            tempo=TempoProfile(
                primary_bpm=118.0,
                confidence=0.84,
                candidates=[
                    TempoCandidate(bpm=118.0, confidence=0.84, relation="primary"),
                    TempoCandidate(bpm=59.0, confidence=0.42, relation="half_time"),
                    TempoCandidate(bpm=236.0, confidence=0.38, relation="double_time"),
                ],
                beat_grid_confidence=0.8,
                bar_grid_confidence=0.76,
            ),
            meter=MeterProfile(time_signature=(4, 4), source="assumed", confidence=0.5),
            harmony=HarmonicProfile(
                key=KeyProfile(
                    primary=KeyCandidate(key="A minor", mode="minor", confidence=0.72),
                    candidates=[
                        KeyCandidate(key="A minor", mode="minor", confidence=0.72),
                        KeyCandidate(key="C major", mode="major", confidence=0.67),
                    ],
                    relative_key_ambiguity=True,
                    confidence=0.72,
                ),
                chord_spans=chord_spans,
                progressions=[
                    ProgressionEstimate(
                        start_bar=1,
                        end_bar=4,
                        chords=["Am", "F", "C", "G"],
                        confidence=0.71,
                        repetitions=2,
                    ),
                    ProgressionEstimate(
                        start_bar=5,
                        end_bar=8,
                        chords=["F", "C", "G", "Am"],
                        confidence=0.6,
                    ),
                ],
                harmonic_rhythm_label="one chord per bar",
                confidence=0.7,
            ),
            structure=StructureProfile(
                sections=[
                    StructuralSection(
                        label="A",
                        start_bar=1,
                        end_bar=8,
                        start_seconds=0.0,
                        end_seconds=16.0,
                        confidence=0.72,
                        main_progression=["Am", "F", "C", "G"],
                    ),
                    StructuralSection(
                        label="B",
                        start_bar=9,
                        end_bar=16,
                        start_seconds=16.0,
                        end_seconds=32.0,
                        confidence=0.74,
                        main_progression=["F", "C", "G", "Am"],
                    ),
                    StructuralSection(
                        label="C",
                        start_bar=17,
                        end_bar=24,
                        start_seconds=32.0,
                        end_seconds=48.0,
                        confidence=0.62,
                        main_progression=["Am", "G", "F", "G"],
                    ),
                ],
                confidence=0.69,
            ),
            analysis_notes=[
                AnalysisNote(
                    code="demucs_fallback",
                    message="Stem separation was unavailable; confidence was reduced.",
                    severity="warning",
                )
            ],
        ),
        summary="Likely key: A minor, with C major as an alternative.",
    )

    payload = profile.model_dump(mode="json")

    assert payload["audio"]["tempo_bpm"] == 118.0
    assert payload["audio"]["key"] == "A minor"
    assert payload["audio"]["chord_estimates"][0]["label"] == "Probably Am - F - C - G"
    assert payload["audio"]["tempo"]["candidates"][1]["relation"] == "half_time"
    assert payload["audio"]["meter"]["time_signature"] == [4, 4]
    assert payload["audio"]["harmony"]["key"]["primary"]["key"] == "A minor"
    assert payload["audio"]["harmony"]["key"]["candidates"][1]["key"] == "C major"
    assert payload["audio"]["harmony"]["chord_spans"][0]["chosen"]["label"] == "Am"
    assert payload["audio"]["harmony"]["progressions"][0]["chords"] == ["Am", "F", "C", "G"]
    assert [section["label"] for section in payload["audio"]["structure"]["sections"]] == ["A", "B", "C"]
    assert payload["audio"]["stems"][0]["role"] == "percussion"
    assert payload["audio"]["stems"][0]["available"] is True
    assert payload["audio"]["analysis_notes"][0]["severity"] == "warning"


def test_audio_profile_keeps_legacy_minimal_defaults():
    audio = AudioProfile(duration_seconds=12.0)

    assert audio.meter.time_signature == (4, 4)
    assert audio.meter.source == "assumed"
    assert audio.analysis_notes == []
    assert audio.tempo is None
    assert audio.harmony is None
    assert audio.structure is None
    assert audio.chord_estimates == []
    assert audio.sections == []


def test_deep_harmonic_contract_rejects_unbounded_feature_payloads():
    candidate = _candidate("Am", "A", "minor", 0.7)

    with pytest.raises(ValidationError):
        ChordSpan(
            start_bar=1,
            end_bar=2,
            start_seconds=0.0,
            end_seconds=2.0,
            candidates=[candidate] * 6,
        )

    span = ChordSpan(
        start_bar=1,
        end_bar=2,
        start_seconds=0.0,
        end_seconds=2.0,
        candidates=[candidate],
    )
    with pytest.raises(ValidationError):
        HarmonicProfile(chord_spans=[span] * 513)

    section = StructuralSection(
        label="A",
        start_bar=1,
        end_bar=4,
        start_seconds=0.0,
        end_seconds=8.0,
    )
    with pytest.raises(ValidationError):
        StructureProfile(sections=[section] * 65)
