"""Tests for per-bar triad chord estimation."""

from __future__ import annotations

import numpy as np

from llm_band.infrastructure.mir.chord_features import chords_from_bar_chromas

# Pitch-class index order: C, C#, D, Eb, E, F, F#, G, Ab, A, Bb, B
C, Cs, D, Eb, E, F, Fs, G, Ab, A, Bb, B = range(12)


def _triad(*notes: int) -> np.ndarray:
    vector = np.zeros(12, dtype=float)
    for note in notes:
        vector[note] = 1.0
    return vector


def _bar_spans(count: int) -> list[tuple[int, int, float, float]]:
    return [(i + 1, i + 1, float(i * 2), float((i + 1) * 2)) for i in range(count)]


def test_four_bar_am_f_c_g_progression():
    bar_chromas = [
        _triad(A, C, E),  # Am
        _triad(F, A, C),  # F
        _triad(C, E, G),  # C
        _triad(G, B, D),  # G
    ]

    spans = chords_from_bar_chromas(bar_chromas, _bar_spans(4))

    chosen = [span.chosen.label for span in spans]
    assert chosen == ["Am", "F", "C", "G"]
    assert all(span.start_bar == i + 1 for i, span in enumerate(spans))
    assert all(span.chosen.confidence > 0.0 for span in spans)


def test_up_to_five_candidates_per_bar():
    spans = chords_from_bar_chromas([_triad(C, E, G)], _bar_spans(1))

    assert 1 <= len(spans[0].candidates) <= 5
    assert spans[0].candidates[0].label == "C"


def test_smoothing_removes_one_bar_outlier_between_matching_neighbors():
    bar_chromas = [
        _triad(F, A, C),  # F
        _triad(C, E, G),  # C  <- spurious one-bar outlier
        _triad(F, A, C),  # F
    ]

    spans = chords_from_bar_chromas(bar_chromas, _bar_spans(3))

    assert [span.chosen.label for span in spans] == ["F", "F", "F"]


def test_low_confidence_bar_has_no_chosen_chord():
    # Flat chroma: every pitch class equally present → no triad stands out.
    spans = chords_from_bar_chromas([np.ones(12, dtype=float)], _bar_spans(1))

    assert spans[0].chosen is None
    assert spans[0].confidence < 0.45


def test_diminished_triad_is_recognized():
    spans = chords_from_bar_chromas([_triad(B, D, F)], _bar_spans(1))

    assert spans[0].chosen is not None
    assert spans[0].chosen.quality == "diminished"
    assert spans[0].chosen.label == "Bdim"
