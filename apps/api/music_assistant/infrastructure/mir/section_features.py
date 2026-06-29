"""Approximate A/B/C sections from bar-aligned novelty signals.

This is an incremental helper over the existing harmonic MVP: it consumes bar
spans plus optional per-bar energy or stem activity summaries. It does not add a
new MIR engine and keeps labels abstract.
"""

from __future__ import annotations

import numpy as np

from music_assistant.domain.reference_profile import ChordSpan, StructuralSection, StructureProfile
from music_assistant.infrastructure.mir.multimodal_features import (
    STEM_WEIGHTS,
    MultimodalBarFeatures,
)


DEFAULT_MIN_SECTION_BARS = 8
BOUNDARY_THRESHOLD = 0.28
MULTIMODAL_BOUNDARY_FLOOR = 0.32
MULTIMODAL_WINDOW_BARS = 4
MULTIMODAL_MIN_SECTION_BARS = 8
SECTION_SIMILARITY_THRESHOLD = 0.82


def detect_multimodal_sections(
    chord_spans: list[ChordSpan],
    features: MultimodalBarFeatures,
    *,
    window_bars: int = MULTIMODAL_WINDOW_BARS,
    min_section_bars: int = MULTIMODAL_MIN_SECTION_BARS,
) -> StructureProfile:
    """Detect sustained arrangement changes and group similar sections."""
    structure, _audit = detect_multimodal_sections_with_audit(
        chord_spans,
        features,
        window_bars=window_bars,
        min_section_bars=min_section_bars,
    )
    return structure


def detect_multimodal_sections_with_audit(
    chord_spans: list[ChordSpan],
    features: MultimodalBarFeatures,
    *,
    window_bars: int = MULTIMODAL_WINDOW_BARS,
    min_section_bars: int = MULTIMODAL_MIN_SECTION_BARS,
) -> tuple[StructureProfile, list[dict]]:
    """Detect sustained arrangement changes and explain boundary decisions."""
    total = min(len(chord_spans), features.bar_count)
    if total < min_section_bars * 2 or not features.by_stem:
        return _single_section(chord_spans), []

    candidates = [
        _multimodal_boundary_candidate(
            features, boundary, window_bars, chord_spans
        )
        for boundary in range(window_bars, total - window_bars + 1)
    ]
    values = np.asarray([candidate["score"] for candidate in candidates], dtype=float)
    median = float(np.median(values)) if values.size else 0.0
    mad = float(np.median(np.abs(values - median))) if values.size else 0.0
    threshold = max(MULTIMODAL_BOUNDARY_FLOOR, median + 1.5 * mad)
    for candidate in candidates:
        candidate["threshold"] = round(threshold, 3)
        if candidate["boundary"] < min_section_bars or total - candidate["boundary"] < min_section_bars:
            candidate["decision"] = "rejected"
            candidate["reason"] = "short_segment"
        elif candidate["score"] < threshold:
            candidate["decision"] = "rejected"
            candidate["reason"] = "weak_evidence"
        elif not _has_sustained_boundary_evidence(candidate["modality_scores"], candidate["boundary"]):
            candidate["decision"] = "rejected"
            candidate["reason"] = "weak_evidence"
        else:
            candidate["decision"] = "candidate"
            candidate["reason"] = "pending_spacing"

    chosen: list[int] = []
    for candidate in sorted(
        (candidate for candidate in candidates if candidate["decision"] == "candidate"),
        key=lambda candidate: (candidate["score"], candidate["boundary"] % 16 == 0, candidate["boundary"] % 8 == 0),
        reverse=True,
    ):
        boundary = candidate["boundary"]
        if all(abs(boundary - existing) >= min_section_bars for existing in chosen):
            chosen.append(boundary)
            candidate["decision"] = "accepted"
            candidate["reason"] = "sustained_multimodal_change"
        else:
            candidate["decision"] = "rejected"
            candidate["reason"] = "too_close_to_stronger_boundary"
    boundaries = sorted(chosen)
    if not boundaries:
        return _single_section(chord_spans), _audit_candidates(candidates)

    starts = [0, *boundaries]
    ends = [boundary - 1 for boundary in boundaries] + [total - 1]
    chord_labels = sorted(
        {
            span.chosen.label
            for span in chord_spans
            if span.chosen is not None
        }
    )
    signatures = [
        _section_signature(
            features,
            start,
            end + 1,
            chord_spans[start : end + 1],
            chord_labels,
        )
        for start, end in zip(starts, ends)
    ]
    labels = _similarity_labels(signatures)
    boundary_score = {candidate["boundary"]: candidate["score"] for candidate in candidates}
    sections: list[StructuralSection] = []
    for index, (start, end) in enumerate(zip(starts, ends)):
        adjacent = []
        if start in boundary_score:
            adjacent.append(boundary_score[start])
        if end + 1 in boundary_score:
            adjacent.append(boundary_score[end + 1])
        confidence = min(0.88, 0.45 + (sum(adjacent) / len(adjacent) if adjacent else 0.0) * 0.35)
        sections.append(
            StructuralSection(
                label=labels[index],
                start_bar=chord_spans[start].start_bar,
                end_bar=chord_spans[end].end_bar,
                start_seconds=chord_spans[start].start_seconds,
                end_seconds=chord_spans[end].end_seconds,
                confidence=round(confidence, 3),
                main_progression=_main_progression(chord_spans[start : end + 1]),
            )
        )
    sections = _merge_adjacent_sections(sections)
    return StructureProfile(
        sections=sections,
        confidence=round(sum(section.confidence for section in sections) / len(sections), 3),
    ), _audit_candidates(candidates)


