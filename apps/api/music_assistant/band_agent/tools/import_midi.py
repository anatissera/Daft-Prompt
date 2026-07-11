"""Import an external `.mid` file as a `SongState`.

Uses `music.read_midi.read_midi` to parse the file, then translates every
track's GM program number back into a `Patch` from our closed vocabulary
(the reverse of `resolve_patch`). Drum tracks always resolve to a synthetic
`drum_kit` roster item — the frontend routes them through GM channel 10.

Programs we don't cover verbatim fall back to the nearest patch in the same
GM family (guitar → distortion_guitar, brass → brass_section, etc.). That
keeps every imported track playable in the browser and exportable to .mid
without ever leaving the Patch vocabulary.
"""

from __future__ import annotations

from pathlib import Path

from music_assistant.domain.patch import PATCH_SPEC, Patch, resolve_patch
from music_assistant.domain.song_state import (
    ChordSpan,
    Header,
    Note,
    Part,
    RosterItem,
    Section,
    SongState,
)
from music_assistant.music.read_midi import ReadSong, read_midi


# Reverse map: GM program → first matching Patch name (sampler-kind entries
# only, since synth-kind patches don't correspond to a GM program).
_PROGRAM_TO_PATCH: dict[int, Patch] = {}
for _name, _spec in PATCH_SPEC.items():
    if _spec.get("kind") == "sampler" and _spec["program"] not in _PROGRAM_TO_PATCH:
        _PROGRAM_TO_PATCH[_spec["program"]] = _name  # type: ignore[assignment]


# When a program isn't in our vocabulary, pick the closest family member.
# Families roughly follow GM's 8-program groupings (0-7 piano, 8-15 chromatic
# perc, 16-23 organ, 24-31 guitar, 32-39 bass, 40-47 strings, 48-55 ensemble,
# 56-63 brass, 64-71 reed, 72-79 pipe, 80-87 synth lead, 88-95 synth pad,
# 96-103 fx, 104-111 ethnic).
_FAMILY_FALLBACK: dict[int, Patch] = {
    0: "acoustic_grand_piano",
    1: "acoustic_grand_piano",
    2: "vibraphone",
    3: "hammond_organ",
    4: "distortion_guitar",
    5: "electric_bass",
    6: "violin",
    7: "string_ensemble",
    8: "trumpet",
    9: "alto_sax",
    10: "flute",
    11: "gm_sawtooth_lead",
    12: "gm_warm_pad",
    13: "gm_warm_pad",         # 96-103 fx → warm pad as safe neutral
    14: "sitar",
}


def _patch_for_program(program: int) -> Patch:
    """Map a GM program (0-127) to the best available `Patch`. Exact match
    first; else fall back to the family representative."""
    if program in _PROGRAM_TO_PATCH:
        return _PROGRAM_TO_PATCH[program]
    return _FAMILY_FALLBACK.get(program // 8, "acoustic_grand_piano")


def import_midi(path: str | Path, *, request: str = "") -> SongState:
    """Convert a `.mid` file at `path` into a `SongState`.

    Empty tracks (a MIDI file often has metadata-only tracks) are dropped.
    Bar / start_beat / dur come pre-quantised from `read_midi`. No LLM in
    the loop — the output is bit-exact to what the MIDI says, modulo the
    program→patch mapping which is deterministic."""
    song: ReadSong = read_midi(str(path))
    header = Header(
        genre="imported",
        key="C major",  # unknown; extract_key exists but is best-effort
        tempo_bpm=song.tempo_bpm,
        time_signature=song.time_signature,
        num_bars=song.num_bars,
        sections=[Section(name="Main", start_bar=0, end_bar=max(0, song.num_bars - 1))],
        chord_progression=[ChordSpan(bar=0, chord="")],
    )
    roster: list[RosterItem] = []
    parts: dict[str, Part] = {}
    used_ids: set[str] = set()
    for idx, track in enumerate(song.tracks):
        if not track.notes:
            continue
        if track.is_drum:
            patch: Patch = "gm_synth_bass"  # placeholder; drums route to ch10
            base_id = "drums"
            instrument_name = "drums"
        else:
            patch = _patch_for_program(track.program)
            base_id = _slug(track.name) or patch
            instrument_name = track.name or patch.replace("_", " ")
        inst_id = _unique(base_id, used_ids)
        used_ids.add(inst_id)
        program, preset = resolve_patch(patch)
        roster.append(
            RosterItem(
                id=inst_id,
                instrument=instrument_name,
                patch=patch,
                midi_program=program,
                synth_preset=preset,
                role="drums" if track.is_drum else "",
                is_drum=track.is_drum,
            )
        )
        parts[inst_id] = Part(
            instrument_id=inst_id,
            notes=[
                Note(
                    bar=n.bar,
                    start_beat=n.start_beat,
                    pitch=n.pitch,
                    dur=max(0.05, n.dur),
                    velocity=n.velocity,
                )
                for n in track.notes
            ],
        )
    return SongState(
        request=request or "imported midi",
        header=header,
        roster=roster,
        parts=parts,
        converged=True,
    )


def _slug(name: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return s[:20]


def _unique(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    for i in range(2, 100):
        cand = f"{base}_{i}"
        if cand not in used:
            return cand
    return base + "_x"
