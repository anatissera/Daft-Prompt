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
    "guitar_harmonics": {"kind": "sampler", "program": 31},
    "gm_synth_bass": {"kind": "sampler", "program": 38},
    "gm_synth_bass_2": {"kind": "sampler", "program": 39},

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
    # GM 23 — the bandoneon-style voice; THE tango lead instrument.
    "tango_accordion": {"kind": "sampler", "program": 23},
    "dulcimer": {"kind": "sampler", "program": 15},

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
    "blown_bottle": {"kind": "sampler", "program": 76},
    "shakuhachi": {"kind": "sampler", "program": 77},
    "whistle": {"kind": "sampler", "program": 78},
    "ocarina": {"kind": "sampler", "program": 79},

    # ---- GM synth leads / pads (80-95) ---------------------------------
    # These are the SAMPLED versions of synth timbres. Prefer the native
    # `supersaw_lead` / `warm_pad` etc. below whenever the intent is a
    # modern EDM sound — they sound fuller and detune correctly.
    "gm_square_lead": {"kind": "sampler", "program": 80},
    "gm_sawtooth_lead": {"kind": "sampler", "program": 81},
    "gm_calliope_lead": {"kind": "sampler", "program": 82},
    "gm_chiff_lead": {"kind": "sampler", "program": 83},
    "gm_charang_lead": {"kind": "sampler", "program": 84},
    "gm_voice_lead": {"kind": "sampler", "program": 85},
    "gm_fifths_lead": {"kind": "sampler", "program": 86},
    "gm_bass_lead": {"kind": "sampler", "program": 87},
    "gm_new_age_pad": {"kind": "sampler", "program": 88},
    "gm_warm_pad": {"kind": "sampler", "program": 89},
    "gm_polysynth_pad": {"kind": "sampler", "program": 90},
    "gm_choir_pad": {"kind": "sampler", "program": 91},
    "gm_bowed_pad": {"kind": "sampler", "program": 92},
    "gm_metallic_pad": {"kind": "sampler", "program": 93},
    "gm_halo_pad": {"kind": "sampler", "program": 94},
    "gm_sweep_pad": {"kind": "sampler", "program": 95},
    "gm_fx_atmosphere": {"kind": "sampler", "program": 99},
    "gm_fx_crystal": {"kind": "sampler", "program": 98},
    "gm_fx_echoes": {"kind": "sampler", "program": 102},

    # ---- Ethnic / world (104-111) ----------------------------------------
    "sitar": {"kind": "sampler", "program": 104},
    "banjo": {"kind": "sampler", "program": 105},
    "shamisen": {"kind": "sampler", "program": 106},
    "koto": {"kind": "sampler", "program": 107},
    "kalimba": {"kind": "sampler", "program": 108},
    "bagpipe": {"kind": "sampler", "program": 109},
    "fiddle": {"kind": "sampler", "program": 110},
    "shanai": {"kind": "sampler", "program": 111},

    # ---- Percussive / melodic percussion (112-119) -------------------------
    "tinkle_bell": {"kind": "sampler", "program": 112},
    "agogo": {"kind": "sampler", "program": 113},
    "steel_drums": {"kind": "sampler", "program": 114},
    "woodblock": {"kind": "sampler", "program": 115},
    "taiko_drum": {"kind": "sampler", "program": 116},
    "melodic_tom": {"kind": "sampler", "program": 117},
    "synth_drum": {"kind": "sampler", "program": 118},

    # ---- Native Tone.js synth presets (modern EDM) ----------------------
    # These skip the sampler entirely and instantiate a Tone.Synth on the
    # frontend. Use for supersaws, sub bass, plucks, warm pads, vocal chops.
    "supersaw_lead": {"kind": "synth", "preset": "supersaw_lead"},
    "sub_bass": {"kind": "synth", "preset": "sub_bass"},
    "pluck": {"kind": "synth", "preset": "pluck"},
    "warm_pad": {"kind": "synth", "preset": "warm_pad"},
    "vocal_fx": {"kind": "synth", "preset": "vocal_fx"},
    # LFO-modulated filter bass — the genre-defining timbre of dubstep /
    # brostep / riddim ("wub wub"). MIDI can't carry filter modulation, so
    # sampled GM basses always play it flat; this preset synthesizes the
    # LFO on the frontend, tempo-synced.
    "wobble_bass": {"kind": "synth", "preset": "wobble_bass"},
}


