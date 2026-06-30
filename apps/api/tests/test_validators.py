"""Phase 2: deterministic validation."""

from __future__ import annotations

from music_assistant.music.validators import errors_only, validate_song
from music_assistant.domain.song_state import Header, Note, Part, RosterItem, SongState


def _song(roster: list[RosterItem], parts: dict[str, Part], *, key="C major",
          num_bars=4, ts=(4, 4)) -> SongState:
    return SongState(
        request="t",
        header=Header(genre="t", key=key, tempo_bpm=100, time_signature=ts, num_bars=num_bars),
        roster=roster,
        parts=parts,
    )


def test_fixture_song_has_no_errors(sample_song):
    issues = validate_song(sample_song)
    assert errors_only(issues) == []  # the canned fixture is clean


def test_pitch_out_of_range_is_error():
    roster = [RosterItem(id="bass", instrument="bass", midi_range=(28, 55))]
    parts = {"bass": Part(instrument_id="bass",
                          notes=[Note(bar=0, start_beat=0, pitch=90, dur=1)])}
    codes = {i.code for i in validate_song(_song(roster, parts))}
    assert "pitch_out_of_range" in codes


def test_note_overflowing_bar_is_error():
    roster = [RosterItem(id="lead", instrument="lead", midi_range=(0, 127))]
    parts = {"lead": Part(instrument_id="lead",
                          notes=[Note(bar=0, start_beat=3.0, pitch=60, dur=2.0)])}
    codes = {i.code for i in validate_song(_song(roster, parts))}
    assert "note_overflows_bar" in codes


def test_bar_index_out_of_range_is_error():
    roster = [RosterItem(id="lead", instrument="lead", midi_range=(0, 127))]
    parts = {"lead": Part(instrument_id="lead",
                          notes=[Note(bar=9, start_beat=0, pitch=60, dur=1)])}
    codes = {i.code for i in validate_song(_song(roster, parts, num_bars=4))}
    assert "bar_oob" in codes


def test_nonpositive_duration_and_velocity():
    roster = [RosterItem(id="lead", instrument="lead", midi_range=(0, 127))]
    parts = {"lead": Part(instrument_id="lead", notes=[
        Note(bar=0, start_beat=0, pitch=60, dur=0.0),
        Note(bar=0, start_beat=1, pitch=60, dur=1, velocity=200),
    ])}
    codes = {i.code for i in validate_song(_song(roster, parts))}
    assert "nonpositive_dur" in codes
    assert "velocity_oob" in codes


def test_drums_exempt_from_range_and_key():
    # a drum pitch that is both out of a melodic range and out of C major:
    roster = [RosterItem(id="drums", instrument="kit", midi_range=(35, 81), is_drum=True)]
    parts = {"drums": Part(instrument_id="drums",
                           notes=[Note(bar=0, start_beat=0, pitch=49, dur=0.5)])}  # 49 = C#3 (out of key)
    issues = validate_song(_song(roster, parts))
    codes = {i.code for i in issues}
    assert "pitch_out_of_range" not in codes
    assert "out_of_key" not in codes


def test_out_of_key_is_warning_not_error():
    roster = [RosterItem(id="lead", instrument="lead", midi_range=(0, 127))]
    parts = {"lead": Part(instrument_id="lead",
                          notes=[Note(bar=0, start_beat=0, pitch=61, dur=1)])}  # C# in C major
    issues = validate_song(_song(roster, parts))
    assert any(i.code == "out_of_key" and i.severity == "warning" for i in issues)
    assert errors_only(issues) == []


def test_part_without_roster_is_error():
    parts = {"ghost": Part(instrument_id="ghost", notes=[])}
    codes = {i.code for i in validate_song(_song([], parts))}
    assert "part_without_roster" in codes


def test_empty_notes_part_is_error():
    # the drum-agent bug: a rostered instrument that returns notes=[] sails through
    # silently today; it should be a repairable error.
    roster = [RosterItem(id="lead", instrument="lead", midi_range=(0, 127))]
    parts = {"lead": Part(instrument_id="lead", notes=[])}
    codes = {i.code for i in validate_song(_song(roster, parts))}
    assert "empty_part" in codes


def test_all_rests_part_is_error():
    # a part with notes present but every pitch None is still silent → same defect.
    roster = [RosterItem(id="lead", instrument="lead", midi_range=(0, 127))]
    parts = {"lead": Part(instrument_id="lead",
                          notes=[Note(bar=0, start_beat=0, pitch=None, dur=1)])}
    codes = {i.code for i in validate_song(_song(roster, parts))}
    assert "empty_part" in codes


def test_empty_drum_part_is_error():
    # drums sound via the GM percussion map, so an empty drum part is just as broken
    # as any other — they must NOT be exempt from the empty-part check.
    roster = [RosterItem(id="drums", instrument="drums", midi_range=(0, 127), is_drum=True)]
    parts = {"drums": Part(instrument_id="drums", notes=[])}
    codes = {i.code for i in validate_song(_song(roster, parts))}
    assert "empty_part" in codes
