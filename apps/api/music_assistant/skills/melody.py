"""Melody skill: chord-tone-anchored contour generation.

`melodic_contour` produces a starter melody an instrument agent can return
verbatim or ornament. It is intentionally simple — alternate chord tones with
in-scale passing tones — so the agent retains creative control while the skill
guarantees in-key, in-range output.
"""

from __future__ import annotations

from ..domain.song_state import ChordSpan, Note
from ..music.theory import beats_per_bar
from .harmony import fit_to_range, scale_degrees


def _nearest_pitch_at_pc(pc: int, anchor: int, midi_low: int, midi_high: int) -> int:
    base = (anchor // 12) * 12 + pc
    candidates = [base - 12, base, base + 12]
    in_range = [p for p in candidates if midi_low <= p <= midi_high]
    if in_range:
        return min(in_range, key=lambda p: abs(p - anchor))
    return fit_to_range(base, midi_low, midi_high)


def melodic_contour(
    progression: list[ChordSpan],
    key: str,
    midi_low: int,
    midi_high: int,
    time_signature: tuple[int, int] = (4, 4),
    density: float = 2.0,
    velocity: int = 90,
) -> list[Note]:
    """Build a melody by stepping chord tones with optional passing tones.

    `density` is notes-per-bar (clamped to [1, beats_per_bar]). The first note
    of each bar lands on a chord tone; remaining notes alternate between chord
    tones and the nearest in-key passing tone, so the line stays consonant on
    beat 1 and adds motion in between. Range is enforced via `fit_to_range`.
    """
    if not progression or midi_low > midi_high:
        return []
    bpb = beats_per_bar(time_signature)
    notes_per_bar = max(1, min(int(round(density)), int(bpb)))
    step_dur = bpb / notes_per_bar

    by_bar = {span.bar: span.chord for span in progression}
    bars = sorted(by_bar)
    anchor = (midi_low + midi_high) // 2

    out: list[Note] = []
    for bar in bars:
        chord = by_bar[bar]
        degrees = scale_degrees(key, chord)
        chord_tones = degrees["chord_tones"]
        scale_pcs = degrees["scale"] or chord_tones
        if not chord_tones:
            continue
        for i in range(notes_per_bar):
            if i % 2 == 0:
                pc = chord_tones[(i // 2) % len(chord_tones)]
            else:
                tensions = degrees["tensions"] or scale_pcs
                pc = tensions[(i // 2) % len(tensions)] if tensions else chord_tones[0]
            pitch = _nearest_pitch_at_pc(pc, anchor, midi_low, midi_high)
            anchor = pitch
            out.append(Note(
                bar=bar, start_beat=round(i * step_dur, 6),
                pitch=pitch, dur=round(step_dur, 6), velocity=velocity,
            ))
    return out


__all__ = ["melodic_contour"]
