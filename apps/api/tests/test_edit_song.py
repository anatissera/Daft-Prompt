"""Deterministic application of EditPlans over a previous SongState."""

from __future__ import annotations

from music_assistant.band_agent.edit_song import EditOp, EditPlan, apply_edit
from music_assistant.domain.song_state import Header, Note, Part, RosterItem, SongState


def _song() -> SongState:
    header = Header(genre="funk", key="E minor", tempo_bpm=100, num_bars=4)
    roster = [
        RosterItem(id="bass", instrument="slap bass", patch="slap_bass", midi_program=36, role="groove"),
        RosterItem(id="keys", instrument="piano", patch="acoustic_grand_piano", midi_program=0, role="comping"),
        RosterItem(id="drums", instrument="kit", role="beat", is_drum=True),
    ]
    parts = {
        "bass": Part(instrument_id="bass", notes=[Note(bar=0, start_beat=0, pitch=40, dur=1, velocity=100)]),
        "keys": Part(instrument_id="keys", notes=[Note(bar=0, start_beat=0, pitch=64, dur=1, velocity=80)]),
        "drums": Part(instrument_id="drums", notes=[Note(bar=0, start_beat=0, pitch=36, dur=0.2, velocity=110)]),
    }
    return SongState(request="funk", header=header, roster=roster, parts=parts)


def test_transpose_skips_drums():
    song, changes = apply_edit(_song(), EditPlan(operations=[EditOp(op="transpose", target="all", semitones=2)]))
    assert song.parts["bass"].notes[0].pitch == 42
    assert song.parts["keys"].notes[0].pitch == 66
    assert song.parts["drums"].notes[0].pitch == 36  # drums untouched
    assert changes


def test_replace_instrument_swaps_patch_and_folds_register():
    plan = EditPlan(operations=[EditOp(op="replace_instrument", target="keys", new_patch="electric_bass")])
    song, changes = apply_edit(_song(), plan)
    keys = next(r for r in song.roster if r.id == "keys")
    assert keys.patch == "electric_bass"
    assert keys.midi_program == 33
    # pitch 64 folded down into bass register (24-55)
    assert song.parts["keys"].notes[0].pitch == 52


def test_replace_instrument_echoed_old_name_does_not_veto_patch():
    # The planner LLM often echoes the OLD instrument name in new_name.
    # That must neither keep the stale display name nor let name-keyword
    # reconciliation override the requested patch (bass name -> bass patch).
    plan = EditPlan(operations=[
        EditOp(op="replace_instrument", target="bass", new_patch="acoustic_grand_piano", new_name="slap bass"),
    ])
    song, _ = apply_edit(_song(), plan)
    bass = next(r for r in song.roster if r.id == "bass")
    assert bass.patch == "acoustic_grand_piano"
    assert bass.midi_program == 0
    assert bass.instrument == "acoustic grand piano"


def test_replace_instrument_skips_drums():
    plan = EditPlan(operations=[EditOp(op="replace_instrument", target="drums", new_patch="acoustic_grand_piano")])
    song, changes = apply_edit(_song(), plan)
    drums = next(r for r in song.roster if r.id == "drums")
    assert drums.is_drum and drums.instrument == "kit"
    assert any("batería" in c for c in changes)


def test_remove_instrument():
    song, _ = apply_edit(_song(), EditPlan(operations=[EditOp(op="remove_instrument", target="piano")]))
    assert all(r.id != "keys" for r in song.roster)
    assert "keys" not in song.parts


def test_set_tempo_and_velocity():
    plan = EditPlan(operations=[
        EditOp(op="set_tempo", tempo_bpm=120),
        EditOp(op="scale_velocity", target="bass", velocity_factor=1.3),
    ])
    song, _ = apply_edit(_song(), plan)
    assert song.header.tempo_bpm == 120
    assert song.parts["bass"].notes[0].velocity == 130 if False else song.parts["bass"].notes[0].velocity == 127


def test_unknown_target_is_skipped_not_fatal():
    song, changes = apply_edit(_song(), EditPlan(operations=[EditOp(op="remove_instrument", target="theremin")]))
    assert len(song.roster) == 3
    assert any("no match" in c for c in changes)
