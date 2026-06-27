"""Tests for downbeat / bar-phase offset selection."""

from __future__ import annotations

import numpy as np

from llm_band.infrastructure.mir.bar_phase import (
    beat_chromas_from_audio,
    choose_bar_phase_offset,
    select_bar_phase_offset,
)

# Pitch-class index order: C, C#, D, Eb, E, F, F#, G, Ab, A, Bb, B
C, Cs, D, Eb, E, F, Fs, G, Ab, A, Bb, B = range(12)


def _triad(*notes: int) -> np.ndarray:
    vector = np.zeros(12, dtype=float)
    for note in notes:
        vector[note] = 1.0
    return vector


_AM = _triad(A, C, E)
_F = _triad(F, A, C)
_C = _triad(C, E, G)
_G = _triad(G, B, D)


def test_recovers_downbeat_offset_by_one_beat():
    # Chords change on a downbeat that sits at beat index 1, not 0. The first beat
    # is an anacrusis (G); bars Am / F / C / G then start at offsets 1, 5, 9, 13.
    beats = [_G] + [_AM] * 4 + [_F] * 4 + [_C] * 4 + [_G] * 4

    offset, confidence = choose_bar_phase_offset(beats)

    assert offset == 1
    assert confidence > 0.0


def test_already_aligned_grid_keeps_offset_zero():
    beats = [_AM] * 4 + [_F] * 4 + [_C] * 4 + [_G] * 4

    offset, confidence = choose_bar_phase_offset(beats)

    assert offset == 0
    assert confidence > 0.0


def test_held_chord_is_ambiguous_and_keeps_offset_zero_with_low_confidence():
    beats = [_AM] * 16

    offset, confidence = choose_bar_phase_offset(beats)

    assert offset == 0
    assert confidence == 0.0


def test_too_few_beats_returns_zero():
    assert choose_bar_phase_offset([_AM, _F, _C]) == (0, 0.0)


def test_beat_chromas_align_to_beat_intervals():
    chroma = np.zeros((12, 4), dtype=float)
    chroma[A, 0] = 1.0
    chroma[F, 1] = 1.0
    chroma[C, 2] = 1.0
    chroma[G, 3] = 1.0
    frame_times = np.array([0.0, 1.0, 2.0, 3.0])

    chromas = beat_chromas_from_audio(
        "h.wav", [0.0, 1.0, 2.0, 3.0], chroma_time_provider=lambda path, sr: (chroma, frame_times)
    )

    # One chroma per gap between consecutive beats (3 gaps for 4 beats).
    assert len(chromas) == 3
    assert int(np.argmax(chromas[0])) == A
    assert int(np.argmax(chromas[1])) == F


def test_select_bar_phase_offset_uses_injected_chroma():
    # Build a per-frame chroma whose beat intervals reproduce the offset-1 pattern.
    pattern = [_G] + [_AM] * 4 + [_F] * 4 + [_C] * 4 + [_G] * 4
    frames = np.stack(pattern, axis=1)  # shape (12, 17)
    frame_times = np.arange(len(pattern), dtype=float)
    beat_times = [float(i) for i in range(len(pattern) + 1)]

    offset, confidence = select_bar_phase_offset(
        "h.wav",
        beat_times,
        chroma_time_provider=lambda path, sr: (frames, frame_times),
    )

    assert offset == 1
    assert confidence > 0.0
