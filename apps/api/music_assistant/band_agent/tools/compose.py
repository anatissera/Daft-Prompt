"""Materialise a `BandSpec` into a `SongState`.

Deterministic and side-effect free (does not write files). The caller
renders artifacts via `infrastructure.storage.render_artifacts` after this
returns, so this tool is trivial to test.
"""

from __future__ import annotations

from typing import Any, Optional

from music_assistant.domain.patch import (
    UnknownPatchError,
    family_pitch_range,
    reconcile_patch,
    resolve_patch,
)
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
from .groove_enforce import enforce_density, enforce_grid, enforce_register


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
        # Propagate the director's groove commitment — it used to be lost
        # here, leaving Header.rhythmic_feel empty for the UI and every
        # downstream consumer (seeded fallbacks, audits).
        rhythmic_feel=spec.rhythmic_feel,
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

    beats_per_bar = _beats_per_bar(
        (spec.time_signature_numerator, spec.time_signature_denominator)
    )
    roster: list[RosterItem] = []
    parts: dict[str, Part] = {}
    for inst in spec.instruments:
        # Make the director's rhythmic commitments BINDING: snap/drop notes
        # off the instrument's committed onset grid, then prune anything over
        # its per-bar density budget. Prose descriptions of groove kept
        # getting lost between the director and the smaller fill models;
        # these two deterministic passes are what turns "dembow" or "sparse
        # blues" from an adjective into arithmetic.
        #
        # DRUMS ARE EXEMPT from the grid: a kit is several voices (kick,
        # snare, hats) with DIFFERENT patterns, and a single union grid is
        # too coarse — an under-committed grid deleted the snare wholesale
        # (measured on a reggaeton run). The kit's groove is governed by
        # the per-voice patterns in the drum fill prompt instead. Density
        # still applies to everyone.
        plan_notes = inst.notes
        if not inst.is_drum:
            plan_notes = enforce_grid(
                plan_notes, inst.onset_grid,
                beats_per_bar=beats_per_bar, instrument_id=inst.id,
            )
        plan_notes = enforce_density(
            plan_notes, inst.max_notes_per_bar, instrument_id=inst.id,
        )
        # Register enforcement (octave folding). A bass line wandering up to
        # G#5 doesn't sound like "a creative bass" — it sounds like a broken
        # piano, because bass samples pitched far above their capture range
        # lose all body. Use the director's committed range; when it left
        # (0, 127), fall back to the family's PHYSICAL range.
        if not inst.is_drum:
            low, high = inst.pitch_low, inst.pitch_high
            if low <= 0 and high >= 127:
                fam = family_pitch_range(inst.instrument, inst.patch)
                if fam:
                    low, high = fam
            plan_notes = enforce_register(
                plan_notes, low, high, instrument_id=inst.id,
            )
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
            for n in plan_notes
        ]
        if inst.is_drum and not notes:
            pattern = (groove or {}).get("pattern_by_channel")
            notes = synthesize_drum_notes(
                pattern,
                num_bars=spec.num_bars,
                beats_per_bar=beats_per_bar,
            )
        # Skip silent non-drum instruments: their fill call failed and the
        # roster would otherwise lie to the frontend about what's playing.
        if not notes and not inst.is_drum:
            continue
        # Repair name↔patch desync BEFORE resolving: the LLM occasionally
        # emits instrument="guitar_rhythm" with patch="electric_grand_piano",
        # which is how rock guitars ended up sounding like pianos. This is a
        # consistency check between two fields the model itself emitted —
        # no genre mapping involved.
        patch = reconcile_patch(inst.instrument, inst.patch)
        if patch != inst.patch:
            import logging
            logging.getLogger(__name__).warning(
                "band_agent: patch reconciled for %s: %r -> %r (name %r)",
                inst.id, inst.patch, patch, inst.instrument,
            )
        # Drop instruments whose patch is unrecognised — the old resolve_patch
        # silently substituted grand piano, which drove a piano bias whenever
        # the LLM slipped on the vocab.
        try:
            program, preset = resolve_patch(patch)
        except UnknownPatchError:
            continue
        roster.append(
            RosterItem(
                id=inst.id,
                instrument=inst.instrument,
                patch=patch,
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
