from __future__ import annotations

from typing import get_args

import pytest

from music_assistant.domain.patch import (
    PATCH_SPEC,
    Patch,
    UnknownPatchError,
    patch_literal_covers_spec,
    resolve_patch,
)


def test_patch_literal_and_spec_are_in_sync():
    # The Literal is maintained by hand; catch any drift immediately.
    assert patch_literal_covers_spec(), (
        f"PATCH_SPEC keys and Patch Literal disagree.\n"
        f"in spec only: {set(PATCH_SPEC.keys()) - set(get_args(Patch))}\n"
        f"in literal only: {set(get_args(Patch)) - set(PATCH_SPEC.keys())}"
    )


def test_resolve_patch_returns_program_for_sampler_kind():
    program, preset = resolve_patch("distortion_guitar")
    assert program == 30
    assert preset is None


def test_resolve_patch_returns_preset_for_synth_kind():
    program, preset = resolve_patch("warm_pad")
    assert program == 0
    assert preset == "warm_pad"


def test_resolve_patch_raises_on_unknown_name():
    # Unknown patches raise so the caller can drop the offending instrument
    # instead of inheriting the old silent grand-piano fallback (which drove a
    # piano bias whenever the director LLM slipped on the vocab).
    with pytest.raises(UnknownPatchError):
        resolve_patch("nonexistent_patch")
