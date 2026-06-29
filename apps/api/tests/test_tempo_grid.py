"""Tests for tempo, beat grid, and assumed 4/4 bar grid."""

from __future__ import annotations

import numpy as np
import pytest

from llm_band.infrastructure.mir.tempo_grid import estimate_tempo_grid


def _stable_tracker(bpm: float, beats: int):
    interval = 60.0 / bpm
    beat_times = [round(i * interval, 6) for i in range(beats)]

    seen: dict[str, str] = {}

    def tracker(path: str, sample_rate: int):
        seen["path"] = path
        return bpm, beat_times

    return tracker, seen


def test_stable_beats_produce_primary_half_double_and_bars():
    tracker, _ = _stable_tracker(120.0, beats=16)

    grid = estimate_tempo_grid("/fake/mix.wav", beat_tracker=tracker)

    assert grid.tempo.primary_bpm == pytest.approx(120.0)
    relations = {c.relation: c.bpm for c in grid.tempo.candidates}
    assert relations["primary"] == pytest.approx(120.0)
    assert relations["half_time"] == pytest.approx(60.0)
    assert relations["double_time"] == pytest.approx(240.0)
    # 16 beats / 4 = 4 bars.
    assert len(grid.bar_times) == 4
    assert grid.beats_per_bar == 4
    assert grid.tempo.beat_grid_confidence > 0.0
    assert grid.tempo.bar_grid_confidence > 0.0
    assert grid.meter.time_signature == (4, 4)
    assert grid.meter.source == "assumed"


def test_tempo_profile_includes_half_and_double_time_candidates():
    tracker, _ = _stable_tracker(86.0, beats=16)

    grid = estimate_tempo_grid("/fake/mix.wav", beat_tracker=tracker)

    relations = {candidate.relation for candidate in grid.tempo.candidates}
    assert {"primary", "half_time", "double_time"} <= relations


def test_bars_span_four_beats_each():
    tracker, _ = _stable_tracker(100.0, beats=12)

    grid = estimate_tempo_grid("/fake/mix.wav", beat_tracker=tracker)

    assert len(grid.bar_times) == 3
    # Each bar start is four beats after the previous one.
    interval = 60.0 / 100.0
    np.testing.assert_allclose(
        np.diff(grid.bar_times), [4 * interval, 4 * interval], rtol=1e-4
    )


def test_drum_path_is_preferred_for_beat_tracking():
    tracker, seen = _stable_tracker(128.0, beats=8)

    estimate_tempo_grid("/fake/mix.wav", drum_path="/fake/drums.wav", beat_tracker=tracker)

    assert seen["path"] == "/fake/drums.wav"


def test_no_beats_degrades_gracefully():
    def empty_tracker(path: str, sample_rate: int):
        return 0.0, []

    grid = estimate_tempo_grid("/fake/mix.wav", beat_tracker=empty_tracker)

    assert grid.tempo.primary_bpm is None
    assert grid.tempo.confidence == 0.0
    assert grid.tempo.candidates == []


def test_real_click_track_detects_expected_tempo(tmp_path):
    librosa = pytest.importorskip("librosa")
    import soundfile as sf

    sample_rate = 22_050
    bpm = 120.0
    duration = 6.0
    beat_times = np.arange(0.0, duration, 60.0 / bpm)
    click = librosa.clicks(times=beat_times, sr=sample_rate, length=int(sample_rate * duration))
    audio_path = tmp_path / "click.wav"
    sf.write(audio_path, click, sample_rate)

    grid = estimate_tempo_grid(str(audio_path))

    assert grid.tempo.primary_bpm is not None
    # Tempo detection may land on a metrically-related multiple; accept the family.
    assert grid.tempo.primary_bpm == pytest.approx(120.0, rel=0.08) or any(
        c.bpm == pytest.approx(120.0, rel=0.08) for c in grid.tempo.candidates
    )
