from __future__ import annotations

from typing import get_args

import pytest

from music_assistant.domain.patch import (
    PATCH_SPEC,
    Patch,
    UnknownPatchError,
    is_native_synth_patch,
    patch_literal_covers_spec,
    reconcile_patch,
    resolve_patch,
)


def test_patch_literal_and_spec_are_in_sync():
    assert patch_literal_covers_spec(), (
        f"PATCH_SPEC keys and Patch Literal disagree.\n"
        f"in spec only: {set(PATCH_SPEC.keys()) - set(get_args(Patch))}\n"
        f"in literal only: {set(get_args(Patch)) - set(PATCH_SPEC.keys())}"
    )


def test_resolve_patch_returns_program_for_sampler_kind():
    program, preset = resolve_patch("distortion_guitar")

    assert program == 30
    assert preset is None


def test_resolve_patch_returns_preset_and_gm_fallback_for_synth_kind():
    program, preset = resolve_patch("warm_pad")

    assert program == 89
    assert preset == "warm_pad"


def test_resolve_patch_raises_on_unknown_name():
    with pytest.raises(UnknownPatchError):
        resolve_patch("nonexistent_patch")


def test_native_synth_patch_detection_uses_closed_spec():
    assert is_native_synth_patch("sub_bass") is True
    assert is_native_synth_patch("gm_synth_bass") is False
    assert is_native_synth_patch(None) is False


def test_reconcile_patch_repairs_obvious_family_mismatch():
    assert reconcile_patch("distorted rhythm guitar", "electric_grand_piano") == "distortion_guitar"
    assert reconcile_patch("Rhodes keys", "distortion_guitar") == "electric_piano_rhodes"


def test_reconcile_patch_keeps_role_labels_when_not_obvious_family():
    assert reconcile_patch("main hook", "supersaw_lead") == "supersaw_lead"
