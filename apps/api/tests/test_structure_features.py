"""Tests for progression and A/B/C structure detection."""

from __future__ import annotations

from llm_band.domain.audio_profile import ChordCandidate, ChordSpan
from llm_band.infrastructure.mir.structure_features import detect_structure


def _span(bar: int, label: str, confidence: float = 0.8) -> ChordSpan:
    chosen = ChordCandidate(root=label[0], quality="major", label=label, confidence=confidence)
    return ChordSpan(
        start_bar=bar,
        end_bar=bar,
        start_seconds=float((bar - 1) * 2),
        end_seconds=float(bar * 2),
        candidates=[chosen],
        chosen=chosen,
        confidence=confidence,
    )


def _phrase(start_bar: int, chords: list[str]) -> list[ChordSpan]:
    return [_span(start_bar + offset, chord) for offset, chord in enumerate(chords)]


def _repetitive_spans_with_one_tail_bar() -> list[ChordSpan]:
    spans: list[ChordSpan] = []
    for bar in range(1, 117):
        progression = ["Am", "F", "C", "G"]
        spans.append(_span(bar, progression[(bar - 1) % len(progression)]))
    spans.append(_span(117, "E"))
    return spans


def test_a_b_c_b_pattern_reuses_label_for_matching_progression():
    spans = (
        _phrase(1, ["Am", "F", "C", "G"])      # A
        + _phrase(5, ["C", "G", "Am", "F"])    # B
        + _phrase(9, ["F", "C", "G", "Am"])    # C
        + _phrase(13, ["C", "G", "Am", "F"])   # B (repeat)
    )

    structure, progressions = detect_structure(spans)

    assert [section.label for section in structure.sections] == ["A", "B", "C", "B"]
    # The repeated progression is detected once with two repetitions.
    repeated = [p for p in progressions if p.repetitions == 2]
    assert len(repeated) == 1
    assert repeated[0].chords == ["C", "G", "Am", "F"]


def test_section_boundaries_are_integer_bars():
    spans = _phrase(1, ["Am", "F", "C", "G"]) + _phrase(5, ["C", "G", "Am", "F"])

    structure, _ = detect_structure(spans)

    for section in structure.sections:
        assert isinstance(section.start_bar, int)
        assert isinstance(section.end_bar, int)
    assert structure.sections[0].start_bar == 1
    assert structure.sections[0].end_bar == 4
    assert structure.sections[1].start_bar == 5
    assert structure.sections[1].end_bar == 8


def test_consecutive_identical_phrases_merge_into_one_section():
    spans = _phrase(1, ["Am", "F", "C", "G"]) + _phrase(5, ["Am", "F", "C", "G"])

    structure, progressions = detect_structure(spans)

    assert len(structure.sections) == 1
    assert structure.sections[0].label == "A"
    assert structure.sections[0].start_bar == 1
    assert structure.sections[0].end_bar == 8
    assert progressions[0].repetitions == 2


def test_empty_input_returns_empty_structure():
    structure, progressions = detect_structure([])

    assert structure.sections == []
    assert progressions == []


def test_labels_stay_abstract():
    spans = _phrase(1, ["Am", "F", "C", "G"]) + _phrase(5, ["C", "G", "Am", "F"])

    structure, _ = detect_structure(spans)

    labels = {section.label for section in structure.sections}
    assert labels <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert not labels & {"verse", "chorus", "bridge"}


def test_rejects_one_huge_section_plus_one_bar_tail_as_low_value_structure():
    structure, progressions = detect_structure(_repetitive_spans_with_one_tail_bar())

    assert structure.confidence < 0.4
    assert len(structure.sections) == 1
    assert structure.sections[0].label == "A"
    assert structure.sections[0].start_bar == 1
    assert structure.sections[0].end_bar == 117
    assert progressions[0].chords
