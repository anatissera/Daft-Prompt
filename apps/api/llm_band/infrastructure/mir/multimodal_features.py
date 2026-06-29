"""Interpretable per-stem feature vectors aligned to the bar grid."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np


STEM_WEIGHTS = {
    "drums": 0.30,
    "vocals": 0.25,
    "other": 0.20,
    "bass": 0.15,
    "harmony": 0.10,
}


@dataclass
class MultimodalBarFeatures:
    """Internal analysis data; vectors are not part of ``ReferenceProfile``."""

    by_stem: dict[str, list[np.ndarray]] = field(default_factory=dict)

    @property
    def bar_count(self) -> int:
        return max((len(vectors) for vectors in self.by_stem.values()), default=0)


StemVectorProvider = Callable[
    [str, str, list[float], float],
    list[np.ndarray],
]


def extract_multimodal_features(
    stem_paths: dict[str, str],
    bar_times: list[float],
    end_seconds: float,
    *,
    stem_vector_provider: StemVectorProvider | None = None,
) -> MultimodalBarFeatures:
    provider = stem_vector_provider or _default_stem_vectors
    by_stem: dict[str, list[np.ndarray]] = {}
    for name in ("vocals", "drums", "bass", "other"):
        path = stem_paths.get(name)
        if path is None:
            continue
        vectors = provider(name, path, bar_times, end_seconds)
        if vectors:
            by_stem[name] = robust_normalize(vectors)
    return MultimodalBarFeatures(by_stem=by_stem)


def robust_normalize(vectors: list[np.ndarray]) -> list[np.ndarray]:
    """Scale each feature to 0..1 using song-level 10th/90th percentiles."""
    if not vectors:
        return []
    matrix = np.asarray(vectors, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("bar feature vectors must form a two-dimensional matrix")
    low = np.percentile(matrix, 10, axis=0)
    high = np.percentile(matrix, 90, axis=0)
    scale = high - low
    scale[scale <= 1e-9] = 1.0
    return [np.clip((row - low) / scale, 0.0, 1.0) for row in matrix]


def _default_stem_vectors(
    name: str,
    path: str,
    bar_times: list[float],
    end_seconds: float,
) -> list[np.ndarray]:
    from llm_band.infrastructure.mir.librosa_analyzer import (
        HOP_LENGTH,
        SAMPLE_RATE,
        _prepare_librosa_import,
    )

    _prepare_librosa_import()
    import librosa

    samples, sr = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    stft = np.abs(librosa.stft(samples, hop_length=HOP_LENGTH))
    frame_times = librosa.frames_to_time(
        np.arange(stft.shape[1]), sr=sr, hop_length=HOP_LENGTH
    )
    rms = librosa.feature.rms(S=stft)[0]
    onset = librosa.onset.onset_strength(
        y=samples, sr=sr, hop_length=HOP_LENGTH
    )
    centroid = librosa.feature.spectral_centroid(S=stft, sr=sr)[0]
    bandwidth = librosa.feature.spectral_bandwidth(S=stft, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(S=stft)[0]
    chroma = librosa.feature.chroma_stft(
        S=stft**2, sr=sr, hop_length=HOP_LENGTH
    )
    frequencies = librosa.fft_frequencies(sr=sr, n_fft=(stft.shape[0] - 1) * 2)
    active_floor = float(np.percentile(rms, 30)) if rms.size else 0.0

    vectors: list[np.ndarray] = []
    for index, start in enumerate(bar_times):
        end = bar_times[index + 1] if index + 1 < len(bar_times) else end_seconds
        mask = (frame_times >= start) & (frame_times < end)
        indexes = np.flatnonzero(mask)
        if indexes.size == 0:
            nearest = int(np.argmin(np.abs(frame_times - start)))
            indexes = np.asarray([nearest])
        bar_rms = rms[indexes]
        bar_onset = onset[indexes]
        common = [
            float(np.mean(bar_rms)),
            float(np.mean(bar_rms > active_floor)),
        ]
        if name == "vocals":
            vector = [
                *common,
                float(np.std(bar_rms)),
                _onset_density(bar_onset),
                float(np.mean(centroid[indexes])),
            ]
        elif name == "drums":
            vector = [
                *common,
                _onset_density(bar_onset),
                *_band_energy(stft[:, indexes], frequencies),
                *_onset_pattern(bar_onset, bins=16),
            ]
        elif name == "bass":
            vector = [
                *common,
                _onset_density(bar_onset),
                *np.mean(chroma[:, indexes], axis=1).tolist(),
            ]
        else:
            vector = [
                *common,
                *np.mean(chroma[:, indexes], axis=1).tolist(),
                float(np.mean(centroid[indexes])),
                float(np.mean(bandwidth[indexes])),
                float(np.mean(flatness[indexes])),
                float(np.mean(bar_onset)),
            ]
        vectors.append(np.asarray(vector, dtype=float))
    return vectors


def _onset_density(onset: np.ndarray) -> float:
    if onset.size == 0:
        return 0.0
    threshold = float(np.mean(onset) + np.std(onset))
    return float(np.mean(onset > threshold))


def _onset_pattern(onset: np.ndarray, *, bins: int) -> list[float]:
    if onset.size == 0:
        return [0.0] * bins
    source = np.linspace(0.0, 1.0, onset.size)
    target = np.linspace(0.0, 1.0, bins)
    pattern = np.interp(target, source, onset)
    peak = float(np.max(pattern))
    if peak > 0.0:
        pattern = pattern / peak
    return pattern.tolist()


def _band_energy(stft: np.ndarray, frequencies: np.ndarray) -> list[float]:
    bands = [(0.0, 180.0), (180.0, 2_000.0), (2_000.0, float("inf"))]
    total = float(np.sum(stft))
    if total <= 0.0:
        return [0.0, 0.0, 0.0]
    return [
        float(np.sum(stft[(frequencies >= low) & (frequencies < high)])) / total
        for low, high in bands
    ]
