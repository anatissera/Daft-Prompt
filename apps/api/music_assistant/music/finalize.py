"""Deterministic composition-finalization passes applied after the agents compose.

Currently: a surgical bass-downbeat harmonic enforcement. The soft-guide prompt
(chord tones in the prompt) already gets melodic/harmonic instruments to ~90%+
chord-tone fit, and the bass's off-beat non-chord notes are idiomatic passing
tones we deliberately leave alone. The one musically-indefensible case is the
BASS landing on a non-chord tone on the DOWNBEAT (beat 0): there the bass defines
the chord's foundation, so a non-chord downbeat weakens the harmony. We snap only
those notes to the nearest in-range chord tone — nothing else is touched, so the
groove and all passing-tone movement are preserved (Valentino's expressivity
concern). The pass is idempotent: a snapped note is already a chord tone.
"""

from __future__ import annotations

from .theory import active_chord_at, chord_pitch_classes
from ..domain.song_state import RosterItem, SongState

_EPS = 1e-6


def _is_bass(roster: RosterItem) -> bool:
    if roster.is_drum:
        return False
    return "bass" in roster.instrument.lower() or "bass" in roster.role.lower()


def _nearest_chord_tone(pitch: int, chord_pcs: frozenset[int]) -> int:
    """The MIDI pitch whose pitch class is in the chord, closest to `pitch`.
    Ties break toward the lower pitch (a deeper bass note). We search within a
    ±6-semitone window so the snap stays in the register the bass is already
    playing — no roster midi_range is needed since the search anchors on the
    note's own pitch."""
    candidates = [
        p for p in range(max(0, pitch - 6), min(127, pitch + 6) + 1)
        if (p % 12) in chord_pcs
    ]
    if not candidates:
        return pitch
    return min(candidates, key=lambda p: (abs(p - pitch), p))


def enforce_bass_downbeats(song: SongState) -> int:
    """Snap bass downbeat (beat 0) non-chord notes to the nearest chord tone.

    Mutates `song` in place; returns the number of notes changed. Safe to call more
    than once (idempotent)."""
    progression = song.header.chord_progression
    roster_by_id = {r.id: r for r in song.roster}
    changed = 0
    for part_id, part in song.parts.items():
        roster = roster_by_id.get(part_id)
        if roster is None or not _is_bass(roster):
            continue
        for note in part.notes:
            if note.pitch is None or abs(note.start_beat) > _EPS:
                continue  # rests and off-downbeat notes are left alone
            chord = active_chord_at(note.bar, progression)
            chord_pcs = chord_pitch_classes(chord) if chord else frozenset()
            if not chord_pcs or (note.pitch % 12) in chord_pcs:
                continue
            snapped = _nearest_chord_tone(note.pitch, chord_pcs)
            if snapped != note.pitch:
                note.pitch = snapped
                changed += 1
    return changed