def _multimodal_boundary_candidate(
    features: MultimodalBarFeatures,
    boundary: int,
    window_bars: int,
    chord_spans: list[ChordSpan] | None = None,
) -> dict:
    modality_scores = _multimodal_modality_scores(
        features, boundary, window_bars, chord_spans
    )
    score = _weighted_boundary_score(modality_scores, boundary)
    return {
        "boundary": boundary,
        "score": round(score, 3),
        "modality_scores": {
            name: round(value, 3) for name, value in sorted(modality_scores.items())
        },
        "aligned_to_4": boundary % 4 == 0,
        "aligned_to_8": boundary % 8 == 0,
        "aligned_to_16": boundary % 16 == 0,
    }


def _audit_candidates(candidates: list[dict]) -> list[dict]:
    return [
        {
            "bar": candidate["boundary"] + 1,
            "boundary_index": candidate["boundary"],
            "score": candidate["score"],
            "threshold": candidate.get("threshold"),
            "modality_scores": candidate["modality_scores"],
            "aligned_to_4": candidate["aligned_to_4"],
            "aligned_to_8": candidate["aligned_to_8"],
            "aligned_to_16": candidate["aligned_to_16"],
            "decision": "rejected" if candidate.get("decision") == "candidate" else candidate.get("decision", "rejected"),
            "reason": "weak_evidence" if candidate.get("decision") == "candidate" else candidate.get("reason", "weak_evidence"),
        }
        for candidate in candidates
    ]


def _has_sustained_boundary_evidence(
    modality_scores: dict[str, float], boundary: int
) -> bool:
    non_harmony = [
        value for name, value in modality_scores.items() if name != "harmony"
    ]
    moderate_non_harmony = sum(value >= 0.5 for value in non_harmony)
    if moderate_non_harmony >= 2:
        return True
    if any(value >= 0.6 for value in non_harmony):
        return any(value >= 0.25 for value in modality_scores.values())
    harmony = modality_scores.get("harmony", 0.0)
    return harmony >= 0.5 and boundary % 8 == 0


def _multimodal_boundary_score(
    features: MultimodalBarFeatures,
    boundary: int,
    window_bars: int,
    chord_spans: list[ChordSpan] | None = None,
) -> float:
    return _weighted_boundary_score(
        _multimodal_modality_scores(features, boundary, window_bars, chord_spans),
        boundary,
    )


def _multimodal_modality_scores(
    features: MultimodalBarFeatures,
    boundary: int,
    window_bars: int,
    chord_spans: list[ChordSpan] | None = None,
) -> dict[str, float]:
    modality_scores: dict[str, float] = {}
    for name, vectors in features.by_stem.items():
        left = vectors[max(0, boundary - window_bars) : boundary]
        right = vectors[boundary : min(len(vectors), boundary + window_bars)]
        if not left or not right:
            continue
        left_mean = np.mean(np.asarray(left, dtype=float), axis=0)
        right_mean = np.mean(np.asarray(right, dtype=float), axis=0)
        modality_scores[name] = _vector_distance(left_mean, right_mean)
    if chord_spans:
        modality_scores["harmony"] = _harmonic_novelty(
            chord_spans, boundary, window_bars
        )
    return modality_scores


