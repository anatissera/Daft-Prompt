"""Orchestration tests for the deep harmonic analyzer (fakes, no audio)."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_band.domain.audio_profile import (
    ChordCandidate,
    ChordSpan,
    KeyCandidate,
    KeyProfile,
    MeterProfile,
    ProgressionEstimate,
    ReferenceSource,
    StructuralSection,
    StructureProfile,
    TempoProfile,
)
from llm_band.infrastructure.mir.deep_harmonic_analyzer import DeepHarmonicAnalyzer
from llm_band.infrastructure.mir.harmonic_source import HarmonicSource
from llm_band.infrastructure.mir.tempo_grid import TempoGrid
from llm_band.ports.stem_separator import SeparatedStem


def _source(tmp_path: Path) -> ReferenceSource:
    audio_path = tmp_path / "loop.wav"
    audio_path.write_bytes(b"fake")
    return ReferenceSource(
        reference_id="ref_test",
        kind="upload",
        label="loop.wav",
        uri=str(audio_path),
        authorized=True,
    )


def _chord_span(bar: int, label: str) -> ChordSpan:
    chosen = ChordCandidate(root=label[0], quality="minor" if label.endswith("m") else "major", label=label, confidence=0.8)
    return ChordSpan(
        start_bar=bar,
        end_bar=bar,
        start_seconds=float((bar - 1) * 2),
        end_seconds=float(bar * 2),
        candidates=[chosen],
        chosen=chosen,
        confidence=0.8,
    )


def _full_stems() -> list[SeparatedStem]:
    return [
        SeparatedStem(name="drums", role="percussion", path="/fake/drums.wav", confidence=1.0),
        SeparatedStem(name="bass", role="bass", path="/fake/bass.wav", confidence=1.0),
        SeparatedStem(name="vocals", role="vocal", path="/fake/vocals.wav", confidence=1.0),
        SeparatedStem(name="other", role="harmony", path="/fake/other.wav", confidence=1.0),
    ]


def _analyzer(
    tmp_path: Path,
    *,
    stems=None,
    bar_grid_confidence=0.8,
    structure_confidence=0.8,
    key_confidence=0.7,
    relative_key_ambiguity=True,
    tuning_deviation=None,
    section_structure=None,
) -> DeepHarmonicAnalyzer:
    stems = stems if stems is not None else _full_stems()
    chord_spans = [
        _chord_span(1, "Am"),
        _chord_span(2, "F"),
        _chord_span(3, "C"),
        _chord_span(4, "G"),
    ]
    key_profile = KeyProfile(
        primary=KeyCandidate(key="A minor", mode="minor", confidence=key_confidence),
        candidates=[
            KeyCandidate(key="A minor", mode="minor", confidence=key_confidence),
            KeyCandidate(key="C major", mode="major", confidence=max(0.0, key_confidence - 0.04)),
            KeyCandidate(key="F major", mode="major", confidence=max(0.0, key_confidence - 0.08)),
        ],
        relative_key_ambiguity=relative_key_ambiguity,
        confidence=key_confidence,
    )
    structure = StructureProfile(
        sections=[
            StructuralSection(
                label="A",
                start_bar=1,
                end_bar=4,
                start_seconds=0.0,
                end_seconds=8.0,
                confidence=structure_confidence,
                main_progression=["Am", "F", "C", "G"],
            )
        ],
        confidence=structure_confidence,
    )
    progressions = [
        ProgressionEstimate(start_bar=1, end_bar=4, chords=["Am", "F", "C", "G"], confidence=0.8, repetitions=1)
    ]
    tempo = TempoProfile(primary_bpm=120.0, confidence=0.8, beat_grid_confidence=0.85, bar_grid_confidence=bar_grid_confidence)
    grid = TempoGrid(tempo=tempo, meter=MeterProfile(), beat_times=[0.0, 0.5, 1.0, 1.5], bar_times=[0.0, 2.0, 4.0, 6.0])

    return DeepHarmonicAnalyzer(
        output_root=tmp_path / "analysis",
        separator=_FakeSeparator(stems),
        harmonic_source_builder=lambda s, path: HarmonicSource(path=str(path), source_kind="stems_bass_other", confidence_adjustment=0.0),
        tempo_estimator=lambda mix_path, drum_path=None: grid,
        key_estimator=lambda path, confidence_adjustment=0.0: key_profile,
        chord_estimator=lambda path, bar_times, duration, **kwargs: chord_spans,
        bass_root_provider=lambda bass_path, bar_times, duration: [None for _ in bar_times],
        structure_detector=lambda spans: (structure, progressions),
        tuning_deviation_provider=(lambda path: tuning_deviation) if tuning_deviation is not None else None,
        section_detector=(lambda spans, **kwargs: section_structure) if section_structure is not None else None,
        energy_provider=lambda path, bar_times, duration: [0.5 for _ in bar_times],
        stem_activity_provider=lambda stem_paths, bar_times, duration: [
            {name: 0.5 for name in stem_paths} for _ in bar_times
        ],
        duration_provider=lambda path: 8.0,
    )


class _FakeSeparator:
    def __init__(self, stems: list[SeparatedStem]) -> None:
        self._stems = stems

    def separate(self, source: ReferenceSource) -> list[SeparatedStem]:
        return self._stems


def test_orchestrator_assembles_harmony_structure_and_compatibility_fields(tmp_path):
    profile = _analyzer(tmp_path).analyze(_source(tmp_path))

    audio = profile.audio
    assert audio is not None
    # New harmonic fields.
    assert audio.harmony is not None
    assert audio.harmony.key.primary.key == "A minor"
    assert [c.chosen.label for c in audio.harmony.chord_spans] == ["Am", "F", "C", "G"]
    assert audio.harmony.harmonic_rhythm_label != ""
    # New structure fields.
    assert audio.structure is not None
    assert [s.label for s in audio.structure.sections] == ["A"]
    # Tempo/meter.
    assert audio.tempo.primary_bpm == 120.0
    assert audio.meter.time_signature == (4, 4)
    # Legacy compatibility fields.
    assert audio.key == "A minor"
    assert audio.key_confidence == 0.7
    assert audio.chord_estimates
    assert audio.chord_estimates[0].is_probable is True
    assert "Probably" in audio.chord_estimates[0].label
    assert audio.sections and audio.sections[0].name == "A"
    # Stems mapped.
    assert {stem.name for stem in audio.stems} == {"drums", "bass", "vocals", "other"}
    # Summary is probabilistic.
    assert "probably" in profile.summary.lower()


def test_mix_fallback_adds_separation_note(tmp_path):
    mix_only = [SeparatedStem(name="mix", role="mix", path="/fake/mix.wav", confidence=0.25)]

    profile = _analyzer(tmp_path, stems=mix_only).analyze(_source(tmp_path))

    codes = {note.code for note in profile.audio.analysis_notes}
    assert "separation_unavailable" in codes


def test_weak_bar_grid_adds_note(tmp_path):
    profile = _analyzer(tmp_path, bar_grid_confidence=0.1).analyze(_source(tmp_path))

    codes = {note.code for note in profile.audio.analysis_notes}
    assert "weak_bar_grid" in codes


def test_ambiguous_key_adds_note(tmp_path):
    profile = _analyzer(tmp_path).analyze(_source(tmp_path))

    notes = profile.audio.analysis_notes
    assert any(note.code == "ambiguous_key" for note in notes)
    assert any("ambiguous" in note.message.lower() for note in notes)


def test_unclear_structure_adds_note(tmp_path):
    profile = _analyzer(tmp_path, structure_confidence=0.25).analyze(_source(tmp_path))

    notes = profile.audio.analysis_notes
    assert any(note.code == "unclear_structure" for note in notes)
    assert any("structure is unclear" in note.message.lower() for note in notes)


def test_possible_detuning_adds_a440_note_without_changing_labels(tmp_path):
    profile = _analyzer(tmp_path, tuning_deviation=0.27).analyze(_source(tmp_path))

    audio = profile.audio
    assert audio.key == "A minor"
    assert any(note.code == "possible_detuning" for note in audio.analysis_notes)
    assert any("Labels assume A=440" in note.message for note in audio.analysis_notes)


def test_summary_does_not_say_likely_key_or_structure_when_confidence_is_low(tmp_path):
    profile = _analyzer(
        tmp_path,
        key_confidence=0.44,
        relative_key_ambiguity=True,
        structure_confidence=0.25,
    ).analyze(_source(tmp_path))

    summary = profile.summary
    assert "The key is likely" not in summary
    assert "Tonal center is ambiguous" in summary
    assert "A minor" in summary
    assert "C major" in summary
    assert "Structure is approximate/unclear" in summary
    assert "The structure looks like" not in summary


def test_orchestrator_uses_approximate_section_boundaries_when_harmonic_structure_is_weak(tmp_path):
    approximate_structure = StructureProfile(
        sections=[
            StructuralSection(
                label="A",
                start_bar=1,
                end_bar=8,
                start_seconds=0.0,
                end_seconds=16.0,
                confidence=0.58,
                main_progression=["Am", "F", "C", "G"],
            ),
            StructuralSection(
                label="B",
                start_bar=9,
                end_bar=16,
                start_seconds=16.0,
                end_seconds=32.0,
                confidence=0.58,
                main_progression=["Am", "F", "C", "G"],
            ),
        ],
        confidence=0.58,
    )
    profile = _analyzer(
        tmp_path,
        structure_confidence=0.25,
        section_structure=approximate_structure,
    ).analyze(_source(tmp_path))

    assert [section.label for section in profile.audio.structure.sections] == ["A", "B"]
    assert any(note.code == "approximate_sections" for note in profile.audio.analysis_notes)


def test_orchestrator_feeds_energy_and_stem_signals_into_section_detector(tmp_path):
    captured: dict = {}

    def capturing_section_detector(spans, *, energy_by_bar=None, stem_activity_by_bar=None):
        captured["energy_by_bar"] = energy_by_bar
        captured["stem_activity_by_bar"] = stem_activity_by_bar
        return StructureProfile(
            sections=[
                StructuralSection(
                    label="A", start_bar=1, end_bar=2, start_seconds=0.0, end_seconds=4.0, confidence=0.58
                ),
                StructuralSection(
                    label="B", start_bar=3, end_bar=4, start_seconds=4.0, end_seconds=8.0, confidence=0.58
                ),
            ],
            confidence=0.58,
        )

    analyzer = _analyzer(tmp_path, structure_confidence=0.25)
    analyzer.section_detector = capturing_section_detector
    analyzer.energy_provider = lambda path, bar_times, duration: [0.2, 0.2, 0.9, 0.9]
    analyzer.stem_activity_provider = lambda stem_paths, bar_times, duration: [
        {"drums": 0.2, "bass": 0.3} for _ in bar_times
    ]

    profile = analyzer.analyze(_source(tmp_path))

    assert captured["energy_by_bar"] == [0.2, 0.2, 0.9, 0.9]
    assert captured["stem_activity_by_bar"] and "drums" in captured["stem_activity_by_bar"][0]
    assert [section.label for section in profile.audio.structure.sections] == ["A", "B"]


def test_non_local_source_is_rejected(tmp_path):
    analyzer = _analyzer(tmp_path)
    remote = ReferenceSource(
        reference_id="ref_remote",
        kind="upload",
        label="x",
        uri="https://example.com/x.wav",
        authorized=True,
    )

    with pytest.raises(ValueError, match="local audio path"):
        analyzer.analyze(remote)
