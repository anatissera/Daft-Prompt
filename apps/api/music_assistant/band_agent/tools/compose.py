"""Materialise a `BandSpec` into a `SongState`.

Deterministic and side-effect free (does not write files). The caller
renders artifacts via `infrastructure.storage.render_artifacts` after this
returns, so this tool is trivial to test.
"""

from __future__ import annotations

from typing import Any, Optional

from music_assistant.domain.patch import UnknownPatchError, resolve_patch
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
from music_assistant.music.theory import beats_per_bar as _beats_per_bar

from ..band_spec import BandSpec
from .drums import synthesize_drum_notes


def compose_band(
    spec: BandSpec,
    *,
    request: str = "",
    groove: Optional[dict[str, Any]] = None,
) -> SongState:
    """Build a `SongState` from a fully-specified `BandSpec`.

    Drum instruments (`is_drum=True`) with an empty note list are filled from
    `groove["pattern_by_channel"]` when supplied; otherwise a default
    four-on-the-floor is used. This is how we keep drums out of the LLM
    token budget without losing musicality — the corpus groove is a real
    DAW-recorded pattern.

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
        # Floor duration so a stray dur=0 from a chatty LLM still produces
        # an audible note (0.05 quarter-note ≈ a 64th-note staccato).
        notes: list[Note] = [
            Note(
                bar=n.bar,
                start_beat=n.start_beat,
                pitch=n.pitch,
                dur=max(0.05, n.dur),
                velocity=n.velocity,
            )
            for n in inst.notes
        ]
        if inst.is_drum and not notes:
            pattern = (groove or {}).get("pattern_by_channel")
            notes = synthesize_drum_notes(
                pattern,
                num_bars=spec.num_bars,
                beats_per_bar=_beats_per_bar(
                    (spec.time_signature_numerator, spec.time_signature_denominator)
                ),
            )
        # Skip silent non-drum instruments: their fill call failed and the
        # roster would otherwise lie to the frontend about what's playing.
        if not notes and not inst.is_drum:
            continue
        # Drop instruments whose patch is unrecognised — the old resolve_patch
        # silently substituted grand piano, which drove a piano bias whenever
        # the LLM slipped on the vocab.
        try:
            program, preset = resolve_patch(inst.patch)
        except UnknownPatchError:
            continue
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
        parts[inst.id] = Part(instrument_id=inst.id, notes=notes)

    song = SongState(
        request=request or spec.genre,
        header=header,
        roster=roster,
        parts=parts,
        converged=True,
    )
    enforce_bass_downbeats(song)
    return song
