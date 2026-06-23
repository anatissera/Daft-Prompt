"""SongState -> multitrack MIDI via pretty_midi.

Time model: an absolute beat = bar * beats_per_bar + start_beat, where a "beat" is
a quarter note. Seconds = beat * 60 / tempo_bpm. Drums (is_drum) route to the GM
percussion channel automatically by pretty_midi.
"""

from __future__ import annotations

import pretty_midi

from .theory import beats_per_bar as _beats_per_bar
from ..schema import SongState


def song_to_pretty_midi(song: SongState) -> pretty_midi.PrettyMIDI:
    bpm = song.header.tempo_bpm
    sec_per_beat = 60.0 / bpm
    beats_per_bar = _beats_per_bar(song.header.time_signature)

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    roster_by_id = {r.id: r for r in song.roster}

    for part_id, part in song.parts.items():
        roster = roster_by_id.get(part_id)
        program = roster.midi_program if roster else 0
        is_drum = roster.is_drum if roster else False
        inst = pretty_midi.Instrument(program=program, is_drum=is_drum, name=part_id)

        for note in part.notes:
            if note.pitch is None:  # rest
                continue
            abs_beat = note.bar * beats_per_bar + note.start_beat
            start = abs_beat * sec_per_beat
            end = (abs_beat + note.dur) * sec_per_beat
            inst.notes.append(
                pretty_midi.Note(
                    velocity=int(note.velocity),
                    pitch=int(note.pitch),
                    start=start,
                    end=end,
                )
            )
        pm.instruments.append(inst)

    return pm


def render_midi(song: SongState, path: str) -> str:
    """Write `song` to a `.mid` file at `path`; returns the path."""
    pm = song_to_pretty_midi(song)
    pm.write(path)
    return path
