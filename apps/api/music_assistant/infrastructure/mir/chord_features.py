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

from music_assistant.domain.reference_profile import ChordCandidate, ChordSpan
from music_assistant.infrastructure.mir.librosa_analyzer import (
    NOTE_NAMES,
    _clamp,
    _cosine_similarity,
)


SAMPLE_RATE = 22_050
CHOSEN_THRESHOLD = 0.45
SMOOTHING_STRONG_THRESHOLD = 0.55
MAX_CANDIDATES = 5
# A confident bass root nudges matching-root triads. The bonus is small and
# capped so it only breaks a near-tie; a clearly-winning non-bass triad stands.
BASS_ROOT_BONUS = 0.06
# The dominant bass pitch class must be at least this many times the mean bass
# chroma energy to be trusted as a root (otherwise the bar's bass is ambiguous).
BASS_ROOT_PROMINENCE = 1.3

# (start_bar, end_bar, start_seconds, end_seconds)
BarSpan = "tuple[int, int, float, float]"

TRIAD_INTERVALS: dict[str, tuple[int, int, int]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "diminished": (0, 3, 6),
}

# (path, sample_rate) -> (chroma[12, frames], frame_times[frames])
ChromaTimeProvider = Callable[[str, int], "tuple[np.ndarray, np.ndarray]"]

NOTE_INDEX = {name: index for index, name in enumerate(NOTE_NAMES)}
ENHARMONIC_TO_INDEX = {
    **NOTE_INDEX,
    "Db": 1,
    "D#": 3,
    "Gb": 6,
    "G#": 8,
    "A#": 10,
}
FLAT_NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def chords_from_bar_chromas(
    bar_chromas: list[np.ndarray],
    bar_spans: list[tuple[int, int, float, float]],
    *,
    confidence_threshold: float = CHOSEN_THRESHOLD,
    bass_roots: list[int | None] | None = None,
) -> list[ChordSpan]:
    spans: list[ChordSpan] = []
    for index, (chroma, (start_bar, end_bar, start_seconds, end_seconds)) in enumerate(
        zip(bar_chromas, bar_spans)
    ):
        bass_root = bass_roots[index] if bass_roots and index < len(bass_roots) else None
        candidates, confidence = _score_bar(np.asarray(chroma, dtype=float), bass_root=bass_root)
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
    bass_roots: list[int | None] | None = None,
) -> list[ChordSpan]:
    if len(bar_times) < 1:
        return []
    provider = chroma_time_provider or _default_chroma_time_provider
    chroma, frame_times = provider(harmonic_path, sample_rate)
    bar_spans = _bar_spans_from_times(bar_times, end_seconds)
    bar_chromas = [_mean_chroma(chroma, frame_times, start, end) for _, _, start, end in bar_spans]
    return chords_from_bar_chromas(
        bar_chromas,
        bar_spans,
        confidence_threshold=confidence_threshold,
        bass_roots=bass_roots,
    )


def bass_root_from_chroma(
    chroma_vector: np.ndarray, *, prominence: float = BASS_ROOT_PROMINENCE
) -> int | None:
    """Dominant bass pitch class as a root, or ``None`` if the bass is ambiguous."""
    vector = np.asarray(chroma_vector, dtype=float).reshape(-1)
    if vector.shape != (12,) or not np.any(vector):
        return None
    top = int(np.argmax(vector))
    mean = float(np.mean(vector))
    if mean <= 0.0 or vector[top] < prominence * mean:
        return None
    return top


def estimate_bass_roots(
    bass_path: str,
    bar_times: list[float],
    end_seconds: float,
    *,
    sample_rate: int = SAMPLE_RATE,
    chroma_time_provider: ChromaTimeProvider | None = None,
) -> list[int | None]:
    """Per-bar bass root pitch class aligned to the same bar spans as the chords."""
    if len(bar_times) < 1:
        return []
    provider = chroma_time_provider or _default_chroma_time_provider
    chroma, frame_times = provider(bass_path, sample_rate)
    bar_spans = _bar_spans_from_times(bar_times, end_seconds)
    return [
        bass_root_from_chroma(_mean_chroma(chroma, frame_times, start, end))
        for _, _, start, end in bar_spans
    ]


def apply_key_context(chord_spans: list[ChordSpan], key_label: str | None) -> list[ChordSpan]:
    if not key_label:
        return chord_spans
    diatonic = _diatonic_triads(key_label)
    if not diatonic:
        return chord_spans

    adjusted: list[ChordSpan] = []
    for index, span in enumerate(chord_spans):
        chosen = span.chosen
        if chosen is None:
            adjusted.append(span)
            continue

        normalized_label = _normalize_chord_label(chosen)
        is_diatonic = normalized_label in diatonic
        confidence = span.confidence
        chosen_confidence = chosen.confidence
        if is_diatonic:
            confidence = _clamp(confidence + 0.05)
            chosen_confidence = _clamp(chosen_confidence + 0.05)
        elif confidence < 0.5 and _is_isolated_outlier(chord_spans, index, diatonic):
            confidence = _clamp(confidence - 0.08)
            chosen_confidence = _clamp(chosen_confidence - 0.08)

        updated_chosen = chosen.model_copy(
            update={
                "root": _chord_root(normalized_label),
                "label": normalized_label,
                "confidence": round(chosen_confidence, 3),
            }
        )
        adjusted.append(
            span.model_copy(
                update={
                    "chosen": updated_chosen,
                    "confidence": round(confidence, 3),
                }
            )
        )
    return adjusted


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


