"""Approximate A/B/C sections from bar-aligned novelty signals.

This is an incremental helper over the existing harmonic MVP: it consumes bar
spans plus optional per-bar energy or stem activity summaries. It does not add a
new MIR engine and keeps labels abstract.
"""

from __future__ import annotations

from llm_band.domain.audio_profile import ChordSpan, StructuralSection, StructureProfile


DEFAULT_MIN_SECTION_BARS = 8
BOUNDARY_THRESHOLD = 0.28


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
