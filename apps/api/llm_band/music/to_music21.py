"""SongState -> music21 Score, used to export MusicXML (for in-browser engraving)
and, later, PDF via MuseScore/LilyPond.

music21 offsets are measured in quarter lengths, which match our beat convention.
Pitched parts are included; drum parts are skipped in the score (Phase 1 keeps the
engraving simple — drums still appear in the MIDI).
"""

from __future__ import annotations

from music21 import clef, instrument, key, meter, note, stream, tempo

from ..schema import SongState


def _beats_per_bar(time_signature: tuple[int, int]) -> float:
    numerator, denominator = time_signature
    return numerator * (4.0 / denominator)


def song_to_score(song: SongState) -> stream.Score:
    score = stream.Score()
    roster_by_id = {r.id: r for r in song.roster}
    beats_per_bar = _beats_per_bar(song.header.time_signature)

    num, den = song.header.time_signature
    for part_id, part in song.parts.items():
        roster = roster_by_id.get(part_id)
        if roster and roster.is_drum:
            continue  # skip percussion in the engraved score for now

        p = stream.Part(id=part_id)
        p.append(instrument.Instrument(instrumentName=part_id))
        p.append(tempo.MetronomeMark(number=song.header.tempo_bpm))
        p.append(meter.TimeSignature(f"{num}/{den}"))
        try:
            p.append(key.Key(song.header.key.split()[0]))
        except Exception:
            pass
        p.append(clef.BassClef() if (roster and roster.id == "bass") else clef.TrebleClef())

        for n in part.notes:
            if n.pitch is None:
                continue
            offset = n.bar * beats_per_bar + n.start_beat
            m21n = note.Note(int(n.pitch), quarterLength=n.dur)
            m21n.volume.velocity = int(n.velocity)
            p.insert(offset, m21n)

        p.makeMeasures(inPlace=True)
        score.insert(0, p)

    return score
