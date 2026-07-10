// General MIDI program metadata shared by local playback and MIDI export.
// Only the canonical 128 melodic patches are needed; drums use a single
// percussion folder where the note number is the kit piece.

export const GM_PROGRAM_FOLDER: Record<number, string> = {
  0: "acoustic_grand_piano", 1: "bright_acoustic_piano", 2: "electric_grand_piano",
  3: "honkytonk_piano", 4: "electric_piano_1", 5: "electric_piano_2", 6: "harpsichord",
  7: "clavinet", 8: "celesta", 9: "glockenspiel", 10: "music_box", 11: "vibraphone",
  12: "marimba", 13: "xylophone", 14: "tubular_bells", 15: "dulcimer",
  16: "drawbar_organ", 17: "percussive_organ", 18: "rock_organ", 19: "church_organ",
  20: "reed_organ", 21: "accordion", 22: "harmonica", 23: "tango_accordion",
  24: "acoustic_guitar_nylon", 25: "acoustic_guitar_steel", 26: "electric_guitar_jazz",
  27: "electric_guitar_clean", 28: "electric_guitar_muted", 29: "overdriven_guitar",
  30: "distortion_guitar", 31: "guitar_harmonics",
  32: "acoustic_bass", 33: "electric_bass_finger", 34: "electric_bass_pick",
  35: "fretless_bass", 36: "slap_bass_1", 37: "slap_bass_2", 38: "synth_bass_1", 39: "synth_bass_2",
  40: "violin", 41: "viola", 42: "cello", 43: "contrabass", 44: "tremolo_strings",
  45: "pizzicato_strings", 46: "orchestral_harp", 47: "timpani",
  48: "string_ensemble_1", 49: "string_ensemble_2", 50: "synth_strings_1", 51: "synth_strings_2",
  52: "choir_aahs", 53: "voice_oohs", 54: "synth_choir", 55: "orchestra_hit",
  56: "trumpet", 57: "trombone", 58: "tuba", 59: "muted_trumpet",
  60: "french_horn", 61: "brass_section", 62: "synth_brass_1", 63: "synth_brass_2",
  64: "soprano_sax", 65: "alto_sax", 66: "tenor_sax", 67: "baritone_sax",
  68: "oboe", 69: "english_horn", 70: "bassoon", 71: "clarinet",
  72: "piccolo", 73: "flute", 74: "recorder", 75: "pan_flute",
  76: "blown_bottle", 77: "shakuhachi", 78: "whistle", 79: "ocarina",
  80: "lead_1_square", 81: "lead_2_sawtooth", 82: "lead_3_calliope", 83: "lead_4_chiff",
  84: "lead_5_charang", 85: "lead_6_voice", 86: "lead_7_fifths", 87: "lead_8_bass__lead",
  88: "pad_1_new_age", 89: "pad_2_warm", 90: "pad_3_polysynth", 91: "pad_4_choir",
  92: "pad_5_bowed", 93: "pad_6_metallic", 94: "pad_7_halo", 95: "pad_8_sweep",
  96: "fx_1_rain", 97: "fx_2_soundtrack", 98: "fx_3_crystal", 99: "fx_4_atmosphere",
  100: "fx_5_brightness", 101: "fx_6_goblins", 102: "fx_7_echoes", 103: "fx_8_scifi",
  104: "sitar", 105: "banjo", 106: "shamisen", 107: "koto", 108: "kalimba",
  109: "bag_pipe", 110: "fiddle", 111: "shanai",
  112: "tinkle_bell", 113: "agogo", 114: "steel_drums", 115: "woodblock",
  116: "taiko_drum", 117: "melodic_tom", 118: "synth_drum", 119: "reverse_cymbal",
  120: "guitar_fret_noise", 121: "breath_noise", 122: "seashore", 123: "bird_tweet",
  124: "telephone_ring", 125: "helicopter", 126: "applause", 127: "gunshot",
};

export function folderForProgram(program: number): string {
  return GM_PROGRAM_FOLDER[program] ?? "acoustic_grand_piano";
}

