"""Pure-function tests for rhythm skills."""

from __future__ import annotations

from llm_band.skills._tables import DRUM_KICK, DRUM_SNARE
from llm_band.skills.rhythm import drum_pattern, quantize_rhythm


def test_quantize_snaps_to_grid():
    out = quantize_rhythm([(0.27, 0.6), (1.13, 0.55)], grid=0.25, bar_beats=4.0)
    assert out == [(0.25, 0.5), (1.25, 0.5)]


def test_quantize_clamps_into_bar():
    out = quantize_rhythm([(3.9, 1.0)], grid=0.25, bar_beats=4.0)
    start, dur = out[0]
    assert start + dur <= 4.0


def test_quantize_enforces_minimum_duration():
    out = quantize_rhythm([(0.0, 0.0)], grid=0.25, bar_beats=4.0)
    assert out[0][1] >= 0.25


def test_quantize_invalid_grid_passes_through():
    onsets = [(0.27, 0.6)]
    assert quantize_rhythm(onsets, grid=0, bar_beats=4.0) == onsets


def test_drum_pattern_four_on_floor_has_kick_on_every_beat():
    notes = drum_pattern("four_on_floor", (4, 4), num_bars=1)
    kicks = sorted(n.start_beat for n in notes if n.pitch == DRUM_KICK)
    assert kicks == [0.0, 1.0, 2.0, 3.0]


def test_drum_pattern_rock_has_snare_on_2_and_4():
    notes = drum_pattern("rock_basic", (4, 4), num_bars=1)
    snares = sorted(n.start_beat for n in notes if n.pitch == DRUM_SNARE)
    assert snares == [1.0, 3.0]


def test_drum_pattern_tiles_across_bars():
    one = drum_pattern("rock_basic", (4, 4), num_bars=1)
    two = drum_pattern("rock_basic", (4, 4), num_bars=2)
    assert len(two) == 2 * len(one)
    assert {n.bar for n in two} == {0, 1}


def test_drum_pattern_unknown_style_falls_back_to_rock():
    fallback = drum_pattern("not-a-real-style", (4, 4), 1)
    rock = drum_pattern("rock_basic", (4, 4), 1)
    assert [(n.pitch, n.start_beat) for n in fallback] == [(n.pitch, n.start_beat) for n in rock]


def test_drum_pattern_alias_resolves():
    house = drum_pattern("house", (4, 4), 1)
    four = drum_pattern("four_on_floor", (4, 4), 1)
    assert [(n.pitch, n.start_beat) for n in house] == [(n.pitch, n.start_beat) for n in four]


def test_drum_pattern_skips_hits_past_bar_in_odd_meter():
    # 3/4 bar = 3 beats; beat-3 hits must be dropped.
    notes = drum_pattern("rock_basic", (3, 4), num_bars=1)
    assert all(n.start_beat < 3.0 for n in notes)
