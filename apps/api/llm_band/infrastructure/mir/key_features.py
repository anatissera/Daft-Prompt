"""Key estimation from a harmonic source.

Builds a tuning-aware CQT chroma pitch-class summary and scores it against the
Krumhansl-Schmuckler major/minor profiles for all 12 tonics. Returns multiple
candidates and flags relative major/minor ambiguity (e.g. C major vs A minor),
which is the most common honest "we are not sure" case in key detection.

The pure scoring logic (:func:`key_profile_from_pitch_classes`) is separated
from audio I/O so it can be unit-tested with synthetic pitch-class vectors.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from llm_band.domain.audio_profile import KeyCandidate, KeyProfile
from llm_band.infrastructure.mir.librosa_analyzer import (
    MAJOR_KEY_PROFILE,
    MINOR_KEY_PROFILE,
    NOTE_NAMES,
    _clamp,
    _cosine_similarity,
)


SAMPLE_RATE = 22_050
RELATIVE_MINOR_OFFSET = 9  # relative minor tonic sits 9 semitones above the major
RELATIVE_AMBIGUITY_MARGIN = 0.04

# (path, sample_rate) -> 12-element pitch-class summary
ChromaProvider = Callable[[str, int], np.ndarray]


def estimate_key(
    harmonic_path: str,
    *,
    sample_rate: int = SAMPLE_RATE,
    chroma_provider: ChromaProvider | None = None,
    confidence_adjustment: float = 0.0,
    max_candidates: int = 8,
) -> KeyProfile:
    provider = chroma_provider or _default_chroma_provider
    pitch_classes = provider(harmonic_path, sample_rate)
    return key_profile_from_pitch_classes(
        pitch_classes,
        confidence_adjustment=confidence_adjustment,
        max_candidates=max_candidates,
    )


def key_profile_from_pitch_classes(
    pitch_classes: np.ndarray,
    *,
    confidence_adjustment: float = 0.0,
    max_candidates: int = 8,
) -> KeyProfile:
    vector = np.asarray(pitch_classes, dtype=float).reshape(-1)
    if vector.shape != (12,) or not np.any(vector):
        return KeyProfile()

    scored: list[tuple[float, int, str]] = []
    for tonic in range(12):
        scored.append((_cosine_similarity(vector, np.roll(MAJOR_KEY_PROFILE, tonic)), tonic, "major"))
        scored.append((_cosine_similarity(vector, np.roll(MINOR_KEY_PROFILE, tonic)), tonic, "minor"))
    scored.sort(reverse=True)

    best_score = scored[0][0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    separation = best_score - second_score
    confidence = _clamp(
        0.2 + separation * 2.0 + best_score * 0.25 + confidence_adjustment
    )

    candidates = [
        KeyCandidate(key=_label(tonic, mode), mode=mode, confidence=round(_clamp(score), 3))
        for score, tonic, mode in scored[: max(1, max_candidates)]
    ]
    relative_ambiguity = _is_relative_pair(scored[0], scored[1]) and (
        separation < RELATIVE_AMBIGUITY_MARGIN
    )
    return KeyProfile(
        primary=candidates[0],
        candidates=candidates,
        relative_key_ambiguity=relative_ambiguity,
        confidence=round(confidence, 3),
    )


def _label(tonic_index: int, mode: str) -> str:
    return f"{NOTE_NAMES[tonic_index]} {mode}"


def _is_relative_pair(
    first: tuple[float, int, str], second: tuple[float, int, str]
) -> bool:
    _, tonic_a, mode_a = first
    _, tonic_b, mode_b = second
    if mode_a == mode_b:
        return False
    major = first if mode_a == "major" else second
    minor = first if mode_a == "minor" else second
    return (minor[1] - major[1]) % 12 == RELATIVE_MINOR_OFFSET


def _default_chroma_provider(path: str, sample_rate: int) -> np.ndarray:
    from llm_band.infrastructure.mir.librosa_analyzer import _prepare_librosa_import

    _prepare_librosa_import()
    import librosa

    samples, sr = librosa.load(path, sr=sample_rate, mono=True)
    tuning = librosa.estimate_tuning(y=samples, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=samples, sr=sr, tuning=tuning)
    if not chroma.size:
        return np.zeros(12)
    return np.mean(chroma, axis=1)
