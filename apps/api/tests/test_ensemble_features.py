"""Ensemble arrangement timeline (deep-music-analysis Track 6): section × stem
activity grid and entry/exit callouts, built from structure + stem dynamics."""

from __future__ import annotations

from music_assistant.domain.audio_profile import (
    DynamicsPoint,
    StemDynamics,
    StructuralSection,
    StructureProfile,
)
from music_assistant.infrastructure.mir.ensemble_features import build_ensemble_profile


def _structure() -> StructureProfile:
    return StructureProfile(
        sections=[
            StructuralSection(label="A", start_bar=1, end_bar=4, start_seconds=0.0, end_seconds=8.0, confidence=0.8),
            StructuralSection(label="B", start_bar=5, end_bar=8, start_seconds=8.0, end_seconds=16.0, confidence=0.8),
        ],
        confidence=0.8,
    )


def _dynamics(levels_by_bar: dict[int, float], confidence: float = 0.6) -> StemDynamics:
    return StemDynamics(
        points=[DynamicsPoint(bar=bar, level=level) for bar, level in levels_by_bar.items()],
        confidence=confidence,
    )


def test_columns_follow_sections_and_cells_follow_levels():
    ensemble = build_ensemble_profile(
        _structure(),
        {
            "drums": _dynamics({1: 0.8, 2: 0.9, 3: 0.85, 4: 0.9, 5: 0.9, 6: 0.95, 7: 0.9, 8: 0.9}),
            "vocals": _dynamics({1: 0.0, 2: 0.0, 3: 0.02, 4: 0.0, 5: 0.7, 6: 0.8, 7: 0.75, 8: 0.8}),
        },
    )
    assert ensemble is not None
    assert [column.section for column in ensemble.columns] == ["A", "B"]
    first = {cell.stem: cell for cell in ensemble.columns[0].cells}
    second = {cell.stem: cell for cell in ensemble.columns[1].cells}
    assert first["drums"].level == "high"
    assert first["vocals"].level == "silent"
    assert second["vocals"].level == "high"
    assert second["vocals"].activity == 1.0


def test_entry_exit_and_push_callouts():
    ensemble = build_ensemble_profile(
        _structure(),
        {
            "vocals": _dynamics({1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.8, 6: 0.8, 7: 0.8, 8: 0.8}),
            "bass": _dynamics({1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5, 5: 0.0, 6: 0.0, 7: 0.0, 8: 0.0}),
            "drums": _dynamics({1: 0.4, 2: 0.45, 3: 0.4, 4: 0.4, 5: 0.9, 6: 0.9, 7: 0.95, 8: 0.9}),
        },
    )
    assert ensemble is not None
    assert "vocals enters in B (bar 5)" in ensemble.callouts
    assert "bass drops out in B (bar 5)" in ensemble.callouts
    assert "drums pushes high in B (bar 5)" in ensemble.callouts
    assert ensemble.interpretation.startswith("Arrangement timeline:")


def test_stable_arrangement_has_no_callouts():
    ensemble = build_ensemble_profile(
        _structure(),
        {"drums": _dynamics({bar: 0.8 for bar in range(1, 9)})},
    )
    assert ensemble is not None
    assert ensemble.callouts == []
    assert "similar stem lineup" in ensemble.interpretation


def test_missing_ingredients_return_none():
    assert build_ensemble_profile(None, {"drums": _dynamics({1: 0.5})}) is None
    assert build_ensemble_profile(_structure(), {}) is None
    assert build_ensemble_profile(_structure(), {"drums": StemDynamics()}) is None


def test_stem_order_is_stable_and_confidence_bounded():
    ensemble = build_ensemble_profile(
        _structure(),
        {
            "other": _dynamics({bar: 0.5 for bar in range(1, 9)}, confidence=0.4),
            "drums": _dynamics({bar: 0.5 for bar in range(1, 9)}, confidence=0.8),
        },
    )
    assert ensemble is not None
    assert [cell.stem for cell in ensemble.columns[0].cells] == ["drums", "other"]
    assert 0.0 <= ensemble.confidence <= 1.0