// Director-LLM frequently leaves midi_program at the default 0 (piano) even
// when the `instrument` string is "flute" / "viola" / "808 kick", so every
// channel ends up sounding like a grand piano. This inferrer takes the human
// name and returns the most plausible GM program — used as a fallback or
// override whenever midi_program is 0.
const NAME_TO_PROGRAM: Array<[RegExp, number]> = [
  // strings
  [/\bvioloncello\b|\bcello\b/i, 42],
  [/\bcontrabass\b|\bupright bass\b|\bdouble bass\b/i, 43],
  [/\bviolin\b|\bfiddle\b/i, 40],
  [/\bviola\b/i, 41],
  [/\bharp\b/i, 46],
  [/pizzicato/i, 45],
  [/\bstrings?\b|\bensemble\b|orchestra/i, 48],
  // woodwinds / pipe
  [/\bpiccolo\b/i, 72],
  [/\bflute\b/i, 73],
  [/\brecorder\b/i, 74],
  [/\bpan ?flute\b/i, 75],
  [/\bshakuhachi\b/i, 77],
  [/\bocarina\b/i, 79],
  [/\bclarinet\b/i, 71],
  [/\boboe\b/i, 68],
  [/\bbassoon\b/i, 70],
  [/english horn|cor anglais/i, 69],
  [/\bsax\b|saxophone/i, 65],
  // brass
  [/muted trumpet/i, 59],
  [/\btrumpet\b/i, 56],
  [/\btrombone\b/i, 57],
  [/\btuba\b/i, 58],
  [/french horn|\bhorn\b/i, 60],
  [/\bbrass\b/i, 61],
  // organ / accordion / harmonica
  [/church organ/i, 19],
  [/rock organ/i, 18],
  [/drawbar organ|hammond/i, 16],
  [/\borgan\b/i, 17],
  [/accordion/i, 21],
  [/harmonica/i, 22],
  // bass family (electric / synth)
  [/synth ?bass/i, 38],
  [/slap bass/i, 36],
  [/fretless bass/i, 35],
  [/electric bass|\bbass guitar\b|\be\.?bass\b/i, 33],
  [/acoustic bass/i, 32],
  [/\bbass\b|\bsub\b|\b808\b/i, 33],
  // guitar family
  [/distortion guitar|distorted/i, 30],
  [/overdriven|overdrive/i, 29],
  [/electric guitar.*muted/i, 28],
  [/electric guitar.*clean|clean guitar/i, 27],
  [/electric guitar.*jazz/i, 26],
  [/acoustic guitar.*steel|steel.*guitar/i, 25],
  [/acoustic guitar|nylon|classical guitar/i, 24],
  [/\bguitar\b/i, 24],
  // keys
  [/electric piano|rhodes|wurli/i, 4],
  [/honkytonk|honky-tonk/i, 3],
  [/harpsichord/i, 6],
  [/clavinet|clav\b/i, 7],
  [/celesta/i, 8],
  [/glockenspiel/i, 9],
  [/music box/i, 10],
  [/vibraphone|vibes/i, 11],
  [/marimba/i, 12],
  [/xylophone/i, 13],
  [/tubular bells?/i, 14],
  [/\bpiano\b/i, 0],
  // voice / pads / leads
  [/choir|aahs|oohs|vox|vocal/i, 52],
  [/synth pad|warm pad|pad\b/i, 89],
  [/synth lead|lead synth|saw lead/i, 81],
  [/synth\b/i, 81],
  // ethnic
  [/sitar/i, 104],
  [/banjo/i, 105],
  [/kalimba/i, 108],
  [/steel drum|steelpan/i, 114],
  // drums / percussion — handled by is_drum, but include for completeness
  [/shaker|tambourine|woodblock|cowbell|congas?|bongo|cajon|claves|maracas|timbales|hi-?hat|snare|kick|drum|percussion|\bperc\b/i, 0],
];

export function inferProgramFromName(name: string): number | null {
  for (const [re, prog] of NAME_TO_PROGRAM) if (re.test(name)) return prog;
  return null;
}

interface RosterLike {
  id?: string;
  instrument?: string;
  role?: string;
  is_drum?: boolean;
  midi_program?: number;
}

/** Trust midi_program when non-zero; otherwise infer from instrument/role name.
 *  Same logic shared by playback (TrackMixer) and MIDI export. */
export function resolveProgram(r: RosterLike): number {
  if (r.midi_program && r.midi_program > 0) return r.midi_program;
  const inferred = inferProgramFromName(r.instrument || r.role || r.id || "");
  return inferred ?? 0;
}

export function resolveIsDrum(r: RosterLike): boolean {
  if (r.is_drum) return true;
  return isDrumByName(r.instrument || r.role || r.id || "");
}

const PERCUSSION_RE = /\b(drum|drums|kit|percussion|perc|shaker|tambourine|woodblock|cowbell|congas?|bongo|cajon|claves|maracas|timbales|hi-?hat|hat|snare|kick|cymbal|tom)\b/i;

export function isDrumByName(name: string): boolean {
  return PERCUSSION_RE.test(name);
}

// FluidR3 filenames use letter+`s` for sharps (e.g. `Cs4.mp3`), but Tone.Sampler
// only accepts standard pitch notation as url keys (e.g. `C#4`). So we expose
// two helpers: `midiToName` returns the Tone-parseable name (used as the sampler
// url key AND for `triggerAttackRelease`), and `midiToFileName` returns the
// FluidR3 filename stem.
const NOTE_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const NOTE_NAMES_FILE = ["C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B"];
export function midiToName(midi: number): string {
  const octave = Math.floor(midi / 12) - 1;
  const name = NOTE_NAMES_SHARP[((midi % 12) + 12) % 12];
  return `${name}${octave}`;
}
export function midiToFileName(midi: number): string {
  const octave = Math.floor(midi / 12) - 1;
  const name = NOTE_NAMES_FILE[((midi % 12) + 12) % 12];
  return `${name}${octave}`;
}

// FluidR3 percussion-mp3 covers the standard GM drum kit (MIDI 35..81)
// but a handful of high keys are missing. Stick to the safe slice.
export const PERCUSSION_MIN = 35;
export const PERCUSSION_MAX = 77;
