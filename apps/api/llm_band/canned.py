"""A hardcoded, musically-valid `SongState` used by the Phase 1 walking skeleton.

No LLM is involved yet — this proves the full pipe (web -> api -> render ->
artifact -> browser playback/score) before any agent exists. Later phases replace
`canned_song()` with the director + instrument agents.
"""

from __future__ import annotations

from .schema import (
    ChordSpan,
    Header,
    Note,
    Part,
    RosterItem,
    Section,
    SongState,
)

_BEATS_PER_BAR = 4

# A simple 4-bar I-V-vi-IV in C major: C  G  Am  F
_CHORDS = ["C", "G", "Am", "F"]
# root MIDI pitches for the bass (C2..) per bar
_BASS_ROOTS = [36, 43, 45, 41]
# a plain quarter-note melody per bar (chord tones), one octave up
_MELODY = [
    [60, 64, 67, 64],  # C  E  G  E
    [62, 67, 71, 67],  # D  G  B  G
    [60, 64, 69, 64],  # C  E  A  E
    [60, 65, 69, 65],  # C  F  A  F
]


def _melody_part() -> Part:
    notes: list[Note] = []
    for bar in range(4):
        for beat, pitch in enumerate(_MELODY[bar]):
            notes.append(Note(bar=bar, start_beat=float(beat), pitch=pitch, dur=1.0, velocity=92))
    return Part(
        instrument_id="lead",
        notes=notes,
        notes_summary="quarter-note chord-tone melody, one per beat",
    )


def _bass_part() -> Part:
    notes: list[Note] = []
    for bar in range(4):
        root = _BASS_ROOTS[bar]
        # root on beats 1 and 3
        notes.append(Note(bar=bar, start_beat=0.0, pitch=root, dur=1.0, velocity=100))
        notes.append(Note(bar=bar, start_beat=2.0, pitch=root, dur=1.0, velocity=96))
    return Part(
        instrument_id="bass",
        notes=notes,
        notes_summary="root on beats 1 and 3",
    )


def _drums_part() -> Part:
    # GM percussion: 36 = kick, 38 = snare, 42 = closed hat
    notes: list[Note] = []
    for bar in range(4):
        for beat in range(_BEATS_PER_BAR):
            notes.append(Note(bar=bar, start_beat=float(beat), pitch=42, dur=0.5, velocity=70))
            if beat % 2 == 0:
                notes.append(Note(bar=bar, start_beat=float(beat), pitch=36, dur=0.5, velocity=100))
            else:
                notes.append(Note(bar=bar, start_beat=float(beat), pitch=38, dur=0.5, velocity=100))
    return Part(instrument_id="drums", notes=notes, notes_summary="four-on-the-floor")


def canned_song(request: str = "demo") -> SongState:
    header = Header(
        genre="demo",
        key="C major",
        tempo_bpm=100.0,
        time_signature=(4, 4),
        num_bars=4,
        sections=[Section(name="loop", start_bar=0, end_bar=4)],
        chord_progression=[ChordSpan(bar=i, chord=_CHORDS[i]) for i in range(4)],
    )
    roster = [
        RosterItem(id="lead", instrument="acoustic_grand_piano", midi_program=0,
                   midi_range=(48, 84), role="melody", is_drum=False),
        RosterItem(id="bass", instrument="electric_bass", midi_program=33,
                   midi_range=(28, 55), role="root motion", is_drum=False),
        RosterItem(id="drums", instrument="drum_kit", midi_program=0,
                   midi_range=(35, 81), role="four-on-the-floor", is_drum=True),
    ]
    parts = {
        "lead": _melody_part(),
        "bass": _bass_part(),
        "drums": _drums_part(),
    }
    return SongState(
        request=request,
        header=header,
        roster=roster,
        parts=parts,
        converged=True,
    )