def _weighted_boundary_score(
    modality_scores: dict[str, float], boundary: int
) -> float:
    if not modality_scores:
        return 0.0

    weights = {
        name: STEM_WEIGHTS.get(name, 0.10)
        for name in modality_scores
    }
    total_weight = sum(weights.values())
    score = sum(modality_scores[name] * weights[name] for name in modality_scores) / total_weight
    if sum(value >= 0.5 for value in modality_scores.values()) >= 2:
        score += 0.05
    if boundary % 8 == 0:
        score += 0.03
    if boundary % 16 == 0:
        score += 0.02
    return min(1.0, float(score))


def _harmonic_novelty(
    chord_spans: list[ChordSpan], boundary: int, window_bars: int
) -> float:
    left = chord_spans[max(0, boundary - window_bars) : boundary]
    right = chord_spans[boundary : boundary + window_bars]
    labels = sorted(
        {
            span.chosen.label
            for span in [*left, *right]
            if span.chosen is not None
        }
    )
    if not labels:
        return 0.0

    def distribution(spans: list[ChordSpan]) -> np.ndarray:
        counts = np.asarray(
            [
                sum(1 for span in spans if span.chosen and span.chosen.label == label)
                for label in labels
            ],
            dtype=float,
        )
        total = float(np.sum(counts))
        return counts / total if total > 0.0 else counts

    return min(1.0, float(0.5 * np.sum(np.abs(distribution(left) - distribution(right)))))


def _vector_distance(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.size, right.size)
    if width == 0:
        return 0.0
    difference = np.abs(left[:width] - right[:width])
    return min(1.0, float(np.mean(difference)))


def _section_signature(
    features: MultimodalBarFeatures,
    start: int,
    end: int,
    chord_spans: list[ChordSpan],
    chord_labels: list[str],
) -> np.ndarray:
    chunks: list[np.ndarray] = []
    for name in ("vocals", "drums", "bass", "other"):
        vectors = features.by_stem.get(name, [])[start:end]
        if vectors:
            chunks.append(np.mean(np.asarray(vectors, dtype=float), axis=0))
    if chord_labels:
        counts = np.asarray(
            [
                sum(
                    1
                    for span in chord_spans
                    if span.chosen and span.chosen.label == label
                )
                for label in chord_labels
            ],
            dtype=float,
        )
        total = float(np.sum(counts))
        chunks.append(counts / total if total > 0.0 else counts)
    return np.concatenate(chunks) if chunks else np.zeros(1)


def _similarity_labels(signatures: list[np.ndarray]) -> list[str]:
    representatives: list[np.ndarray] = []
    labels: list[str] = []
    for signature in signatures:
        match = next(
            (
                index
                for index, representative in enumerate(representatives)
                if _signature_similarity(signature, representative) >= SECTION_SIMILARITY_THRESHOLD
            ),
            None,
        )
        if match is None:
            representatives.append(signature)
            match = len(representatives) - 1
        labels.append(_ordinal_label(match))
    return labels


def _merge_adjacent_sections(
    sections: list[StructuralSection],
) -> list[StructuralSection]:
    merged: list[StructuralSection] = []
    for section in sections:
        if not merged or merged[-1].label != section.label:
            merged.append(section)
            continue
        previous = merged[-1]
        previous_bars = previous.end_bar - previous.start_bar + 1
        section_bars = section.end_bar - section.start_bar + 1
        total_bars = previous_bars + section_bars
        confidence = (
            previous.confidence * previous_bars
            + section.confidence * section_bars
        ) / total_bars
        merged[-1] = previous.model_copy(
            update={
                "end_bar": section.end_bar,
                "end_seconds": section.end_seconds,
                "confidence": round(confidence, 3),
                "main_progression": (
                    previous.main_progression + section.main_progression
                )[:16],
            }
        )
    return merged


def _signature_similarity(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.size, right.size)
    if width == 0:
        return 0.0
    left = left[:width]
    right = right[:width]
    return max(0.0, 1.0 - float(np.mean(np.abs(left - right))))


