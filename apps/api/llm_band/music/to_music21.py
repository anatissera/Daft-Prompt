"""SongState -> music21 Score, used to export MusicXML (for in-browser engraving)
and, later, PDF via MuseScore/LilyPond.

music21 offsets are measured in quarter lengths, which match our beat convention.
Pitched parts are included; drum parts are skipped in the score (Phase 1 keeps the
engraving simple — drums still appear in the MIDI).
"""

from __future__ import annotations

from music21 import clef, instrument, key, meter, note, stream, tempo

from .theory import beats_per_bar as _beats_per_bar
from ..schema import SongState

# quarter-length divisors used when snapping ragged float durations to a clean
# notation grid: 4 -> sixteenths, 3 -> triplet-eighths.
_QUANTIZE_DIVISORS = (4, 3)


def song_to_score(song: SongState, quantize: bool = True) -> stream.Score:
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

        if quantize:
            # snap ragged float offsets/durations (e.g. 0.333…) to a clean grid so
            # notation doesn't blow up on un-representable tuplets.
            p.quantize(quarterLengthDivisors=_QUANTIZE_DIVISORS,
                       processOffsets=True, processDurations=True, inPlace=True)
        p.makeMeasures(inPlace=True)
        score.insert(0, p)

    return score
