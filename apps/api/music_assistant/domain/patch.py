"""Semantic patch vocabulary.

The composition pipeline used to make the director LLM emit a raw GM program
number (0-127) alongside the human name of the instrument. That is a memory
task the LLM slipped on constantly ("String Ensemble 1" → 4 = Electric Piano,
"Strings 1" → 101 = FX 6 Goblins). The mismatches broke playback because the
sampler folder is picked by the number, not the name.

This module replaces that with a closed vocabulary of semantic patch names.
The director picks a name from `Patch` (Literal), the backend deterministically
resolves it to either:
  - a FluidR3 GM sampler patch (via `program`) — traditional/acoustic patches
  - a native Tone.js synth preset — modern EDM archetypes GM can't render

Adding a new patch is 3 lines: one entry in `PATCH_SPEC` (below) plus a matching
literal in the generated `Patch` typing alias (auto-derived).

Drums are still flagged with `is_drum=True` on the roster item — the drum kit
is a channel-10 fixed mapping, not a patch.
"""

from __future__ import annotations

from typing import Literal, get_args

# ---------------------------------------------------------------------------
# The mapping. Adding a new instrument = adding a row here + adding the string
# to the `Patch` alias below. Nothing else changes downstream.
# ---------------------------------------------------------------------------

# A sampler entry maps to a GM program; the frontend picks the FluidR3 folder
# by that number. A synth entry names a Tone.js preset that already exists in
# `apps/web/lib/synthPresets.ts`.

PATCH_SPEC: dict[str, dict] = {
    # ---- Guitar (24-31) --------------------------------------------------
    "acoustic_guitar_nylon": {"kind": "sampler", "program": 24},
    "acoustic_guitar_steel": {"kind": "sampler", "program": 25},
    "jazz_electric_guitar": {"kind": "sampler", "program": 26},
    "clean_electric_guitar": {"kind": "sampler", "program": 27},
    "muted_electric_guitar": {"kind": "sampler", "program": 28},
    "overdriven_guitar": {"kind": "sampler", "program": 29},
    "distortion_guitar": {"kind": "sampler", "program": 30},

    # ---- Bass (32-39) ----------------------------------------------------
    "acoustic_bass": {"kind": "sampler", "program": 32},
    "electric_bass": {"kind": "sampler", "program": 33},
    "pick_bass": {"kind": "sampler", "program": 34},
    "fretless_bass": {"kind": "sampler", "program": 35},
    "slap_bass": {"kind": "sampler", "program": 36},
    "gm_synth_bass": {"kind": "sampler", "program": 38},

    # ---- Piano / Keys (0-7) ---------------------------------------------
    "acoustic_grand_piano": {"kind": "sampler", "program": 0},
    "bright_acoustic_piano": {"kind": "sampler", "program": 1},
    "electric_grand_piano": {"kind": "sampler", "program": 2},
    "honky_tonk_piano": {"kind": "sampler", "program": 3},
    "electric_piano_rhodes": {"kind": "sampler", "program": 4},
    "electric_piano_dx": {"kind": "sampler", "program": 5},
    "harpsichord": {"kind": "sampler", "program": 6},
    "clavinet": {"kind": "sampler", "program": 7},

    # ---- Chromatic percussion (8-15) ------------------------------------
    "celesta": {"kind": "sampler", "program": 8},
    "glockenspiel": {"kind": "sampler", "program": 9},
    "music_box": {"kind": "sampler", "program": 10},
    "vibraphone": {"kind": "sampler", "program": 11},
    "marimba": {"kind": "sampler", "program": 12},
    "xylophone": {"kind": "sampler", "program": 13},
    "tubular_bells": {"kind": "sampler", "program": 14},

    # ---- Organ / Accordion (16-23) --------------------------------------
    "hammond_organ": {"kind": "sampler", "program": 16},
    "percussive_organ": {"kind": "sampler", "program": 17},
    "rock_organ": {"kind": "sampler", "program": 18},
    "church_organ": {"kind": "sampler", "program": 19},
    "reed_organ": {"kind": "sampler", "program": 20},
    "accordion": {"kind": "sampler", "program": 21},
    "harmonica": {"kind": "sampler", "program": 22},

    # ---- Solo strings (40-47) -------------------------------------------
    "violin": {"kind": "sampler", "program": 40},
    "viola": {"kind": "sampler", "program": 41},
    "cello": {"kind": "sampler", "program": 42},
    "contrabass": {"kind": "sampler", "program": 43},
    "tremolo_strings": {"kind": "sampler", "program": 44},
    "pizzicato_strings": {"kind": "sampler", "program": 45},
    "orchestral_harp": {"kind": "sampler", "program": 46},
    "timpani": {"kind": "sampler", "program": 47},

    # ---- Ensemble strings / choir (48-55) -------------------------------
    "string_ensemble": {"kind": "sampler", "program": 48},
    "gm_synth_strings": {"kind": "sampler", "program": 50},
    "choir_aahs": {"kind": "sampler", "program": 52},
    "voice_oohs": {"kind": "sampler", "program": 53},
    "orchestra_hit": {"kind": "sampler", "program": 55},

    # ---- Brass (56-63) --------------------------------------------------
    "trumpet": {"kind": "sampler", "program": 56},
    "trombone": {"kind": "sampler", "program": 57},
    "tuba": {"kind": "sampler", "program": 58},
    "muted_trumpet": {"kind": "sampler", "program": 59},
    "french_horn": {"kind": "sampler", "program": 60},
    "brass_section": {"kind": "sampler", "program": 61},

    # ---- Reed (64-71) ---------------------------------------------------
    "soprano_sax": {"kind": "sampler", "program": 64},
    "alto_sax": {"kind": "sampler", "program": 65},
    "tenor_sax": {"kind": "sampler", "program": 66},
    "baritone_sax": {"kind": "sampler", "program": 67},
    "oboe": {"kind": "sampler", "program": 68},
    "english_horn": {"kind": "sampler", "program": 69},
    "bassoon": {"kind": "sampler", "program": 70},
    "clarinet": {"kind": "sampler", "program": 71},

    # ---- Pipe (72-79) ---------------------------------------------------
    "piccolo": {"kind": "sampler", "program": 72},
    "flute": {"kind": "sampler", "program": 73},
    "recorder": {"kind": "sampler", "program": 74},
    "pan_flute": {"kind": "sampler", "program": 75},
    "shakuhachi": {"kind": "sampler", "program": 77},

    # ---- GM synth leads / pads (80-95) ---------------------------------
    # These are the SAMPLED versions of synth timbres. Prefer the native
    # `supersaw_lead` / `warm_pad` etc. below whenever the intent is a
    # modern EDM sound — they sound fuller and detune correctly.
    "gm_square_lead": {"kind": "sampler", "program": 80},
    "gm_sawtooth_lead": {"kind": "sampler", "program": 81},
    "gm_new_age_pad": {"kind": "sampler", "program": 88},
    "gm_warm_pad": {"kind": "sampler", "program": 89},

    # ---- Ethnic (104-111) -----------------------------------------------
    "sitar": {"kind": "sampler", "program": 104},
    "banjo": {"kind": "sampler", "program": 105},
    "kalimba": {"kind": "sampler", "program": 108},
    "steel_drums": {"kind": "sampler", "program": 114},

    # ---- Native Tone.js synth presets (modern EDM) ----------------------
    # These skip the sampler entirely and instantiate a Tone.Synth on the
    # frontend. Use for supersaws, sub bass, plucks, warm pads, vocal chops.
    "supersaw_lead": {"kind": "synth", "preset": "supersaw_lead"},
    "sub_bass": {"kind": "synth", "preset": "sub_bass"},
    "pluck": {"kind": "synth", "preset": "pluck"},
    "warm_pad": {"kind": "synth", "preset": "warm_pad"},
    "vocal_fx": {"kind": "synth", "preset": "vocal_fx"},
}


