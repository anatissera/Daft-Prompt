"""Progressions and abstract A/B/C structure from bar-aligned chords.

Splits the per-bar chord sequence into fixed phrase windows, labels windows that
share the same chord signature with the same abstract letter (A, B, C, ...), and
merges consecutive same-label windows into structural sections. Labels are
deliberately abstract: no ``verse``/``chorus``/``bridge`` semantics.
"""

from __future__ import annotations

from music_assistant.domain.reference_profile import (
    ChordSpan,
    ProgressionEstimate,
    StructuralSection,
    StructureProfile,
)


PHRASE_BARS = 4


def detect_structure(
    chord_spans: list[ChordSpan],
    *,
    phrase_bars: int = PHRASE_BARS,
) -> tuple[StructureProfile, list[ProgressionEstimate]]:
    if not chord_spans:
        return StructureProfile(), []

    windows = _windows(chord_spans, phrase_bars)
    labels = _assign_labels(windows)
    sections = _merge_sections(windows, labels)
    progressions = _progressions(windows)
    fuzzy_progression = find_repeated_progression_candidate(
        chord_spans, phrase_bars=phrase_bars
    )
    if fuzzy_progression and _should_prepend_fuzzy_progression(fuzzy_progression, progressions):
        progressions = [fuzzy_progression, *progressions]
    sections = _fallback_sections_if_degenerate(chord_spans, sections)

    structure_confidence = (
        round(sum(section.confidence for section in sections) / len(sections), 3)
        if sections
        else 0.0
    )
    return StructureProfile(sections=sections, confidence=structure_confidence), progressions


def find_repeated_progression_candidate(
    chord_spans: list[ChordSpan],
    *,
    phrase_bars: int = PHRASE_BARS,
) -> ProgressionEstimate | None:
    if len(chord_spans) < phrase_bars * 2:
        return None

    windows = _windows(chord_spans, phrase_bars)
    best_group: list[dict] = []
    best_score = 0.0
    for seed in windows:
        group = [window for window in windows if _fuzzy_window_match(seed, window)]
        if len(group) < 2:
            continue
        confidence = _fuzzy_group_confidence(group)
        score = len(group) + confidence
        if score > best_score:
            best_group = group
            best_score = score

    if not best_group:
        return None

    chords = _consensus_chords(best_group)
    if not chords:
        return None
    confidence = _fuzzy_group_confidence(best_group)
    return ProgressionEstimate(
        start_bar=best_group[0]["start_bar"],
        end_bar=best_group[0]["end_bar"],
        chords=chords,
        confidence=confidence,
        repetitions=len(best_group),
    )


def _windows(
    spans: list[ChordSpan], phrase_bars: int
) -> list[dict]:
    windows: list[dict] = []
    for start in range(0, len(spans), phrase_bars):
        chunk = spans[start : start + phrase_bars]
        confidences = [span.confidence for span in chunk]
        windows.append(
            {
                "start_bar": chunk[0].start_bar,
                "end_bar": chunk[-1].end_bar,
                "start_seconds": chunk[0].start_seconds,
                "end_seconds": chunk[-1].end_seconds,
                "chords": [span.chosen.label if span.chosen else "?" for span in chunk],
                "confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
            }
        )
    return windows


def _assign_labels(windows: list[dict]) -> list[str]:
    label_by_signature: dict[tuple[str, ...], str] = {}
    labels: list[str] = []
    for window in windows:
        signature = tuple(window["chords"])
        if signature not in label_by_signature:
            label_by_signature[signature] = _ordinal_label(len(label_by_signature))
        labels.append(label_by_signature[signature])
    return labels


def _merge_sections(windows: list[dict], labels: list[str]) -> list[StructuralSection]:
    sections: list[StructuralSection] = []
    index = 0
    while index < len(windows):
        end = index
        while end + 1 < len(windows) and labels[end + 1] == labels[index]:
            end += 1
        group = windows[index : end + 1]
        confidence = round(sum(w["confidence"] for w in group) / len(group), 3)
        main_progression = [chord for chord in windows[index]["chords"] if chord != "?"][:16]
        sections.append(
            StructuralSection(
                label=labels[index],
                start_bar=windows[index]["start_bar"],
                end_bar=windows[end]["end_bar"],
                start_seconds=windows[index]["start_seconds"],
                end_seconds=windows[end]["end_seconds"],
                confidence=confidence,
                main_progression=main_progression,
            )
        )
        index = end + 1
    return sections


