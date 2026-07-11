"""The director's onset_grid and max_notes_per_bar commitments are enforced
deterministically after fills — genre rhythm as data, density as arithmetic."""

from __future__ import annotations

from music_assistant.band_agent.band_spec import NotePlan
from music_assistant.band_agent.tools.groove_enforce import (
    enforce_density,
    enforce_grid,
)


def _n(bar: int, beat: float, pitch: int = 60, vel: int = 96) -> NotePlan:
    return NotePlan(bar=bar, start_beat=beat, pitch=pitch, dur=0.5, velocity=vel)


DEMBOW_KICK = "x.......x......."  # kick on beats 0 and 2


def test_grid_keeps_on_slot_notes_and_drops_off_grid():
    notes = [_n(0, 0.0), _n(0, 2.0), _n(0, 1.5), _n(0, 3.5)]
    out = enforce_grid(notes, DEMBOW_KICK, beats_per_bar=4.0)
    assert [(n.bar, n.start_beat) for n in out] == [(0, 0.0), (0, 2.0)]


def test_grid_snaps_near_misses_onto_the_slot():
    out = enforce_grid([_n(0, 2.1)], DEMBOW_KICK, beats_per_bar=4.0)
    assert len(out) == 1 and out[0].start_beat == 2.0


def test_empty_or_garbage_grid_means_free_phrasing():
    notes = [_n(0, 0.33), _n(0, 1.77)]
    assert enforce_grid(notes, "", beats_per_bar=4.0) == notes
    assert enforce_grid(notes, "????", beats_per_bar=4.0) == notes
    assert enforce_grid(notes, "....", beats_per_bar=4.0) == notes  # no onsets


def test_grid_applies_per_bar_cycle():
    # Same cell repeats every bar: beat 2 of bar 7 is still an "x" slot.
    out = enforce_grid([_n(7, 2.0), _n(7, 3.0)], DEMBOW_KICK, beats_per_bar=4.0)
    assert [(n.bar, n.start_beat) for n in out] == [(7, 2.0)]


def test_density_prunes_weakest_events_per_bar():
    notes = [
        _n(0, 0.0, vel=120), _n(0, 1.0, vel=60), _n(0, 2.0, vel=100),
        _n(0, 3.0, vel=50),
    ]
    out = enforce_density(notes, 2)
    assert sorted(n.start_beat for n in out) == [0.0, 2.0]


def test_density_counts_a_chord_as_one_event():
    chord = [_n(0, 0.0, pitch=60), _n(0, 0.0, pitch=64), _n(0, 0.0, pitch=67)]
    melody = [_n(0, 2.0), _n(0, 3.0, vel=40)]
    out = enforce_density(chord + melody, 2)
    # chord (1 event) + loudest melody note survive; all 3 chord tones kept
    assert len([n for n in out if n.start_beat == 0.0]) == 3
    assert len([n for n in out if n.start_beat == 2.0]) == 1
    assert not [n for n in out if n.start_beat == 3.0]


def test_density_zero_means_unlimited():
    notes = [_n(0, i / 4) for i in range(16)]
    assert enforce_density(notes, 0) == notes
