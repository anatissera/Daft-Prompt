"""Surgical bass-downbeat harmony enforcement (composition finalization)."""

from __future__ import annotations

from music_assistant.domain.song_state import (
    ChordSpan,
    Header,
    Note,
    Part,
    RosterItem,
    SongState,
)
from music_assistant.music.finalize import enforce_bass_downbeats


def _song(bass_notes, *, instrument="electric_bass", role="bass",
          chords=None, key="C major"):
    roster = [RosterItem(id="bass", instrument=instrument, role=role,
                         is_drum=False)]
    return SongState(
        request="t",
        header=Header(genre="t", key=key, tempo_bpm=100, num_bars=4,
                      chord_progression=([ChordSpan(bar=0, chord="Am7")]
                                         if chords is None else chords)),
        roster=roster,
        parts={"bass": Part(instrument_id="bass", notes=bass_notes)},
    )


def test_snaps_downbeat_non_chord_note_to_nearest_chord_tone():
    # D (38) on the downbeat over Am7 {A,C,E,G} → nearest chord tone is C (36) or E (40);
    # tie breaks lower → C (36).
    song = _song([Note(bar=0, start_beat=0.0, pitch=38, dur=1)])
    changed = enforce_bass_downbeats(song)
    assert changed == 1
    assert song.parts["bass"].notes[0].pitch == 36


def test_leaves_offbeat_passing_tones_alone():
    # same D (38) but on beat 2 — idiomatic bass movement, must NOT be touched.
    song = _song([Note(bar=0, start_beat=2.0, pitch=38, dur=1)])
    assert enforce_bass_downbeats(song) == 0
    assert song.parts["bass"].notes[0].pitch == 38


def test_leaves_downbeat_chord_tones_alone():
    # A (45) is the root of Am7 on the downbeat — already correct.
    song = _song([Note(bar=0, start_beat=0.0, pitch=45, dur=1)])
    assert enforce_bass_downbeats(song) == 0
    assert song.parts["bass"].notes[0].pitch == 45


def test_does_not_touch_non_bass_instruments():
    roster = [RosterItem(id="lead", instrument="synth", role="melody",
                         is_drum=False)]
    song = SongState(
        request="t",
        header=Header(genre="t", key="C major", tempo_bpm=100, num_bars=4,
                      chord_progression=[ChordSpan(bar=0, chord="Am7")]),
        roster=roster,
        parts={"lead": Part(instrument_id="lead",
                            notes=[Note(bar=0, start_beat=0.0, pitch=38, dur=1)])},
    )
    assert enforce_bass_downbeats(song) == 0
    assert song.parts["lead"].notes[0].pitch == 38


def test_snapped_pitch_stays_in_range():
    # tight bass range that excludes the in-octave chord tones near the note forces the
    # snap to pick an in-range chord tone.
    song = _song([Note(bar=0, start_beat=0.0, pitch=38, dur=1)])
    enforce_bass_downbeats(song)
    p = song.parts["bass"].notes[0].pitch
    assert 33 <= p <= 45
    assert p % 12 in {9, 0, 4, 7}  # Am7 pitch classes


def test_idempotent():
    song = _song([Note(bar=0, start_beat=0.0, pitch=38, dur=1)])
    assert enforce_bass_downbeats(song) == 1
    assert enforce_bass_downbeats(song) == 0


def test_no_chord_progression_no_change():
    song = _song([Note(bar=0, start_beat=0.0, pitch=38, dur=1)], chords=[])
    assert enforce_bass_downbeats(song) == 0
