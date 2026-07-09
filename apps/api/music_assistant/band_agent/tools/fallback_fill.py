"""Deterministic per-instrument fill used when the LLM fill call fails.

MiniMax M3 (via opencode-go) intermittently truncates tool-call JSON mid-note
or refuses to call the tool at all. Rather than leaving that instrument
silent — which turns "compose a 6-piece band" into "here's a solo drum
loop" — we synthesise a minimal, on-chord pattern from the skeleton itself.

The output is not musically ambitious. It respects the chord progression,
lands chord tones on downbeats, and stays in a register that matches the
instrument's role. That's enough to make the roster audibly consistent
with what the frontend claims is playing.
"""

from __future__ import annotations

import re
from typing import Iterable

from music_assistant.music.theory import active_chord_at, chord_tone_names

from ..band_spec import BandSkeleton, InstrumentDecl, NotePlan


_NOTE_NAME_TO_PC = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def _pitch_class(name: str) -> int | None:
    return _NOTE_NAME_TO_PC.get(name)


def _chord_tone_pcs(chord: str) -> list[int]:
    """Ordered chord tones (root first) as pitch classes 0-11."""
    names = chord_tone_names(chord)
    pcs: list[int] = []
    for n in names:
        pc = _pitch_class(n)
        if pc is not None and pc not in pcs:
            pcs.append(pc)
    return pcs


def _chord_root_pc(chord: str) -> int | None:
    """Fast fallback root when chord_tone_names returns nothing (bad symbol)."""
    m = re.match(r"^([A-G][#b]?)", chord.strip())
    if not m:
        return None
    return _pitch_class(m.group(1))


def _nearest_pitch_in_range(pc: int, lo: int, hi: int) -> int:
    """Cheapest MIDI number with pitch class `pc` in [lo, hi]."""
    for octave in range((lo // 12) - 1, (hi // 12) + 2):
        p = octave * 12 + pc
        if lo <= p <= hi:
            return p
    return max(lo, min(hi, 60))


def _role_profile(instrument: InstrumentDecl) -> str:
    """Bucket the instrument into a synthesis strategy from id/role/instrument text."""
    hay = f"{instrument.id} {instrument.role} {instrument.instrument}".lower()
    if "bass" in hay:
        return "bass"
    if "pad" in hay or "atmosphere" in hay or "strings" in hay:
        return "pad"
    if "lead" in hay or "melody" in hay:
        return "lead"
    if "rhythm" in hay or "guitar" in hay or "pluck" in hay:
        return "rhythm"
    return "harmony"


def deterministic_fill(
    skeleton: BandSkeleton, instrument: InstrumentDecl
) -> list[NotePlan]:
    """Return a note list that covers `skeleton.num_bars`, following the
    chord progression and matching the instrument's role."""
    if instrument.is_drum:
        return []
    profile = _role_profile(instrument)
    notes: list[NotePlan] = []
    for bar in range(skeleton.num_bars):
        chord = active_chord_at(bar, skeleton.chord_progression)
        if not chord:
            continue
        tones = _chord_tone_pcs(chord)
        if not tones:
            root = _chord_root_pc(chord)
            if root is None:
                continue
            tones = [root]
        root_pc = tones[0]
        third_pc = tones[1] if len(tones) > 1 else root_pc
        fifth_pc = tones[2] if len(tones) > 2 else root_pc

        if profile == "bass":
            p = _nearest_pitch_in_range(root_pc, 28, 48)
            notes.append(NotePlan(bar=bar, start_beat=0.0, pitch=p, dur=4.0, velocity=96))
        elif profile == "pad":
            for pc in (root_pc, third_pc, fifth_pc):
                notes.append(
                    NotePlan(
                        bar=bar, start_beat=0.0,
                        pitch=_nearest_pitch_in_range(pc, 60, 72),
                        dur=4.0, velocity=72,
                    )
                )
        elif profile == "lead":
            notes.append(NotePlan(bar=bar, start_beat=0.0,
                                  pitch=_nearest_pitch_in_range(root_pc, 72, 84),
                                  dur=2.0, velocity=100))
            notes.append(NotePlan(bar=bar, start_beat=2.0,
                                  pitch=_nearest_pitch_in_range(fifth_pc, 72, 84),
                                  dur=2.0, velocity=100))
        elif profile == "rhythm":
            for beat in (0.0, 2.0):
                for pc in (root_pc, third_pc, fifth_pc):
                    notes.append(
                        NotePlan(
                            bar=bar, start_beat=beat,
                            pitch=_nearest_pitch_in_range(pc, 55, 67),
                            dur=1.5, velocity=84,
                        )
                    )
        else:  # harmony / keys / piano — arpeggiate the triad
            arpeggio: Iterable[tuple[float, int]] = (
                (0.0, root_pc), (1.0, third_pc), (2.0, fifth_pc), (3.0, third_pc)
            )
            for beat, pc in arpeggio:
                notes.append(
                    NotePlan(
                        bar=bar, start_beat=beat,
                        pitch=_nearest_pitch_in_range(pc, 60, 72),
                        dur=1.0, velocity=88,
                    )
                )
    return notes
