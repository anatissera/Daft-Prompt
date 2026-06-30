"""Tests for per-bar energy and per-stem activity summaries."""

from __future__ import annotations

import numpy as np

from music_assistant.infrastructure.mir.bar_energy import (
    bar_means_from_rms,
    per_bar_energy,
    per_stem_activity_by_bar,
)


def _ramp_rms(duration: float = 8.0, hop: float = 0.5):
    frame_times = np.arange(0.0, duration, hop)
    # Quiet first half, loud second half.
    rms = np.where(frame_times < duration / 2, 0.2, 1.0)
    return rms, frame_times


def test_bar_means_align_to_bars_and_normalize_by_peak():
    rms, frame_times = _ramp_rms()
    bar_times = [0.0, 2.0, 4.0, 6.0]

    means = bar_means_from_rms(rms, frame_times, bar_times, end_seconds=8.0)

    assert len(means) == 4
    # Peak-normalized: quiet bars ~0.2, loud bars ~1.0.
    assert means[0] == means[1] == 0.2
    assert means[2] == means[3] == 1.0


def test_empty_rms_returns_zeroed_bars():
    means = bar_means_from_rms(np.array([]), np.array([]), [0.0, 2.0], end_seconds=4.0)
    assert means == [0.0, 0.0]


def test_per_bar_energy_uses_injected_provider():
    rms, frame_times = _ramp_rms()
    provider = lambda path, sr: (rms, frame_times)

    means = per_bar_energy("ignored.wav", [0.0, 4.0], 8.0, rms_provider=provider)

    assert means == [0.2, 1.0]


def test_per_stem_activity_produces_one_dict_per_bar():
    def provider(path, sr):
        if "loud" in path:
            return np.array([1.0, 1.0]), np.array([0.0, 4.0])
        return np.array([0.3, 0.3]), np.array([0.0, 4.0])

    activity = per_stem_activity_by_bar(
        {"drums": "loud.wav", "bass": "quiet.wav"},
        [0.0, 4.0],
        8.0,
        rms_provider=provider,
    )

    assert len(activity) == 2
    assert set(activity[0]) == {"drums", "bass"}
    # Each stem is self-normalized, so a flat stem reads as its own peak (1.0).
    assert activity[0]["drums"] == 1.0
    assert activity[0]["bass"] == 1.0


def test_no_bars_returns_empty():
    assert per_bar_energy("x.wav", [], 0.0, rms_provider=lambda p, s: (np.array([1.0]), np.array([0.0]))) == []
    assert per_stem_activity_by_bar({"bass": "x.wav"}, [], 0.0) == []
    assert per_stem_activity_by_bar({}, [0.0, 4.0], 8.0) == []
