"""Tempo, beat grid, and an assumed 4/4 bar grid.

Produces a renderable :class:`TempoProfile` and :class:`MeterProfile` plus the
raw beat/bar times that later stages (chords per bar, structure) need. The bar
grid assumes 4/4 for the first version. Beats are tracked from the drum stem
when available (cleaner onsets) and otherwise from the mix.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from music_assistant.domain.reference_profile import MeterProfile, TempoCandidate, TempoProfile


SAMPLE_RATE = 22_050
BEATS_PER_BAR = 4

# (path, sample_rate) -> (tempo_bpm, beat_times_seconds)
BeatTracker = Callable[[str, int], "tuple[float, list[float]]"]


@dataclass
class TempoGrid:
    """Internal analysis scaffolding (not part of ``ReferenceProfile``)."""

    tempo: TempoProfile
    meter: MeterProfile
    beat_times: list[float] = field(default_factory=list)
    bar_times: list[float] = field(default_factory=list)
    beats_per_bar: int = BEATS_PER_BAR


def estimate_tempo_grid(
    mix_path: str,
    *,
    drum_path: str | None = None,
    sample_rate: int = SAMPLE_RATE,
    beat_tracker: BeatTracker | None = None,
) -> TempoGrid:
    track = beat_tracker or _default_beat_tracker
    # Drums give cleaner beat onsets; prefer them when separated.
    beat_input = drum_path or mix_path
    tempo_bpm, beat_times = track(beat_input, sample_rate)
    beat_times = sorted(float(t) for t in beat_times)

    if tempo_bpm <= 0.0 or len(beat_times) < 2:
        return TempoGrid(
            tempo=TempoProfile(primary_bpm=None, confidence=0.0),
            meter=_assumed_meter(),
            beat_times=beat_times,
            bar_times=beat_times[:1],
        )

    beat_confidence = _beat_stability(beat_times)
    bar_times = beat_times[::BEATS_PER_BAR]
    has_full_bar = len(beat_times) >= BEATS_PER_BAR
    bar_confidence = beat_confidence * 0.9 if has_full_bar else beat_confidence * 0.4

    tempo = TempoProfile(
        primary_bpm=round(float(tempo_bpm), 2),
        confidence=beat_confidence,
        candidates=[
            TempoCandidate(bpm=round(float(tempo_bpm), 2), confidence=beat_confidence, relation="primary"),
            TempoCandidate(bpm=round(float(tempo_bpm) / 2.0, 2), confidence=beat_confidence * 0.5, relation="half_time"),
            TempoCandidate(bpm=round(float(tempo_bpm) * 2.0, 2), confidence=beat_confidence * 0.5, relation="double_time"),
        ],
        beat_grid_confidence=beat_confidence,
        bar_grid_confidence=bar_confidence,
    )
    return TempoGrid(
        tempo=tempo,
        meter=_assumed_meter(),
        beat_times=beat_times,
        bar_times=bar_times,
    )


def _assumed_meter() -> MeterProfile:
    return MeterProfile(time_signature=(4, 4), source="assumed", confidence=0.5)


def _beat_stability(beat_times: list[float]) -> float:
    intervals = np.diff(np.asarray(beat_times, dtype=float))
    if intervals.size == 0:
        return 0.0
    mean = float(np.mean(intervals))
    if mean <= 0.0:
        return 0.0
    variation = float(np.std(intervals) / mean)
    return max(0.0, min(1.0, 1.0 - variation))


def _default_beat_tracker(path: str, sample_rate: int) -> tuple[float, list[float]]:
    from music_assistant.infrastructure.mir.librosa_analyzer import _prepare_librosa_import

    _prepare_librosa_import()
    import librosa

    samples, sr = librosa.load(path, sr=sample_rate, mono=True)
    tempo, beats = librosa.beat.beat_track(y=samples, sr=sr, units="time")
    tempo_value = float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else 0.0
    return tempo_value, [float(beat) for beat in beats]
