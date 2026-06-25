"""Tests for key candidate estimation."""

from __future__ import annotations

import numpy as np

from llm_band.infrastructure.mir.key_features import (
    estimate_key,
    key_profile_from_pitch_classes,
)

# Pitch-class index order: C, C#, D, Eb, E, F, F#, G, Ab, A, Bb, B
C, Cs, D, Eb, E, F, Fs, G, Ab, A, Bb, B = range(12)


def _vector(weights: dict[int, float]) -> np.ndarray:
    vector = np.zeros(12, dtype=float)
    for index, value in weights.items():
        vector[index] = value
    return vector


def test_clear_major_triad_returns_major_key():
    # Strong C-E-G plus diatonic support → C major.
    vector = _vector({C: 1.0, E: 0.8, G: 0.9, D: 0.3, A: 0.3, F: 0.3, B: 0.2})

    profile = key_profile_from_pitch_classes(vector)

    assert profile.primary is not None
    assert profile.primary.key == "C major"
    assert profile.primary.mode == "major"
    assert profile.confidence > 0.0


def test_relative_major_minor_ambiguity_is_flagged():
    # Flat diatonic C/Am content with shared-tone emphasis → C major vs A minor.
    vector = _vector(
        {C: 0.9, D: 0.5, E: 0.8, F: 0.5, G: 0.8, A: 0.9, B: 0.5}
    )

    profile = key_profile_from_pitch_classes(vector)

    top_two = {candidate.key for candidate in profile.candidates[:2]}
    assert top_two == {"C major", "A minor"}
    assert profile.relative_key_ambiguity is True


def test_empty_pitch_classes_returns_empty_profile():
    profile = key_profile_from_pitch_classes(np.zeros(12))

    assert profile.primary is None
    assert profile.candidates == []
    assert profile.confidence == 0.0


def test_confidence_adjustment_lowers_confidence():
    vector = _vector({C: 1.0, E: 0.8, G: 0.9, D: 0.3, A: 0.3, F: 0.3, B: 0.2})

    full = key_profile_from_pitch_classes(vector)
    penalized = key_profile_from_pitch_classes(vector, confidence_adjustment=-0.2)

    assert penalized.confidence < full.confidence


def test_estimate_key_uses_injected_chroma_provider():
    vector = _vector({A: 1.0, C: 0.7, E: 0.8, D: 0.3, F: 0.3, G: 0.3, B: 0.2})

    profile = estimate_key("/fake/harmonic.wav", chroma_provider=lambda path, sr: vector)

    assert profile.primary is not None
    assert profile.primary.mode in {"major", "minor"}
