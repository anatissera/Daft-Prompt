"""Pure tests for multimodal, bar-aligned section detection."""

from __future__ import annotations

import numpy as np

from music_assistant.domain.reference_profile import ChordCandidate, ChordSpan
from music_assistant.infrastructure.mir.multimodal_features import (
    MultimodalBarFeatures,
    extract_multimodal_features,
    robust_normalize,
)
from music_assistant.infrastructure.mir.section_features import (
    _merge_adjacent_sections,
    detect_multimodal_sections,
)


def _span(bar: int, label: str = "Am") -> ChordSpan:
    candidate = ChordCandidate(
        root=label.rstrip("m"),
        quality="minor" if label.endswith("m") else "major",
        label=label,
        confidence=0.75,
    )
    return ChordSpan(
        start_bar=bar,
        end_bar=bar,
        start_seconds=float((bar - 1) * 2),
        end_seconds=float(bar * 2),
        candidates=[candidate],
        chosen=candidate,
        confidence=0.75,
    )


def _features(
    vocals: list[list[float]] | None = None,
    drums: list[list[float]] | None = None,
    bass: list[list[float]] | None = None,
    other: list[list[float]] | None = None,
) -> MultimodalBarFeatures:
    return MultimodalBarFeatures(
        by_stem={
            name: [np.asarray(vector, dtype=float) for vector in values]
            for name, values in {
                "vocals": vocals,
                "drums": drums,
                "bass": bass,
                "other": other,
            }.items()
            if values is not None
        }
    )


def test_sustained_vocal_and_drum_change_creates_boundary_with_bar_and_seconds():
    spans = [_span(bar) for bar in range(1, 17)]
    quiet = [[0.1, 0.1, 0.1]] * 8
    loud = [[0.9, 0.9, 0.9]] * 8

    structure = detect_multimodal_sections(
        spans,
        _features(vocals=loud + quiet, drums=quiet + loud),
        window_bars=4,
        min_section_bars=4,
    )

    assert [(section.start_bar, section.end_bar) for section in structure.sections] == [
        (1, 8),
        (9, 16),
    ]
    assert [section.label for section in structure.sections] == ["A", "B"]
    assert structure.sections[1].start_seconds == 16.0


def test_default_multimodal_detection_ignores_four_bar_fragments():
    spans = [_span(bar) for bar in range(1, 17)]
    quiet = [[0.1, 0.1, 0.1]] * 4
    loud = [[0.9, 0.9, 0.9]] * 4

    structure = detect_multimodal_sections(
        spans,
        _features(
            vocals=quiet + loud + quiet + loud,
            drums=quiet + loud + quiet + loud,
        ),
    )

    assert [(section.start_bar, section.end_bar) for section in structure.sections] == [
        (1, 16),
    ]
    assert structure.confidence < 0.4


def test_default_multimodal_detection_keeps_strong_eight_bar_sections():
    spans = [_span(bar) for bar in range(1, 33)]
    quiet = [[0.1, 0.1, 0.1]] * 8
    loud = [[0.9, 0.9, 0.9]] * 8

    structure = detect_multimodal_sections(
        spans,
        _features(vocals=quiet + loud + quiet + loud, drums=quiet + loud + quiet + loud),
    )

    assert [(section.label, section.start_bar, section.end_bar) for section in structure.sections] == [
        ("A", 1, 8),
        ("B", 9, 16),
        ("A", 17, 24),
        ("B", 25, 32),
    ]


def test_single_moderate_stem_change_is_not_enough_for_default_boundary():
    spans = [_span(bar) for bar in range(1, 17)]
    other = [[0.2, 0.2]] * 8 + [[0.5, 0.5]] * 8

    structure = detect_multimodal_sections(spans, _features(other=other))

    assert [(section.start_bar, section.end_bar) for section in structure.sections] == [
        (1, 16),
    ]


def test_single_bar_drum_fill_does_not_create_section():
    spans = [_span(bar) for bar in range(1, 17)]
    drums = [[0.2, 0.2, 0.2] for _ in spans]
    drums[7] = [1.0, 1.0, 1.0]

    structure = detect_multimodal_sections(
        spans,
        _features(drums=drums),
        window_bars=4,
        min_section_bars=4,
    )

    assert len(structure.sections) == 1
    assert structure.sections[0].confidence < 0.4


