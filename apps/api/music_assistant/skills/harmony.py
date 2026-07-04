"""Harmony skills: scale/chord pitch classes, octave fitting, voice leading.

All functions are pure and deterministic. Pitches are MIDI integers (0-127);
pitch classes are 0-11. Chord input is a chord symbol string ("Cmaj7", "Am",
"G7", "F#m7b5") parsed by music21.harmony.

These skills do not touch SongState — callers feed them explicit context, which
keeps them reusable across director, instrument, and arbiter agents.
"""

from __future__ import annotations

from functools import lru_cache

from ..domain.song_state import Note
from ..music.theory import key_pitch_classes


@lru_cache(maxsize=256)
def _parse_chord_pcs(chord_symbol: str) -> tuple[int, ...]:
    """Pitch classes of `chord_symbol` as parsed by music21, or () if unparseable."""
    from music21 import harmony as m21harmony

    try:
        cs = m21harmony.ChordSymbol(chord_symbol)
        return tuple(sorted({p.pitchClass for p in cs.pitches}))
    except Exception:
        return ()


def scale_degrees(key: str, chord: str | None = None) -> dict[str, list[int]]:
    """Return diatonic scale pitch classes for `key` and chord tones for `chord`.

    `tensions` is the scale minus the chord tones — useful as passing-tone
    candidates. Unknown key or unparseable chord yields empty lists so callers
    can fall back to free choice rather than crash.
    """
    scale_pcs = sorted(key_pitch_classes(key))
    chord_pcs = list(_parse_chord_pcs(chord)) if chord else []
    tensions = [p for p in scale_pcs if p not in set(chord_pcs)]
    return {"scale": scale_pcs, "chord_tones": chord_pcs, "tensions": tensions}


def transpose(notes: list[Note], semitones: int) -> list[Note]:
    """Return a new list of notes with each melodic pitch shifted by `semitones`.

    Rests (pitch=None) and out-of-MIDI results are passed through unchanged so
    callers can decide whether to clip or drop them via `fit_to_range`.
    """
    out: list[Note] = []
    for n in notes:
        if n.pitch is None:
            out.append(n.model_copy())
            continue
        new_pitch = n.pitch + semitones
        if 0 <= new_pitch <= 127:
            out.append(n.model_copy(update={"pitch": new_pitch}))
        else:
            out.append(n.model_copy())
    return out


def fit_to_range(pitch: int, midi_low: int, midi_high: int) -> int:
    """Octave-shift `pitch` into `[midi_low, midi_high]`.

    If the range is narrower than an octave and `pitch`'s pitch class falls
    outside it, returns the nearest endpoint — callers that care about pitch
    fidelity should widen the range.
    """
    if midi_low > midi_high:
        midi_low, midi_high = midi_high, midi_low
    p = pitch
    while p < midi_low:
        p += 12
    while p > midi_high:
        p -= 12
    if p < midi_low:
        return midi_low if abs(midi_low - p) <= abs(p - midi_high) else midi_high
    return p


def voice_lead(
    next_chord: str,
    prev_pitches: list[int],
    midi_low: int,
    midi_high: int,
) -> list[int]:
    """Greedy minimal-motion voicing of `next_chord` given previous voicing.

    For each previous pitch, picks the in-range octave of the closest chord tone
    that has not been claimed by an earlier voice (so a triad against a three-
    voice prev voicing returns three distinct pitches when possible). Returns an
    empty list if the chord can't be parsed; returns fewer pitches than
    `prev_pitches` only if no in-range chord tone exists at all.
    """
    pcs = _parse_chord_pcs(next_chord)
    if not pcs or not prev_pitches:
        return []

    def candidates(pc: int) -> list[int]:
        base = pc
        while base + 12 <= midi_high:
            base += 12
        opts: list[int] = []
        p = base
        while p >= midi_low:
            opts.append(p)
            p -= 12
        return opts

    pc_options = {pc: candidates(pc) for pc in pcs}
    used: set[int] = set()
    out: list[int] = []
    for prev in prev_pitches:
        best: tuple[int, int] | None = None  # (distance, pitch)
        for pc, opts in pc_options.items():
            for cand in opts:
                if cand in used:
                    continue
                dist = abs(cand - prev)
                if best is None or dist < best[0]:
                    best = (dist, cand)
        if best is None:
            for opts in pc_options.values():
                for cand in opts:
                    dist = abs(cand - prev)
                    if best is None or dist < best[0]:
                        best = (dist, cand)
        if best is not None:
            out.append(best[1])
            used.add(best[1])
    return out


__all__ = ["scale_degrees", "transpose", "fit_to_range", "voice_lead"]