def _progressions(windows: list[dict]) -> list[ProgressionEstimate]:
    order: list[tuple[str, ...]] = []
    info: dict[tuple[str, ...], dict] = {}
    for window in windows:
        signature = tuple(window["chords"])
        if signature not in info:
            info[signature] = {
                "start_bar": window["start_bar"],
                "end_bar": window["end_bar"],
                "chords": [chord for chord in window["chords"] if chord != "?"][:16],
                "confidences": [],
            }
            order.append(signature)
        info[signature]["confidences"].append(window["confidence"])

    progressions: list[ProgressionEstimate] = []
    for signature in order:
        entry = info[signature]
        confidences = entry["confidences"]
        progressions.append(
            ProgressionEstimate(
                start_bar=entry["start_bar"],
                end_bar=entry["end_bar"],
                chords=entry["chords"],
                confidence=round(sum(confidences) / len(confidences), 3),
                repetitions=len(confidences),
            )
        )
    return progressions


def _should_prepend_fuzzy_progression(
    fuzzy: ProgressionEstimate, progressions: list[ProgressionEstimate]
) -> bool:
    if not progressions:
        return True
    if any(
        progression.chords == fuzzy.chords
        and progression.start_bar == fuzzy.start_bar
        and progression.end_bar == fuzzy.end_bar
        for progression in progressions
    ):
        return False
    first = progressions[0]
    if fuzzy.repetitions > first.repetitions:
        return True
    return fuzzy.repetitions == first.repetitions and len(fuzzy.chords) > len(first.chords)


def _fuzzy_window_match(left: dict, right: dict) -> bool:
    comparable = 0
    matches = 0
    for left_chord, right_chord in zip(left["chords"], right["chords"]):
        if left_chord == "?" or right_chord == "?":
            continue
        comparable += 1
        if left_chord == right_chord:
            matches += 1
    if comparable == 0:
        return False
    mismatches = comparable - matches
    return matches >= max(2, comparable - 1) and mismatches <= 1


def _consensus_chords(windows: list[dict]) -> list[str]:
    chords: list[str] = []
    width = max((len(window["chords"]) for window in windows), default=0)
    for index in range(width):
        counts: dict[str, int] = {}
        for window in windows:
            if index >= len(window["chords"]):
                continue
            chord = window["chords"][index]
            if chord == "?":
                continue
            counts[chord] = counts.get(chord, 0) + 1
        if counts:
            chords.append(max(counts.items(), key=lambda item: (item[1], item[0]))[0])
    return chords[:16]


def _fuzzy_group_confidence(windows: list[dict]) -> float:
    if not windows:
        return 0.0
    confidences = [window["confidence"] for window in windows]
    unknown_count = sum(
        1 for window in windows for chord in window["chords"] if chord == "?"
    )
    total_slots = sum(len(window["chords"]) for window in windows)
    unknown_penalty = unknown_count / max(1, total_slots) * 0.2
    return round(max(0.0, sum(confidences) / len(confidences) - unknown_penalty), 3)


def _fallback_sections_if_degenerate(
    spans: list[ChordSpan], sections: list[StructuralSection]
) -> list[StructuralSection]:
    if not spans or len(sections) != 2:
        return sections

    total_bars = spans[-1].end_bar - spans[0].start_bar + 1
    if total_bars <= 0:
        return sections
    first, tail = sections
    first_bars = first.end_bar - first.start_bar + 1
    tail_bars = tail.end_bar - tail.start_bar + 1
    if first_bars / total_bars <= 0.85 or tail_bars >= 2:
        return sections

    chosen = [span.chosen.label for span in spans[:PHRASE_BARS] if span.chosen]
    return [
        StructuralSection(
            label="A",
            start_bar=spans[0].start_bar,
            end_bar=spans[-1].end_bar,
            start_seconds=spans[0].start_seconds,
            end_seconds=spans[-1].end_seconds,
            confidence=0.25,
            main_progression=chosen[:16],
        )
    ]


def _ordinal_label(index: int) -> str:
    if index < 26:
        return chr(ord("A") + index)
    return f"S{index}"
