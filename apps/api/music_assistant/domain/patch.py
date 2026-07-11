"""Closed semantic vocabulary for instrument patches.

Directors can choose a musical patch name instead of memorizing General MIDI
program numbers. The backend resolves the semantic name deterministically while
keeping a GM fallback program for the current MIDI and browser playback paths.
"""

from __future__ import annotations

from typing import Literal, get_args


PATCH_SPEC: dict[str, dict[str, int | str]] = {
    # Guitar family.
    "acoustic_guitar_nylon": {"kind": "sampler", "program": 24},
    "acoustic_guitar_steel": {"kind": "sampler", "program": 25},
    "jazz_electric_guitar": {"kind": "sampler", "program": 26},
    "clean_electric_guitar": {"kind": "sampler", "program": 27},
    "muted_electric_guitar": {"kind": "sampler", "program": 28},
    "overdriven_guitar": {"kind": "sampler", "program": 29},
    "distortion_guitar": {"kind": "sampler", "program": 30},
    "guitar_harmonics": {"kind": "sampler", "program": 31},
    # Bass family.
    "acoustic_bass": {"kind": "sampler", "program": 32},
    "electric_bass": {"kind": "sampler", "program": 33},
    "pick_bass": {"kind": "sampler", "program": 34},
    "fretless_bass": {"kind": "sampler", "program": 35},
    "slap_bass": {"kind": "sampler", "program": 36},
    "gm_synth_bass": {"kind": "sampler", "program": 38},
    "gm_synth_bass_2": {"kind": "sampler", "program": 39},
    # Piano and keys.
    "acoustic_grand_piano": {"kind": "sampler", "program": 0},
    "bright_acoustic_piano": {"kind": "sampler", "program": 1},
    "electric_grand_piano": {"kind": "sampler", "program": 2},
    "honky_tonk_piano": {"kind": "sampler", "program": 3},
    "electric_piano_rhodes": {"kind": "sampler", "program": 4},
    "electric_piano_dx": {"kind": "sampler", "program": 5},
    "harpsichord": {"kind": "sampler", "program": 6},
    "clavinet": {"kind": "sampler", "program": 7},
    "celesta": {"kind": "sampler", "program": 8},
    "glockenspiel": {"kind": "sampler", "program": 9},
    "music_box": {"kind": "sampler", "program": 10},
    "vibraphone": {"kind": "sampler", "program": 11},
    "marimba": {"kind": "sampler", "program": 12},
    "xylophone": {"kind": "sampler", "program": 13},
    "tubular_bells": {"kind": "sampler", "program": 14},
    "dulcimer": {"kind": "sampler", "program": 15},
    # Organs and free reeds.
    "hammond_organ": {"kind": "sampler", "program": 16},
    "percussive_organ": {"kind": "sampler", "program": 17},
    "rock_organ": {"kind": "sampler", "program": 18},
    "church_organ": {"kind": "sampler", "program": 19},
    "reed_organ": {"kind": "sampler", "program": 20},
    "accordion": {"kind": "sampler", "program": 21},
    "harmonica": {"kind": "sampler", "program": 22},
    "tango_accordion": {"kind": "sampler", "program": 23},
    # Strings, choir, and orchestra.
    "violin": {"kind": "sampler", "program": 40},
    "viola": {"kind": "sampler", "program": 41},
    "cello": {"kind": "sampler", "program": 42},
    "contrabass": {"kind": "sampler", "program": 43},
    "tremolo_strings": {"kind": "sampler", "program": 44},
    "pizzicato_strings": {"kind": "sampler", "program": 45},
    "orchestral_harp": {"kind": "sampler", "program": 46},
    "timpani": {"kind": "sampler", "program": 47},
    "string_ensemble": {"kind": "sampler", "program": 48},
    "gm_synth_strings": {"kind": "sampler", "program": 50},
    "choir_aahs": {"kind": "sampler", "program": 52},
    "voice_oohs": {"kind": "sampler", "program": 53},
    "orchestra_hit": {"kind": "sampler", "program": 55},
    # Brass, reeds, and pipe instruments.
    "trumpet": {"kind": "sampler", "program": 56},
    "trombone": {"kind": "sampler", "program": 57},
    "tuba": {"kind": "sampler", "program": 58},
    "muted_trumpet": {"kind": "sampler", "program": 59},
    "french_horn": {"kind": "sampler", "program": 60},
    "brass_section": {"kind": "sampler", "program": 61},
    "soprano_sax": {"kind": "sampler", "program": 64},
    "alto_sax": {"kind": "sampler", "program": 65},
    "tenor_sax": {"kind": "sampler", "program": 66},
    "baritone_sax": {"kind": "sampler", "program": 67},
    "oboe": {"kind": "sampler", "program": 68},
    "english_horn": {"kind": "sampler", "program": 69},
    "bassoon": {"kind": "sampler", "program": 70},
    "clarinet": {"kind": "sampler", "program": 71},
    "piccolo": {"kind": "sampler", "program": 72},
    "flute": {"kind": "sampler", "program": 73},
    "recorder": {"kind": "sampler", "program": 74},
    "pan_flute": {"kind": "sampler", "program": 75},
    "blown_bottle": {"kind": "sampler", "program": 76},
    "shakuhachi": {"kind": "sampler", "program": 77},
    "whistle": {"kind": "sampler", "program": 78},
    "ocarina": {"kind": "sampler", "program": 79},
    # GM synth lead, pad, and texture programs.
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
    "gm_fx_crystal": {"kind": "sampler", "program": 98},
    "gm_fx_atmosphere": {"kind": "sampler", "program": 99},
    "gm_fx_echoes": {"kind": "sampler", "program": 102},
    # World and melodic percussion.
    "sitar": {"kind": "sampler", "program": 104},
    "banjo": {"kind": "sampler", "program": 105},
    "shamisen": {"kind": "sampler", "program": 106},
    "koto": {"kind": "sampler", "program": 107},
    "kalimba": {"kind": "sampler", "program": 108},
    "bagpipe": {"kind": "sampler", "program": 109},
    "fiddle": {"kind": "sampler", "program": 110},
    "shanai": {"kind": "sampler", "program": 111},
    "tinkle_bell": {"kind": "sampler", "program": 112},
    "agogo": {"kind": "sampler", "program": 113},
    "steel_drums": {"kind": "sampler", "program": 114},
    "woodblock": {"kind": "sampler", "program": 115},
    "taiko_drum": {"kind": "sampler", "program": 116},
    "melodic_tom": {"kind": "sampler", "program": 117},
    "synth_drum": {"kind": "sampler", "program": 118},
    # Native synth targets keep a GM fallback until the frontend synth layer is
    # fully wired to synth_preset.
    "supersaw_lead": {"kind": "synth", "program": 81, "preset": "supersaw_lead"},
    "sub_bass": {"kind": "synth", "program": 38, "preset": "sub_bass"},
    "pluck": {"kind": "synth", "program": 80, "preset": "pluck"},
    "warm_pad": {"kind": "synth", "program": 89, "preset": "warm_pad"},
    "vocal_fx": {"kind": "synth", "program": 85, "preset": "vocal_fx"},
    "wobble_bass": {"kind": "synth", "program": 38, "preset": "wobble_bass"},
}


