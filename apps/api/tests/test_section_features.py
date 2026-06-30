"""Tests for approximate section boundaries from bar-aligned novelty signals."""

from __future__ import annotations

from music_assistant.domain.audio_profile import ChordCandidate, ChordSpan
from music_assistant.infrastructure.mir.section_features import detect_sections_from_bar_signals


def _span(bar: int, label: str = "Am", confidence: float = 0.7) -> ChordSpan:
    chosen = ChordCandidate(root=label[0], quality="minor" if label.endswith("m") else "major", label=label, confidence=confidence)
    return ChordSpan(
        start_bar=bar,
        end_bar=bar,
        start_seconds=float((bar - 1) * 2),
        end_seconds=float(bar * 2),
        candidates=[chosen],
        chosen=chosen,
        confidence=confidence,
    )


def test_energy_novelty_splits_repetitive_harmony_into_approximate_sections():
    spans = [_span(bar, ["Am", "F", "C", "G"][(bar - 1) % 4]) for bar in range(1, 33)]
    energy_by_bar = [0.25] * 16 + [0.82] * 8 + [0.45] * 8

    structure = detect_sections_from_bar_signals(
        spans,
        energy_by_bar=energy_by_bar,
        min_section_bars=8,
    )

    assert [section.label for section in structure.sections] == ["A", "B", "C"]
    assert [(section.start_bar, section.end_bar) for section in structure.sections] == [
        (1, 16),
        (17, 24),
        (25, 32),
    ]
    assert structure.confidence >= 0.5


def test_stem_activity_novelty_can_split_when_chords_repeat():
    spans = [_span(bar, ["Am", "F", "C", "G"][(bar - 1) % 4]) for bar in range(1, 25)]
    stem_activity_by_bar = [
        {"drums": 0.2, "bass": 0.35, "other": 0.4} for _ in range(8)
    ] + [
        {"drums": 0.85, "bass": 0.7, "other": 0.75} for _ in range(8)
    ] + [
        {"drums": 0.4, "bass": 0.3, "other": 0.25} for _ in range(8)
    ]

    structure = detect_sections_from_bar_signals(
        spans,
        stem_activity_by_bar=stem_activity_by_bar,
        min_section_bars=8,
    )

    assert [(section.start_bar, section.end_bar) for section in structure.sections] == [
        (1, 8),
        (9, 16),
        (17, 24),
    ]


def test_low_evidence_returns_single_uncertain_a_section():
    spans = [_span(bar) for bar in range(1, 17)]

    structure = detect_sections_from_bar_signals(spans, energy_by_bar=[0.5] * 16)

    assert len(structure.sections) == 1
    assert structure.sections[0].label == "A"
    assert structure.sections[0].start_bar == 1
    assert structure.sections[0].end_bar == 16
    assert structure.confidence < 0.4