def detect_sections_from_bar_signals(
    chord_spans: list[ChordSpan],
    *,
    energy_by_bar: list[float] | None = None,
    stem_activity_by_bar: list[dict[str, float]] | None = None,
    min_section_bars: int = DEFAULT_MIN_SECTION_BARS,
) -> StructureProfile:
    if not chord_spans:
        return StructureProfile()

    boundaries = _candidate_boundaries(
        chord_spans,
        energy_by_bar=energy_by_bar,
        stem_activity_by_bar=stem_activity_by_bar,
        min_section_bars=min_section_bars,
    )
    if not boundaries:
        return _single_section(chord_spans)

    sections: list[StructuralSection] = []
    starts = [0, *boundaries]
    ends = [boundary - 1 for boundary in boundaries] + [len(chord_spans) - 1]
    confidence = _structure_confidence(boundaries)
    for index, (start, end) in enumerate(zip(starts, ends)):
        span_start = chord_spans[start]
        span_end = chord_spans[end]
        sections.append(
            StructuralSection(
                label=_ordinal_label(index),
                start_bar=span_start.start_bar,
                end_bar=span_end.end_bar,
                start_seconds=span_start.start_seconds,
                end_seconds=span_end.end_seconds,
                confidence=confidence,
                main_progression=_main_progression(chord_spans[start : end + 1]),
            )
        )
    return StructureProfile(sections=sections, confidence=confidence)


def _candidate_boundaries(
    chord_spans: list[ChordSpan],
    *,
    energy_by_bar: list[float] | None,
    stem_activity_by_bar: list[dict[str, float]] | None,
    min_section_bars: int,
) -> list[int]:
    scored: list[tuple[float, int]] = []
    total = len(chord_spans)
    for boundary in range(min_section_bars, total - min_section_bars + 1):
        previous_bar = chord_spans[boundary - 1].end_bar
        if previous_bar % 8 != 0:
            continue
        score = _boundary_score(
            chord_spans,
            boundary,
            energy_by_bar=energy_by_bar,
            stem_activity_by_bar=stem_activity_by_bar,
        )
        if previous_bar % 16 == 0:
            score += 0.04
        if score >= BOUNDARY_THRESHOLD:
            scored.append((score, boundary))

    chosen: list[int] = []
    for _score, boundary in sorted(scored, reverse=True):
        if all(abs(boundary - existing) >= min_section_bars for existing in chosen):
            chosen.append(boundary)
    return sorted(chosen)


def _boundary_score(
    chord_spans: list[ChordSpan],
    boundary: int,
    *,
    energy_by_bar: list[float] | None,
    stem_activity_by_bar: list[dict[str, float]] | None,
) -> float:
    scores = [_chord_novelty(chord_spans, boundary)]
    if energy_by_bar and len(energy_by_bar) >= boundary + 1:
        scores.append(abs(energy_by_bar[boundary] - energy_by_bar[boundary - 1]))
    if stem_activity_by_bar and len(stem_activity_by_bar) >= boundary + 1:
        scores.append(
            _stem_activity_novelty(
                stem_activity_by_bar[boundary - 1], stem_activity_by_bar[boundary]
            )
        )
    return max(scores)


def _chord_novelty(chord_spans: list[ChordSpan], boundary: int) -> float:
    left = _labels(chord_spans[max(0, boundary - 4) : boundary])
    right = _labels(chord_spans[boundary : boundary + 4])
    comparable = [(a, b) for a, b in zip(left, right) if a != "?" and b != "?"]
    if not comparable:
        return 0.0
    differences = sum(1 for a, b in comparable if a != b)
    return differences / len(comparable) * 0.35


def _stem_activity_novelty(left: dict[str, float], right: dict[str, float]) -> float:
    names = set(left) | set(right)
    if not names:
        return 0.0
    return sum(abs(right.get(name, 0.0) - left.get(name, 0.0)) for name in names) / len(names)


def _structure_confidence(boundaries: list[int]) -> float:
    return 0.58 if boundaries else 0.25


def _single_section(chord_spans: list[ChordSpan]) -> StructureProfile:
    section = StructuralSection(
        label="A",
        start_bar=chord_spans[0].start_bar,
        end_bar=chord_spans[-1].end_bar,
        start_seconds=chord_spans[0].start_seconds,
        end_seconds=chord_spans[-1].end_seconds,
        confidence=0.25,
        main_progression=_main_progression(chord_spans),
    )
    return StructureProfile(sections=[section], confidence=0.25)


def _main_progression(spans: list[ChordSpan]) -> list[str]:
    labels = [span.chosen.label for span in spans if span.chosen]
    return labels[:16]


def _labels(spans: list[ChordSpan]) -> list[str]:
    return [span.chosen.label if span.chosen else "?" for span in spans]


def _ordinal_label(index: int) -> str:
    if index < 26:
        return chr(ord("A") + index)
    return f"S{index}"