Patch = Literal[
    "acoustic_guitar_nylon", "acoustic_guitar_steel", "jazz_electric_guitar",
    "clean_electric_guitar", "muted_electric_guitar", "overdriven_guitar",
    "distortion_guitar", "guitar_harmonics", "acoustic_bass", "electric_bass",
    "pick_bass", "fretless_bass", "slap_bass", "gm_synth_bass",
    "gm_synth_bass_2", "acoustic_grand_piano", "bright_acoustic_piano",
    "electric_grand_piano", "honky_tonk_piano", "electric_piano_rhodes",
    "electric_piano_dx", "harpsichord", "clavinet", "celesta", "glockenspiel",
    "music_box", "vibraphone", "marimba", "xylophone", "tubular_bells",
    "dulcimer", "hammond_organ", "percussive_organ", "rock_organ",
    "church_organ", "reed_organ", "accordion", "harmonica", "tango_accordion",
    "violin", "viola", "cello", "contrabass", "tremolo_strings",
    "pizzicato_strings", "orchestral_harp", "timpani", "string_ensemble",
    "gm_synth_strings", "choir_aahs", "voice_oohs", "orchestra_hit",
    "trumpet", "trombone", "tuba", "muted_trumpet", "french_horn",
    "brass_section", "soprano_sax", "alto_sax", "tenor_sax", "baritone_sax",
    "oboe", "english_horn", "bassoon", "clarinet", "piccolo", "flute",
    "recorder", "pan_flute", "blown_bottle", "shakuhachi", "whistle",
    "ocarina", "gm_square_lead", "gm_sawtooth_lead", "gm_calliope_lead",
    "gm_chiff_lead", "gm_charang_lead", "gm_voice_lead", "gm_fifths_lead",
    "gm_bass_lead", "gm_new_age_pad", "gm_warm_pad", "gm_polysynth_pad",
    "gm_choir_pad", "gm_bowed_pad", "gm_metallic_pad", "gm_halo_pad",
    "gm_sweep_pad", "gm_fx_crystal", "gm_fx_atmosphere", "gm_fx_echoes",
    "sitar", "banjo", "shamisen", "koto", "kalimba", "bagpipe", "fiddle",
    "shanai", "tinkle_bell", "agogo", "steel_drums", "woodblock",
    "taiko_drum", "melodic_tom", "synth_drum", "supersaw_lead", "sub_bass",
    "pluck", "warm_pad", "vocal_fx", "wobble_bass",
]

