"""Triad chord estimation per bar.

Scores each bar's chroma against major/minor/diminished triad templates, keeps
up to five candidates, and only commits a ``chosen`` chord when confidence clears
a conservative threshold. A light smoothing pass corrects a single-bar outlier
sitting between two identical, confident neighbours.

The pure logic (:func:`chords_from_bar_chromas`) takes per-bar chroma vectors so
it can be unit-tested without audio. :func:`estimate_chords` is the audio-level
convenience that slices a chroma matrix along the bar grid.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from llm_band.domain.audio_profile import ChordCandidate, ChordSpan
from llm_band.infrastructure.mir.librosa_analyzer import (
    NOTE_NAMES,
    _clamp,
    _cosine_similarity,
)


SAMPLE_RATE = 22_050
CHOSEN_THRESHOLD = 0.45
SMOOTHING_STRONG_THRESHOLD = 0.55
MAX_CANDIDATES = 5

# (start_bar, end_bar, start_seconds, end_seconds)
BarSpan = "tuple[int, int, float, float]"

TRIAD_INTERVALS: dict[str, tuple[int, int, int]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "diminished": (0, 3, 6),
}

# (path, sample_rate) -> (chroma[12, frames], frame_times[frames])
ChromaTimeProvider = Callable[[str, int], "tuple[np.ndarray, np.ndarray]"]


def chords_from_bar_chromas(
    bar_chromas: list[np.ndarray],
    bar_spans: list[tuple[int, int, float, float]],
    *,
    confidence_threshold: float = CHOSEN_THRESHOLD,
) -> list[ChordSpan]:
    spans: list[ChordSpan] = []
    for chroma, (start_bar, end_bar, start_seconds, end_seconds) in zip(bar_chromas, bar_spans):
        candidates, confidence = _score_bar(np.asarray(chroma, dtype=float))
        chosen = candidates[0] if candidates and confidence >= confidence_threshold else None
        spans.append(
            ChordSpan(
                start_bar=start_bar,
                end_bar=end_bar,
                start_beat=1.0,
                end_beat=5.0,
                start_seconds=round(float(start_seconds), 3),
                end_seconds=round(float(end_seconds), 3),
                candidates=candidates,
                chosen=chosen,
                confidence=confidence,
            )
        )
    return _smooth(spans)


def estimate_chords(
    harmonic_path: str,
    bar_times: list[float],
    end_seconds: float,
    *,
    sample_rate: int = SAMPLE_RATE,
    confidence_threshold: float = CHOSEN_THRESHOLD,
    chroma_time_provider: ChromaTimeProvider | None = None,
) -> list[ChordSpan]:
    if len(bar_times) < 1:
        return []
    provider = chroma_time_provider or _default_chroma_time_provider
    chroma, frame_times = provider(harmonic_path, sample_rate)
    bar_spans = _bar_spans_from_times(bar_times, end_seconds)
    bar_chromas = [_mean_chroma(chroma, frame_times, start, end) for _, _, start, end in bar_spans]
    return chords_from_bar_chromas(
        bar_chromas, bar_spans, confidence_threshold=confidence_threshold
    )


def _bar_spans_from_times(
    bar_times: list[float], end_seconds: float
) -> list[tuple[int, int, float, float]]:
    spans: list[tuple[int, int, float, float]] = []
    for index, start in enumerate(bar_times):
        end = bar_times[index + 1] if index + 1 < len(bar_times) else end_seconds
        if end <= start:
            continue
        spans.append((index + 1, index + 1, float(start), float(end)))
    return spans


def _mean_chroma(
    chroma: np.ndarray, frame_times: np.ndarray, start: float, end: float
) -> np.ndarray:
    mask = (frame_times >= start) & (frame_times < end)
    if not np.any(mask):
        nearest = int(np.argmin(np.abs(frame_times - start)))
        return chroma[:, nearest]
    return np.mean(chroma[:, mask], axis=1)


def _score_bar(chroma_vector: np.ndarray) -> tuple[list[ChordCandidate], float]:
    if chroma_vector.shape != (12,) or not np.any(chroma_vector):
        return [], 0.0

    scored: list[tuple[float, int, str]] = []
    for root in range(12):
        for quality, intervals in TRIAD_INTERVALS.items():
            template = _triad_template(root, intervals)
            scored.append((_cosine_similarity(chroma_vector, template), root, quality))
    scored.sort(reverse=True)

    best = scored[0][0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    # Lean on candidate separation: a flat/ambiguous bar (best ~= second) should
    # stay low even though its absolute template fit is moderate.
    confidence = round(_clamp(0.15 + (best - second) * 1.8 + best * 0.1), 3)
    candidates = [
        ChordCandidate(
            root=NOTE_NAMES[root],
            quality=quality,
            label=_triad_label(root, quality),
            confidence=round(_clamp(score), 3),
        )
        for score, root, quality in scored[:MAX_CANDIDATES]
    ]
    return candidates, confidence


def _smooth(spans: list[ChordSpan]) -> list[ChordSpan]:
    if len(spans) < 3:
        return spans
    result = list(spans)
    for index in range(1, len(spans) - 1):
        previous, current, following = spans[index - 1], spans[index], spans[index + 1]
        if not (previous.chosen and following.chosen):
            continue
        if previous.chosen.label != following.chosen.label:
            continue
        if previous.confidence < SMOOTHING_STRONG_THRESHOLD:
            continue
        if following.confidence < SMOOTHING_STRONG_THRESHOLD:
            continue
        if current.chosen is not None and current.chosen.label == previous.chosen.label:
            continue
        result[index] = current.model_copy(update={"chosen": previous.chosen.model_copy()})
    return result


def _triad_template(root: int, intervals: tuple[int, int, int]) -> np.ndarray:
    template = np.zeros(12)
    for interval in intervals:
        template[(root + interval) % 12] = 1.0
    return template


def _triad_label(root: int, quality: str) -> str:
    name = NOTE_NAMES[root]
    if quality == "major":
        return name
    if quality == "minor":
        return f"{name}m"
    return f"{name}dim"


def _default_chroma_time_provider(path: str, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    from llm_band.infrastructure.mir.librosa_analyzer import HOP_LENGTH, _prepare_librosa_import

    _prepare_librosa_import()
    import librosa

    samples, sr = librosa.load(path, sr=sample_rate, mono=True)
    tuning = librosa.estimate_tuning(y=samples, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=samples, sr=sr, hop_length=HOP_LENGTH, tuning=tuning)
    frame_times = librosa.frames_to_time(
        np.arange(chroma.shape[1]), sr=sr, hop_length=HOP_LENGTH
    )
    return chroma, frame_times
