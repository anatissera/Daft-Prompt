"""Materialise a `BandSpec` into a `SongState`.

Deterministic and side-effect free (does not write files). The caller
renders artifacts via `infrastructure.storage.render_artifacts` after this
returns, so this tool is trivial to test.
"""

from __future__ import annotations

from music_assistant.domain.patch import resolve_patch
from music_assistant.domain.song_state import (
    ChordSpan,
    Header,
    Note,
    Part,
    RosterItem,
    Section,
    SongState,
)
from music_assistant.music.finalize import enforce_bass_downbeats

from ..band_spec import BandSpec


def compose_band(spec: BandSpec, *, request: str = "") -> SongState:
    """Build a `SongState` from a fully-specified `BandSpec`.

    Bass downbeat harmonic enforcement is applied so the exported .mid has a
    grounded bass foundation regardless of any planner drift.
    """
    header = Header(
        genre=spec.genre,
        key=spec.key,
        tempo_bpm=spec.tempo_bpm,
        time_signature=(spec.time_signature_numerator, spec.time_signature_denominator),
        num_bars=spec.num_bars,
        sections=[
            Section(
                name=s.name,
                start_bar=s.start_bar,
                end_bar=s.end_bar,
                energy=s.energy,
            )
            for s in spec.sections
        ],
        chord_progression=[
            ChordSpan(bar=cs.bar, chord=cs.chord) for cs in spec.chord_progression
        ],
    )

    roster: list[RosterItem] = []
    parts: dict[str, Part] = {}
    for inst in spec.instruments:
        program, preset = resolve_patch(inst.patch)
        roster.append(
            RosterItem(
                id=inst.id,
                instrument=inst.instrument,
                patch=inst.patch,
                midi_program=program,
                synth_preset=preset,
                role=inst.role,
                playing_style=inst.playing_style,
                is_drum=inst.is_drum,
            )
        )
        parts[inst.id] = Part(
            instrument_id=inst.id,
            notes=[
                Note(
                    bar=n.bar,
                    start_beat=n.start_beat,
                    pitch=n.pitch,
                    dur=n.dur,
                    velocity=n.velocity,
                )
                for n in inst.notes
            ],
        )

    song = SongState(
        request=request or spec.genre,
        header=header,
        roster=roster,
        parts=parts,
        converged=True,
    )
    enforce_bass_downbeats(song)
    return song