# The typing alias — pydantic reads this to validate the field. Kept
# hand-maintained so IDEs / static checkers see it; keep it in sync with
# PATCH_SPEC (a small test asserts they agree).
Patch = Literal[
    "acoustic_guitar_nylon", "acoustic_guitar_steel",
    "jazz_electric_guitar", "clean_electric_guitar", "muted_electric_guitar",
    "overdriven_guitar", "distortion_guitar",
    "acoustic_bass", "electric_bass", "pick_bass", "fretless_bass",
    "slap_bass", "gm_synth_bass",
    "acoustic_grand_piano", "bright_acoustic_piano", "electric_grand_piano",
    "honky_tonk_piano", "electric_piano_rhodes", "electric_piano_dx",
    "harpsichord", "clavinet",
    "celesta", "glockenspiel", "music_box", "vibraphone", "marimba",
    "xylophone", "tubular_bells",
    "hammond_organ", "percussive_organ", "rock_organ", "church_organ",
    "reed_organ", "accordion", "harmonica",
    "violin", "viola", "cello", "contrabass",
    "tremolo_strings", "pizzicato_strings", "orchestral_harp", "timpani",
    "string_ensemble", "gm_synth_strings", "choir_aahs", "voice_oohs",
    "orchestra_hit",
    "trumpet", "trombone", "tuba", "muted_trumpet", "french_horn",
    "brass_section",
    "soprano_sax", "alto_sax", "tenor_sax", "baritone_sax",
    "oboe", "english_horn", "bassoon", "clarinet",
    "piccolo", "flute", "recorder", "pan_flute", "shakuhachi",
    "gm_square_lead", "gm_sawtooth_lead", "gm_new_age_pad", "gm_warm_pad",
    "sitar", "banjo", "kalimba", "steel_drums",
    "supersaw_lead", "sub_bass", "pluck", "warm_pad", "vocal_fx",
]


SynthPreset = Literal["supersaw_lead", "sub_bass", "pluck", "warm_pad", "vocal_fx"]


def resolve_patch(patch: str) -> tuple[int, str | None]:
    """Return (midi_program, synth_preset). midi_program is 0 for synth-only
    patches (frontend won't use it in that case). Unknown patches fall back to
    (0, None) — grand piano — so downstream never crashes on a bad literal."""
    spec = PATCH_SPEC.get(patch)
    if spec is None:
        return 0, None
    if spec["kind"] == "synth":
        return 0, spec["preset"]
    return spec["program"], None


# Sanity check exposed for a small unit test.
def patch_literal_covers_spec() -> bool:
    return set(get_args(Patch)) == set(PATCH_SPEC.keys())
