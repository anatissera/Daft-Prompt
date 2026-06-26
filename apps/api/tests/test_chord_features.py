"""Tests for per-bar triad chord estimation."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np

from llm_band.domain.audio_profile import ChordCandidate, ChordSpan
from llm_band.infrastructure.mir.chord_features import (
    _default_chroma_time_provider,
    apply_key_context,
    chords_from_bar_chromas,
)

# Pitch-class index order: C, C#, D, Eb, E, F, F#, G, Ab, A, Bb, B
C, Cs, D, Eb, E, F, Fs, G, Ab, A, Bb, B = range(12)


def _triad(*notes: int) -> np.ndarray:
    vector = np.zeros(12, dtype=float)
    for note in notes:
        vector[note] = 1.0
    return vector


def _bar_spans(count: int) -> list[tuple[int, int, float, float]]:
    return [(i + 1, i + 1, float(i * 2), float((i + 1) * 2)) for i in range(count)]


def _chosen_span(bar: int, label: str, confidence: float) -> ChordSpan:
    root = label.rstrip("mdim")
    quality = "minor" if label.endswith("m") else "diminished" if label.endswith("dim") else "major"
    chosen = ChordCandidate(root=root, quality=quality, label=label, confidence=confidence)
    return ChordSpan(
        start_bar=bar,
        end_bar=bar,
        start_seconds=float((bar - 1) * 2),
        end_seconds=float(bar * 2),
        candidates=[chosen],
        chosen=chosen,
        confidence=confidence,
    )


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


def test_key_context_boosts_diatonic_chords_without_forcing_them():
    spans = chords_from_bar_chromas(
        [
            _triad(F, Ab, C),  # Fm
            _triad(Cs, F, Ab),  # Db
            _triad(Ab, C, Eb),  # Ab
            _triad(Eb, G, Bb),  # Eb
        ],
        _bar_spans(4),
    )

    adjusted = apply_key_context(spans, key_label="F minor")

    assert [span.chosen.label for span in adjusted] == ["Fm", "Db", "Ab", "Eb"]
    assert adjusted[0].confidence >= spans[0].confidence


def test_key_context_does_not_replace_isolated_non_diatonic_chord():
    spans = [
        _chosen_span(1, "Fm", 0.8),
        _chosen_span(2, "B", 0.42),
        _chosen_span(3, "Ab", 0.8),
    ]

    adjusted = apply_key_context(spans, key_label="F minor")

    assert adjusted[1].chosen is not None
    assert adjusted[1].chosen.label == "B"
    assert adjusted[1].confidence < spans[1].confidence


def test_default_chroma_time_provider_labels_against_a440_without_relabeling_for_tuning(monkeypatch):
    calls = {}

    fake_librosa = SimpleNamespace(
        load=lambda path, sr, mono: (np.ones(1024), sr),
        estimate_tuning=lambda y, sr: -0.28,
        feature=SimpleNamespace(
            chroma_cqt=lambda y, sr, hop_length, tuning: calls.setdefault("tuning", tuning)
            or np.ones((12, 3))
        ),
        frames_to_time=lambda frames, sr, hop_length: np.asarray(frames, dtype=float),
    )
    monkeypatch.setitem(sys.modules, "librosa", fake_librosa)
    monkeypatch.setattr(
        "llm_band.infrastructure.mir.librosa_analyzer._prepare_librosa_import",
        lambda: None,
    )

    chroma, frame_times = _default_chroma_time_provider("/fake/harmonic.wav", 22_050)

    assert calls["tuning"] == 0.0
    assert chroma.shape == (12, 3)
    assert frame_times.tolist() == [0.0, 1.0, 2.0]
