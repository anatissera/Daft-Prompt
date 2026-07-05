"""Ensemble / arrangement view (plans/deep-music-analysis.md Track 6).

Builds a bar-aligned arrangement timeline — which stems play in which A/B/C
section, at what loudness — from ingredients the analyzer already has:
`StructureProfile` sections (1-based inclusive bars) and per-stem
`StemDynamics` curves from the deep-listening pass. Pure functions, no audio.

Section-to-section callouts ("vocals enter in B", "drums push high in C")
give the LLM explainer concrete arrangement events to cite. The plan's
voice-leading half of Track 6 needs per-stem transcription (Track 1, heavy
deps) and stays deferred.
"""

from __future__ import annotations

from music_assistant.domain.audio_profile import (
    ArrangementCell,
    ArrangementColumn,
    EnsembleProfile,
    StemDynamics,
    StructureProfile,
)

# Mean-section-level thresholds for the cell label.
LEVEL_SILENT = 0.05
LEVEL_LOW = 0.35
LEVEL_MEDIUM = 0.65
# A bar counts toward `activity` when the stem is audibly present in it.
ACTIVITY_FLOOR = 0.1

STEM_ORDER = ("drums", "bass", "vocals", "other")


def build_ensemble_profile(
    structure: StructureProfile | None,
    dynamics_by_stem: dict[str, StemDynamics],
) -> EnsembleProfile | None:
    """None when there is nothing to say (no sections or no stem curves)."""
    if structure is None or not structure.sections or not dynamics_by_stem:
        return None

    levels_by_stem = {
        name: {point.bar: point.level for point in dynamics.points}
        for name, dynamics in dynamics_by_stem.items()
        if dynamics.points
    }
    if not levels_by_stem:
        return None

    ordered_stems = [name for name in STEM_ORDER if name in levels_by_stem]
    ordered_stems += [name for name in levels_by_stem if name not in ordered_stems]

    columns: list[ArrangementColumn] = []
    for section in structure.sections:
        cells = []
        for name in ordered_stems:
            cells.append(
                _cell(name, levels_by_stem[name], section.start_bar, section.end_bar)
            )
        columns.append(
            ArrangementColumn(
                section=section.label,
                start_bar=section.start_bar,
                end_bar=section.end_bar,
                cells=cells,
            )
        )

    callouts = _section_change_callouts(columns)
    interpretation = (
        "Arrangement timeline: " + "; ".join(callouts[:3]) + "."
        if callouts
        else "The arrangement keeps a similar stem lineup across sections."
    )
    dynamics_confidence = sum(d.confidence for d in dynamics_by_stem.values()) / len(
        dynamics_by_stem
    )
    return EnsembleProfile(
        columns=columns,
        callouts=callouts[:12],
        interpretation=interpretation,
        confidence=round(min(structure.confidence, dynamics_confidence) * 0.9, 3),
    )


def _cell(
    name: str, levels_by_bar: dict[int, float], start_bar: int, end_bar: int
) -> ArrangementCell:
    bars = [
        levels_by_bar[bar]
        for bar in range(start_bar, end_bar + 1)
        if bar in levels_by_bar
    ]
    if not bars:
        return ArrangementCell(stem=name, activity=0.0, level="silent")
    mean_level = sum(bars) / len(bars)
    activity = sum(1 for level in bars if level > ACTIVITY_FLOOR) / len(bars)
    if mean_level <= LEVEL_SILENT:
        label = "silent"
    elif mean_level <= LEVEL_LOW:
        label = "low"
    elif mean_level <= LEVEL_MEDIUM:
        label = "medium"
    else:
        label = "high"
    return ArrangementCell(stem=name, activity=round(activity, 3), level=label)


def _section_change_callouts(columns: list[ArrangementColumn]) -> list[str]:
    callouts: list[str] = []
    for previous, current in zip(columns, columns[1:]):
        prev_cells = {cell.stem: cell for cell in previous.cells}
        for cell in current.cells:
            prev = prev_cells.get(cell.stem)
            if prev is None:
                continue
            where = f"in {current.section} (bar {current.start_bar})"
            if prev.level == "silent" and cell.level != "silent":
                callouts.append(f"{cell.stem} enters {where}")
            elif prev.level != "silent" and cell.level == "silent":
                callouts.append(f"{cell.stem} drops out {where}")
            elif cell.level == "high" and prev.level in ("low", "medium"):
                callouts.append(f"{cell.stem} pushes high {where}")
    return callouts