def _diatonic_triads(key_label: str) -> set[str]:
    parts = key_label.split()
    if len(parts) < 2:
        return set()
    tonic_index = ENHARMONIC_TO_INDEX.get(parts[0])
    mode = parts[1].lower()
    if tonic_index is None:
        return set()
    if mode == "major":
        intervals = [0, 2, 4, 5, 7, 9, 11]
        qualities = ["major", "minor", "minor", "major", "major", "minor", "diminished"]
    elif mode == "minor":
        intervals = [0, 2, 3, 5, 7, 8, 10]
        qualities = ["minor", "diminished", "major", "minor", "minor", "major", "major"]
    else:
        return set()

    prefer_flats = "b" in parts[0] or mode == "minor"
    return {
        _triad_label_for_key((tonic_index + interval) % 12, quality, prefer_flats)
        for interval, quality in zip(intervals, qualities)
    }


def _normalize_chord_label(chosen: ChordCandidate) -> str:
    root_index = ENHARMONIC_TO_INDEX.get(chosen.root)
    if root_index is None:
        root_index = ENHARMONIC_TO_INDEX.get(_chord_root(chosen.label))
    if root_index is None:
        return chosen.label
    return _triad_label_for_key(root_index, chosen.quality, prefer_flats=True)


def _is_isolated_outlier(
    spans: list[ChordSpan], index: int, diatonic: set[str]
) -> bool:
    neighbors = []
    for neighbor_index in (index - 1, index + 1):
        if 0 <= neighbor_index < len(spans) and spans[neighbor_index].chosen:
            neighbors.append(_normalize_chord_label(spans[neighbor_index].chosen))
    return bool(neighbors) and all(label in diatonic for label in neighbors)


def _triad_label_for_key(root: int, quality: str, prefer_flats: bool) -> str:
    name = FLAT_NOTE_NAMES[root] if prefer_flats else NOTE_NAMES[root]
    if quality == "major":
        return name
    if quality == "minor":
        return f"{name}m"
    return f"{name}dim"


def _chord_root(label: str) -> str:
    if label.endswith("dim"):
        return label[:-3]
    if label.endswith("m"):
        return label[:-1]
    return label


def best_triad_fit(chroma_vector: np.ndarray) -> float:
    """Best cosine fit of any major/minor/diminished triad to a chroma vector.

    A single-chord bar fits one triad tightly (near 1.0); a bar that straddles
    two chords smears the chroma and fits every triad worse. Used to score
    bar-phase alignment without committing to a specific chord.
    """
    vector = np.asarray(chroma_vector, dtype=float).reshape(-1)
    if vector.shape != (12,) or not np.any(vector):
        return 0.0
    best = 0.0
    for root in range(12):
        for intervals in TRIAD_INTERVALS.values():
            best = max(best, _cosine_similarity(vector, _triad_template(root, intervals)))
    return float(best)


def _score_bar(
    chroma_vector: np.ndarray, *, bass_root: int | None = None
) -> tuple[list[ChordCandidate], float]:
    if chroma_vector.shape != (12,) or not np.any(chroma_vector):
        return [], 0.0

    # (ranked_score, raw_score, root, quality). A confident bass root adds a
    # capped bonus to matching-root triads; ranking uses the bonus, displayed
    # candidate confidences keep the raw template fit.
    scored: list[tuple[float, float, int, str]] = []
    for root in range(12):
        for quality, intervals in TRIAD_INTERVALS.items():
            template = _triad_template(root, intervals)
            raw = _cosine_similarity(chroma_vector, template)
            ranked = raw + BASS_ROOT_BONUS if bass_root is not None and root == bass_root else raw
            scored.append((ranked, raw, root, quality))
    scored.sort(key=lambda item: item[0], reverse=True)

    best = scored[0][0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    # Lean on candidate separation: a flat/ambiguous bar (best ~= second) should
    # stay low even though its absolute template fit is moderate. When the bass
    # only just broke a tie, this separation stays small, so confidence stays low.
    confidence = round(_clamp(0.15 + (best - second) * 1.8 + best * 0.1), 3)
    candidates = [
        ChordCandidate(
            root=NOTE_NAMES[root],
            quality=quality,
            label=_triad_label(root, quality),
            confidence=round(_clamp(raw), 3),
        )
        for _ranked, raw, root, quality in scored[:MAX_CANDIDATES]
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
    from music_assistant.infrastructure.mir.librosa_analyzer import HOP_LENGTH, _prepare_librosa_import

    _prepare_librosa_import()
    import librosa

    samples, sr = librosa.load(path, sr=sample_rate, mono=True)
    # Tune the CQT bins for SCORING (detuned recordings land on the right pitch
    # classes); labels stay A=440 since note names come from the pitch-class index.
    tuning = librosa.estimate_tuning(y=samples, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=samples, sr=sr, hop_length=HOP_LENGTH, tuning=tuning)
    frame_times = librosa.frames_to_time(
        np.arange(chroma.shape[1]), sr=sr, hop_length=HOP_LENGTH
    )
    return chroma, frame_times