# The typing alias — pydantic reads this to validate the field. Kept
# hand-maintained so IDEs / static checkers see it; keep it in sync with
# PATCH_SPEC (a small test asserts they agree).
Patch = Literal[
    "acoustic_guitar_nylon", "acoustic_guitar_steel",
    "jazz_electric_guitar", "clean_electric_guitar", "muted_electric_guitar",
    "overdriven_guitar", "distortion_guitar", "guitar_harmonics",
    "acoustic_bass", "electric_bass", "pick_bass", "fretless_bass",
    "slap_bass", "gm_synth_bass", "gm_synth_bass_2",
    "acoustic_grand_piano", "bright_acoustic_piano", "electric_grand_piano",
    "honky_tonk_piano", "electric_piano_rhodes", "electric_piano_dx",
    "harpsichord", "clavinet",
    "celesta", "glockenspiel", "music_box", "vibraphone", "marimba",
    "xylophone", "tubular_bells", "dulcimer",
    "hammond_organ", "percussive_organ", "rock_organ", "church_organ",
    "reed_organ", "accordion", "harmonica", "tango_accordion",
    "violin", "viola", "cello", "contrabass",
    "tremolo_strings", "pizzicato_strings", "orchestral_harp", "timpani",
    "string_ensemble", "gm_synth_strings", "choir_aahs", "voice_oohs",
    "orchestra_hit",
    "trumpet", "trombone", "tuba", "muted_trumpet", "french_horn",
    "brass_section",
    "soprano_sax", "alto_sax", "tenor_sax", "baritone_sax",
    "oboe", "english_horn", "bassoon", "clarinet",
    "piccolo", "flute", "recorder", "pan_flute", "blown_bottle",
    "shakuhachi", "whistle", "ocarina",
    "gm_square_lead", "gm_sawtooth_lead", "gm_calliope_lead", "gm_chiff_lead",
    "gm_charang_lead", "gm_voice_lead", "gm_fifths_lead", "gm_bass_lead",
    "gm_new_age_pad", "gm_warm_pad", "gm_polysynth_pad", "gm_choir_pad",
    "gm_bowed_pad", "gm_metallic_pad", "gm_halo_pad", "gm_sweep_pad",
    "gm_fx_atmosphere", "gm_fx_crystal", "gm_fx_echoes",
    "sitar", "banjo", "shamisen", "koto", "kalimba", "bagpipe", "fiddle",
    "shanai",
    "tinkle_bell", "agogo", "steel_drums", "woodblock", "taiko_drum",
    "melodic_tom", "synth_drum",
    "supersaw_lead", "sub_bass", "pluck", "warm_pad", "vocal_fx",
    "wobble_bass",
]


SynthPreset = Literal[
    "supersaw_lead", "sub_bass", "pluck", "warm_pad", "vocal_fx", "wobble_bass"
]


class UnknownPatchError(ValueError):
    """Raised when the director LLM emits a patch name outside the closed vocab.
    Callers catch this and DROP the offending instrument rather than silently
    substituting grand piano — the latter produced a piano bias across every
    genre where the LLM slipped on the patch name."""

    def __init__(self, patch: str):
        super().__init__(f"unknown patch: {patch!r}")
        self.patch = patch


def resolve_patch(patch: str) -> tuple[int, str | None]:
    """Return (midi_program, synth_preset). midi_program is 0 for synth-only
    patches (frontend won't use it in that case). Raises UnknownPatchError for
    names outside PATCH_SPEC so the caller can drop that instrument instead of
    inheriting the old silent grand-piano fallback."""
    spec = PATCH_SPEC.get(patch)
    if spec is None:
        raise UnknownPatchError(patch)
    if spec["kind"] == "synth":
        return 0, spec["preset"]
    return spec["program"], None


# Sanity check exposed for a small unit test.
def patch_literal_covers_spec() -> bool:
    return set(get_args(Patch)) == set(PATCH_SPEC.keys())


# ---------------------------------------------------------------------------
# instrument-name ↔ patch consistency
# ---------------------------------------------------------------------------
#
# The skeleton schema carries BOTH a free-text `instrument` (display name)
# and a closed-vocab `patch` (the sound). LLMs occasionally desynchronise
# them — `instrument="guitar_rhythm"` with `patch="electric_grand_piano"` —
# which is how "rock guitars sometimes sound like pianos". This is a pure
# consistency repair between two fields the model itself emitted; it maps
# no genres and invents no instruments.