def test_matching_section_signatures_reuse_label():
    spans = [_span(bar) for bar in range(1, 25)]
    section_a = [[0.15, 0.2, 0.1]] * 8
    section_b = [[0.9, 0.8, 0.85]] * 8

    structure = detect_multimodal_sections(
        spans,
        _features(
            vocals=section_a + section_b + section_a,
            drums=section_a + section_b + section_a,
        ),
        window_bars=4,
        min_section_bars=4,
    )

    assert [section.label for section in structure.sections] == ["A", "B", "A"]


def test_adjacent_segments_with_same_signature_are_merged():
    spans = [_span(bar) for bar in range(1, 25)]
    features = [[0.1, 0.1]] * 8 + [[0.7, 0.7]] * 8 + [[0.9, 0.9]] * 8

    structure = detect_multimodal_sections(
        spans,
        _features(drums=features),
        window_bars=4,
        min_section_bars=4,
    )

    assert [(section.label, section.start_bar, section.end_bar) for section in structure.sections] == [
        ("A", 1, 8),
        ("B", 9, 24),
    ]


def test_adjacent_equal_labels_are_collapsed_after_similarity_grouping():
    from music_assistant.domain.reference_profile import StructuralSection

    sections = [
        StructuralSection(label="A", start_bar=1, end_bar=8, start_seconds=0, end_seconds=16, confidence=0.6),
        StructuralSection(label="B", start_bar=9, end_bar=16, start_seconds=16, end_seconds=32, confidence=0.7),
        StructuralSection(label="B", start_bar=17, end_bar=24, start_seconds=32, end_seconds=48, confidence=0.5),
    ]

    merged = _merge_adjacent_sections(sections)

    assert [(section.label, section.start_bar, section.end_bar) for section in merged] == [
        ("A", 1, 8),
        ("B", 9, 24),
    ]
    assert merged[1].end_seconds == 48


def test_missing_modalities_redistribute_weights():
    spans = [_span(bar) for bar in range(1, 17)]
    other = [[0.1, 0.1]] * 8 + [[0.9, 0.9]] * 8

    structure = detect_multimodal_sections(
        spans,
        _features(other=other),
        window_bars=4,
        min_section_bars=4,
    )

    assert len(structure.sections) == 2


def test_sustained_moderate_single_stem_change_is_rejected_as_weak_evidence():
    spans = [_span(bar) for bar in range(1, 17)]
    other = [[0.2, 0.2]] * 8 + [[0.5, 0.5]] * 8

    structure = detect_multimodal_sections(
        spans,
        _features(other=other),
        window_bars=4,
        min_section_bars=4,
    )

    assert [(section.start_bar, section.end_bar) for section in structure.sections] == [(1, 16)]


def test_harmonic_change_contributes_independent_boundary_evidence():
    spans = [
        _span(bar, "Am" if bar <= 8 else "C")
        for bar in range(1, 17)
    ]
    constant_other = [[0.4, 0.4] for _ in spans]

    structure = detect_multimodal_sections(
        spans,
        _features(other=constant_other),
        window_bars=4,
        min_section_bars=4,
    )

    assert [(section.start_bar, section.end_bar) for section in structure.sections] == [
        (1, 8),
        (9, 16),
    ]
    assert [section.label for section in structure.sections] == ["A", "B"]


def test_feature_extraction_keeps_one_normalized_vector_per_bar_and_stem():
    def provider(name, path, bar_times, end_seconds):
        assert path.endswith(f"{name}.wav")
        return [
            np.asarray([float(index), float(index * 2)])
            for index in range(len(bar_times))
        ]

    features = extract_multimodal_features(
        {
            "vocals": "/tmp/vocals.wav",
            "drums": "/tmp/drums.wav",
        },
        [0.0, 2.0, 4.0],
        6.0,
        stem_vector_provider=provider,
    )

    assert set(features.by_stem) == {"vocals", "drums"}
    assert features.bar_count == 3
    assert np.allclose(features.by_stem["vocals"][0], [0.0, 0.0])
    assert np.allclose(features.by_stem["vocals"][-1], [1.0, 1.0])


def test_robust_normalization_keeps_constant_features_finite():
    normalized = robust_normalize(
        [np.asarray([0.5, 2.0]), np.asarray([0.5, 4.0])]
    )

    assert all(np.all(np.isfinite(vector)) for vector in normalized)