SynthPreset = Literal["supersaw_lead", "sub_bass", "pluck", "warm_pad", "vocal_fx", "wobble_bass"]


class UnknownPatchError(ValueError):
    def __init__(self, patch: str):
        super().__init__(f"unknown patch: {patch!r}")
        self.patch = patch


def resolve_patch(patch: str) -> tuple[int, str | None]:
    """Resolve a semantic patch to (GM program, optional native synth preset)."""
    spec = PATCH_SPEC.get(patch)
    if spec is None:
        raise UnknownPatchError(patch)
    program = int(spec["program"])
    if spec["kind"] == "synth":
        return program, str(spec["preset"])
    return program, None


def patch_literal_covers_spec() -> bool:
    return set(get_args(Patch)) == set(PATCH_SPEC.keys())


def is_native_synth_patch(patch: str | None) -> bool:
    if not patch:
        return False
    spec = PATCH_SPEC.get(patch)
    return bool(spec and spec["kind"] == "synth")


_FAMILIES: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("bass", ("bass", "bajo", "sub"), (
        "acoustic_bass", "electric_bass", "pick_bass", "fretless_bass",
        "slap_bass", "gm_synth_bass", "gm_synth_bass_2", "sub_bass",
        "wobble_bass", "contrabass", "tuba", "gm_bass_lead",
    )),
    ("guitar", ("guitar", "guitarra"), (
        "acoustic_guitar_nylon", "acoustic_guitar_steel", "jazz_electric_guitar",
        "clean_electric_guitar", "muted_electric_guitar", "overdriven_guitar",
        "distortion_guitar", "guitar_harmonics",
    )),
    ("piano", ("piano", "keys", "rhodes", "keyboard"), (
        "acoustic_grand_piano", "bright_acoustic_piano", "electric_grand_piano",
        "honky_tonk_piano", "electric_piano_rhodes", "electric_piano_dx",
        "harpsichord", "clavinet",
    )),
    ("organ", ("organ", "hammond", "organo"), (
        "hammond_organ", "percussive_organ", "rock_organ", "church_organ", "reed_organ",
    )),
    ("strings", ("violin", "fiddle", "viola", "cello", "strings"), (
        "violin", "viola", "cello", "contrabass", "fiddle", "tremolo_strings",
        "pizzicato_strings", "string_ensemble", "gm_synth_strings", "orchestral_harp",
    )),
    ("brass", ("trumpet", "trombone", "horn", "brass", "tuba"), (
        "trumpet", "trombone", "tuba", "muted_trumpet", "french_horn", "brass_section",
    )),
    ("sax", ("sax",), ("soprano_sax", "alto_sax", "tenor_sax", "baritone_sax")),
    ("flute", ("flute", "piccolo", "whistle", "ocarina", "pan"), (
        "piccolo", "flute", "recorder", "pan_flute", "blown_bottle",
        "shakuhachi", "whistle", "ocarina",
    )),
    ("vocal", ("vocal", "voice", "choir", "chop"), (
        "choir_aahs", "voice_oohs", "vocal_fx", "gm_choir_pad", "gm_voice_lead",
    )),
    ("pad", ("pad", "atmosphere", "texture"), (
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

_GUITAR_ADJECTIVES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("dist", "metal", "heavy", "power"), "distortion_guitar"),
    (("overdrive", "over", "crunch", "rock", "grunge"), "overdriven_guitar"),
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
    "strings": "string_ensemble",
    "brass": "brass_section",
    "sax": "alto_sax",
    "flute": "flute",
    "vocal": "choir_aahs",
    "pad": "warm_pad",
    "lead_synth": "gm_sawtooth_lead",
}


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def reconcile_patch(instrument_name: str, patch: str) -> str:
    """Return a patch consistent with the readable instrument name.

    This only repairs obvious family mismatches. It does not infer genre or add
    instruments; it keeps the emitted patch when the name is merely a role label.
    """
    name_n = _normalize_name(instrument_name)
    if not name_n:
        return patch
    if name_n in PATCH_SPEC and name_n != patch:
        return name_n
    for family, keywords, members in _FAMILIES:
        if any(keyword in name_n for keyword in keywords):
            if patch in members:
                return patch
            if family == "guitar":
                for adjectives, pick in _GUITAR_ADJECTIVES:
                    if any(adjective in name_n for adjective in adjectives):
                        return pick
            if family == "piano":
                if "rhodes" in name_n:
                    return "electric_piano_rhodes"
                if "dx" in name_n:
                    return "electric_piano_dx"
                if "clav" in name_n:
                    return "clavinet"
            return _FAMILY_DEFAULTS[family]
    return patch