# Instrument families: which vocab patches legitimately cover a family, and
# the keywords in a free-text name that identify it. Order matters — more
# specific families (e.g. bass before guitar is unnecessary since keywords
# differ, but "synth" is checked last so "synth bass" hits bass first).
_FAMILIES: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    # (family, name keywords, member patches)
    ("bass", ("bass", "bajo", "sub"), (
        "acoustic_bass", "electric_bass", "pick_bass", "fretless_bass",
        "slap_bass", "gm_synth_bass", "gm_synth_bass_2", "sub_bass",
        "wobble_bass", "contrabass", "tuba", "gm_bass_lead",
    )),
    ("guitar", ("guitar", "guitarra"), (
        "acoustic_guitar_nylon", "acoustic_guitar_steel",
        "jazz_electric_guitar", "clean_electric_guitar",
        "muted_electric_guitar", "overdriven_guitar", "distortion_guitar",
        "guitar_harmonics",
    )),
    ("piano", ("piano", "keys", "rhodes", "keyboard"), (
        "acoustic_grand_piano", "bright_acoustic_piano",
        "electric_grand_piano", "honky_tonk_piano", "electric_piano_rhodes",
        "electric_piano_dx", "harpsichord", "clavinet",
    )),
    ("organ", ("organ", "hammond", "órgano", "organo"), (
        "hammond_organ", "percussive_organ", "rock_organ", "church_organ",
        "reed_organ",
    )),
    ("accordion", ("accordion", "bandoneon", "bandoneón", "acordeón", "acordeon"), (
        "accordion", "tango_accordion", "harmonica",
    )),
    ("violin", ("violin", "violín", "fiddle", "viola", "cello", "strings", "cuerdas"), (
        "violin", "viola", "cello", "contrabass", "fiddle",
        "tremolo_strings", "pizzicato_strings", "string_ensemble",
        "gm_synth_strings", "orchestral_harp",
    )),
    ("brass", ("trumpet", "trombone", "horn", "brass", "trompeta", "tuba"), (
        "trumpet", "trombone", "tuba", "muted_trumpet", "french_horn",
        "brass_section",
    )),
    ("sax", ("sax",), (
        "soprano_sax", "alto_sax", "tenor_sax", "baritone_sax",
    )),
    ("flute", ("flute", "flauta", "piccolo", "whistle", "ocarina", "pan"), (
        "piccolo", "flute", "recorder", "pan_flute", "blown_bottle",
        "shakuhachi", "whistle", "ocarina",
    )),
    ("vocal", ("vocal", "voice", "voz", "choir", "coro", "chop"), (
        "choir_aahs", "voice_oohs", "vocal_fx", "gm_choir_pad", "gm_voice_lead",
    )),
    ("pad", ("pad", "atmosphere", "atmos", "texture"), (
        "warm_pad", "gm_new_age_pad", "gm_warm_pad", "gm_polysynth_pad",
        "gm_choir_pad", "gm_bowed_pad", "gm_metallic_pad", "gm_halo_pad",
        "gm_sweep_pad", "gm_fx_atmosphere",
    )),
    ("lead_synth", ("lead", "saw", "arp", "synth", "pluck", "stab"), (
        "supersaw_lead", "pluck", "gm_square_lead", "gm_sawtooth_lead",
        "gm_calliope_lead", "gm_chiff_lead", "gm_charang_lead",
        "gm_voice_lead", "gm_fifths_lead", "gm_bass_lead",
    )),
]

# Per-family default when the emitted patch is outside the family: adjectives
# in the name refine the pick; otherwise the family's most neutral member.
_GUITAR_ADJECTIVES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("dist", "metal", "heavy", "power"), "distortion_guitar"),
    (("overdrive", "over", "crunch", "rock"), "overdriven_guitar"),
    (("nylon", "classical", "spanish", "flamenco"), "acoustic_guitar_nylon"),
    (("acoustic", "steel", "folk"), "acoustic_guitar_steel"),
    (("jazz",), "jazz_electric_guitar"),
    (("muted", "mute", "funk"), "muted_electric_guitar"),
)
_FAMILY_DEFAULTS: dict[str, str] = {
    "bass": "electric_bass",
    "guitar": "clean_electric_guitar",
    "piano": "acoustic_grand_piano",
    "organ": "hammond_organ",
    "accordion": "tango_accordion",
    "violin": "violin",
    "brass": "trumpet",
    "sax": "alto_sax",
    "flute": "flute",
    "vocal": "choir_aahs",
    "pad": "warm_pad",
    "lead_synth": "gm_sawtooth_lead",
}


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def reconcile_patch(instrument_name: str, patch: str) -> str:
    """Return a patch consistent with the human-readable instrument name.

    - If the name itself IS a vocab patch (normalized), trust the name.
    - If the name clearly belongs to a family and the emitted patch does
      not, repair to a family member (adjective-refined for guitars).
    - Otherwise keep the emitted patch — the name may be a role nickname
      ("wobble", "chops") where the patch is the real signal.
    """
    name_n = _normalize_name(instrument_name)
    if not name_n:
        return patch
    if name_n in PATCH_SPEC and name_n != patch:
        return name_n
    for family, keywords, members in _FAMILIES:
        if any(kw in name_n for kw in keywords):
            if patch in members:
                return patch  # already consistent
            if family == "guitar":
                for adjectives, pick in _GUITAR_ADJECTIVES:
                    if any(a in name_n for a in adjectives):
                        return pick
            return _FAMILY_DEFAULTS[family]
    return patch
