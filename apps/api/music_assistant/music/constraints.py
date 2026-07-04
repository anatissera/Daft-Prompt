"""Deterministic musical constraint helpers for agent prompts and tests."""

from __future__ import annotations

from music_assistant.domain.song_state import Header, Note
from music_assistant.music.theory import chord_pitch_classes


_ROOT_PC = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}


def bass_pattern_from_chords(
    header: Header,
    *,
    register: tuple[int, int],
    density: str = "medium",
) -> list[Note]:
    starts = [0.0] if density == "sparse" else [0.0, 2.0] if density == "medium" else [0.0, 1.5, 2.0, 3.5]
    notes: list[Note] = []
    for span in header.chord_progression:
        pitch = _pitch_in_register(_root_pc(span.chord), register)
        for start in starts:
            notes.append(Note(bar=span.bar, start_beat=start, pitch=pitch, dur=0.75, velocity=96))
    return notes


def chord_voicing(chord: str, *, register: tuple[int, int], density: str = "medium") -> list[int]:
    pcs = sorted(chord_pitch_classes(chord) or {_root_pc(chord)})
    target_count = 3 if density == "sparse" else min(4, len(pcs)) if density == "medium" else min(5, len(pcs) + 1)
    pitches: list[int] = []
    octave = 0
    while len(pitches) < target_count and octave < 11:
        for pc in pcs:
            pitch = pc + (octave * 12)
            if register[0] <= pitch <= register[1]:
                pitches.append(pitch)
                if len(pitches) >= target_count:
                    break
        octave += 1
    return pitches


def melody_constraint_summary(*, key: str, register: tuple[int, int], motif: str = "short motif") -> str:
    return (
        f"Melody constraints: use {key} as the main pitch pool, stay in MIDI {register[0]}-{register[1]}, "
        f"repeat and vary a {motif}, build tension before section peaks, and resolve phrase endings."
    )


def synth_timbre_constraints(role: str, *, density: str = "medium") -> dict[str, str]:
    waveform = "saw/pulse blend" if "lead" in role.lower() else "warm saw pad" if "pad" in role.lower() else "simple subtractive synth"
    return {
        "role": role,
        "density": density,
        "waveform_family": waveform,
        "filter_envelope": "soft attack and low-pass movement" if "pad" in role.lower() else "snappy attack with moderate brightness",
        "playback_note": "General MIDI playback approximates this timbre; symbolic constraints remain primary.",
    }


def role_constraint_text(instrument: str, role: str, register: tuple[int, int], key: str = "") -> str:
    haystack = f"{instrument} {role}".lower()
    if "bass" in haystack:
        return (
            "Constraint hints: prioritize root motion, lock strong notes to kick beats, "
            f"use approach tones sparingly, and stay in MIDI {register[0]}-{register[1]}."
        )
    if "drum" in haystack or "kit" in haystack:
        return "Constraint hints: one coherent kit, clear kick/snare relationship, density follows section energy, fills only into transitions."
    if "guitar" in haystack:
        return "Constraint hints: choose strumming or picking pattern, keep register consistent, and leave rhythmic space for vocals/leads."
    if "synth" in haystack or "pad" in haystack:
        traits = synth_timbre_constraints(role)
        return f"Constraint hints: timbre={traits['waveform_family']}; {traits['filter_envelope']}; density={traits['density']}."
    if "lead" in haystack or "melody" in haystack:
        return "Constraint hints: " + melody_constraint_summary(key=key or "the song key", register=register)
    if "piano" in haystack or "keys" in haystack:
        return "Constraint hints: use chord voicings by register, vary rhythm by section energy, and avoid muddy low clusters."
    return "Constraint hints: match section energy, respect register, repeat a recognizable motif, and leave space for other parts."


def _root_pc(chord: str) -> int:
    cleaned = chord.strip()
    if not cleaned:
        return 0
    root = cleaned[0].upper()
    if len(cleaned) > 1 and cleaned[1] in {"#", "b"}:
        root += cleaned[1]
    return _ROOT_PC.get(root, 0)


def _pitch_in_register(pc: int, register: tuple[int, int]) -> int:
    lo, hi = register
    for pitch in range(lo, hi + 1):
        if pitch % 12 == pc:
            return pitch
    return max(lo, min(hi, lo))
