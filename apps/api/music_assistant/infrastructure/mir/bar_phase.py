"""Downbeat / bar-phase offset selection.

The tempo grid groups beats into bars starting at beat 0, but the true downbeat
can sit at beat 1, 2, or 3 of that grouping. A wrong phase makes every bar window
straddle two chords, so chords and sections come out coherent but shifted by a
fraction of a bar. This picks the bar-start offset whose bar windows give the
cleanest per-bar triad fit - the offset where chord changes land on bar lines.

The pure logic (:func:`choose_bar_phase_offset`) takes per-beat chroma vectors so
it is unit-testable without audio. :func:`select_bar_phase_offset` is the
audio-level convenience that builds beat chromas from the harmonic source.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from music_assistant.infrastructure.mir.chord_features import (
    _default_chroma_time_provider,
    _mean_chroma,
    best_triad_fit,
)
from music_assistant.infrastructure.mir.librosa_analyzer import _clamp


SAMPLE_RATE = 22_050
BEATS_PER_BAR = 4
# Maps the mean-triad-fit advantage of the best offset over the next into a 0..1
# confidence. Clean-vs-smeared bar fits differ by ~0.1-0.2, so a 4x scale puts a
# clear winner well above the apply threshold.
PHASE_CONFIDENCE_SCALE = 4.0

# (path, sample_rate) -> (chroma[12, frames], frame_times[frames])
ChromaTimeProvider = Callable[[str, int], "tuple[np.ndarray, np.ndarray]"]


def choose_bar_phase_offset(
    beat_chromas: list[np.ndarray],
    *,
    beats_per_bar: int = BEATS_PER_BAR,
) -> tuple[int, float]:
    """Return ``(offset, confidence)`` for the best bar-start beat offset."""
    if len(beat_chromas) < beats_per_bar * 2:
        return 0, 0.0

    scores = [
        _phase_score(beat_chromas, offset, beats_per_bar)
        for offset in range(beats_per_bar)
    ]
    best_offset = int(np.argmax(scores))
    best = scores[best_offset]
    rest = [score for index, score in enumerate(scores) if index != best_offset]
    second = max(rest) if rest else 0.0
    confidence = round(_clamp((best - second) * PHASE_CONFIDENCE_SCALE), 3)
    return best_offset, confidence


def select_bar_phase_offset(
    harmonic_path: str,
    beat_times: list[float],
    *,
    beats_per_bar: int = BEATS_PER_BAR,
    sample_rate: int = SAMPLE_RATE,
    chroma_time_provider: ChromaTimeProvider | None = None,
) -> tuple[int, float]:
    chromas = beat_chromas_from_audio(
        harmonic_path,
        beat_times,
        sample_rate=sample_rate,
        chroma_time_provider=chroma_time_provider,
    )
    return choose_bar_phase_offset(chromas, beats_per_bar=beats_per_bar)


def beat_chromas_from_audio(
    harmonic_path: str,
    beat_times: list[float],
    *,
    sample_rate: int = SAMPLE_RATE,
    chroma_time_provider: ChromaTimeProvider | None = None,
) -> list[np.ndarray]:
    """One mean-chroma vector per beat interval ``[beat[i], beat[i+1])``."""
    if len(beat_times) < 2:
        return []
    provider = chroma_time_provider or _default_chroma_time_provider
    chroma, frame_times = provider(harmonic_path, sample_rate)
    return [
        _mean_chroma(chroma, frame_times, beat_times[index], beat_times[index + 1])
        for index in range(len(beat_times) - 1)
    ]


def _phase_score(
    beat_chromas: list[np.ndarray], offset: int, beats_per_bar: int
) -> float:
    fits: list[float] = []
    index = offset
    while index + beats_per_bar <= len(beat_chromas):
        bar = np.mean(
            np.asarray(beat_chromas[index : index + beats_per_bar], dtype=float), axis=0
        )
        fits.append(best_triad_fit(bar))
        index += beats_per_bar
    return float(np.mean(fits)) if fits else 0.0
