"""Per-bar energy and per-stem activity summaries.

Cheap RMS-based signals aligned to the bar grid. Section detection uses them to
find arrangement/energy boundaries that pure chord repetition misses (e.g. a song
that loops the same four chords through a quiet verse and a loud chorus). This is
deliberately light: one RMS pass per audio file, averaged into bar-sized windows.
No new MIR engine.

The pure logic (:func:`bar_means_from_rms`) takes an RMS frame series so it can be
unit-tested without audio. Audio I/O lives behind an injectable ``rms_provider``.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


SAMPLE_RATE = 22_050

# (path, sample_rate) -> (rms[frames], frame_times[frames])
RmsProvider = Callable[[str, int], "tuple[np.ndarray, np.ndarray]"]


def per_bar_energy(
    audio_path: str,
    bar_times: list[float],
    end_seconds: float,
    *,
    sample_rate: int = SAMPLE_RATE,
    rms_provider: RmsProvider | None = None,
) -> list[float]:
    """Normalized per-bar RMS energy aligned to ``bar_times`` (0..1 by peak)."""
    if len(bar_times) < 1:
        return []
    provider = rms_provider or _default_rms_provider
    rms, frame_times = provider(audio_path, sample_rate)
    return bar_means_from_rms(rms, frame_times, bar_times, end_seconds)


def per_stem_activity_by_bar(
    stem_paths: dict[str, str],
    bar_times: list[float],
    end_seconds: float,
    *,
    sample_rate: int = SAMPLE_RATE,
    rms_provider: RmsProvider | None = None,
) -> list[dict[str, float]]:
    """Per-bar ``{stem_name: activity}`` dicts, each stem self-normalized.

    Self-normalizing per stem means the signal captures when a stem becomes more
    or less active relative to its own range, which is what section novelty cares
    about - not whether one stem is louder than another in absolute terms.
    """
    if len(bar_times) < 1 or not stem_paths:
        return []
    per_stem = {
        name: per_bar_energy(
            path,
            bar_times,
            end_seconds,
            sample_rate=sample_rate,
            rms_provider=rms_provider,
        )
        for name, path in stem_paths.items()
    }
    activity: list[dict[str, float]] = []
    for index in range(len(bar_times)):
        activity.append(
            {
                name: values[index]
                for name, values in per_stem.items()
                if index < len(values)
            }
        )
    return activity


def bar_means_from_rms(
    rms: np.ndarray,
    frame_times: np.ndarray,
    bar_times: list[float],
    end_seconds: float,
) -> list[float]:
    rms = np.asarray(rms, dtype=float).reshape(-1)
    frame_times = np.asarray(frame_times, dtype=float).reshape(-1)
    if rms.size == 0 or frame_times.size == 0:
        return [0.0 for _ in bar_times]
    peak = float(np.max(rms))
    normalized = rms / peak if peak > 0.0 else rms

    means: list[float] = []
    for index, start in enumerate(bar_times):
        end = bar_times[index + 1] if index + 1 < len(bar_times) else end_seconds
        if end <= start:
            means.append(0.0)
            continue
        mask = (frame_times >= start) & (frame_times < end)
        if not np.any(mask):
            nearest = int(np.argmin(np.abs(frame_times - start)))
            means.append(round(float(normalized[nearest]), 4))
        else:
            means.append(round(float(np.mean(normalized[mask])), 4))
    return means


def _default_rms_provider(path: str, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    from music_assistant.infrastructure.mir.librosa_analyzer import HOP_LENGTH, _prepare_librosa_import

    _prepare_librosa_import()
    import librosa

    samples, sr = librosa.load(path, sr=sample_rate, mono=True)
    rms = librosa.feature.rms(y=samples, hop_length=HOP_LENGTH)[0]
    frame_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP_LENGTH)
    return rms, frame_times
