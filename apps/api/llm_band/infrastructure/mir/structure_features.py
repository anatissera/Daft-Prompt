"""Progressions and abstract A/B/C structure from bar-aligned chords.

Splits the per-bar chord sequence into fixed phrase windows, labels windows that
share the same chord signature with the same abstract letter (A, B, C, ...), and
merges consecutive same-label windows into structural sections. Labels are
deliberately abstract: no ``verse``/``chorus``/``bridge`` semantics.
"""

from __future__ import annotations

from llm_band.domain.audio_profile import (
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

    structure_confidence = (
        round(sum(section.confidence for section in sections) / len(sections), 3)
        if sections
        else 0.0
    )
    return StructureProfile(sections=sections, confidence=structure_confidence), progressions


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


def _ordinal_label(index: int) -> str:
    if index < 26:
        return chr(ord("A") + index)
    return f"S{index}"
