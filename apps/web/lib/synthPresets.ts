// Native Tone.js synthesis presets for timbres the FluidR3 GM soundfont
// can't cover — modern EDM leads (supersaw), sub bass, plucks, warm pads,
// and vocal-chop FX.
//
// The choice of preset (or "use the sampler") is now made upstream by the
// director LLM via the roster's `synth_preset` field. We do NOT try to
// guess the intent back from playing_style / instrument name / roster id
// with regex — that was fragile and drifted every time the LLM re-worded
// its output. This file just holds the audio factory for each named preset.

import type * as ToneType from "tone";
import type { RosterItem, SynthPreset } from "./types";

export type { SynthPreset } from "./types";

/** Returns the preset chosen by the director, or null when the track should
 *  play through the FluidR3 sampler. Drums always sample. */
export function resolveSynthPreset(r: RosterItem): SynthPreset | null {
  if (r.is_drum) return null;
  return r.synth_preset ?? null;
}

// ---- factory ---------------------------------------------------------------

type ToneInstrument = ToneType.Sampler | ToneType.PolySynth | ToneType.MonoSynth;

export function makeSynth(Tone: typeof ToneType, preset: SynthPreset): ToneInstrument {
  switch (preset) {
    case "supersaw_lead":
      // Detuned saw approximation via PolySynth voices. The filter envelope
      // opens on attack — that "wow" sweep is the Marshmello lead's defining
      // transient.
      return new Tone.PolySynth(Tone.MonoSynth, {
        oscillator: { type: "sawtooth" },
        detune: 6,
        filter: { type: "lowpass", Q: 2 },
        filterEnvelope: { attack: 0.02, decay: 0.15, sustain: 0.6, release: 0.4, baseFrequency: 400, octaves: 3 },
        envelope: { attack: 0.01, decay: 0.1, sustain: 0.7, release: 0.3 },
        volume: -8,
      }) as unknown as ToneType.PolySynth;

    case "sub_bass":
      // Mono, triangle, quick tight envelope — sits below 80Hz and never
      // fights the lead.
      return new Tone.MonoSynth({
        oscillator: { type: "triangle" },
        envelope: { attack: 0.005, decay: 0.2, sustain: 0.9, release: 0.15 },
        filter: { type: "lowpass", frequency: 200, Q: 0.5 },
        filterEnvelope: { attack: 0.001, decay: 0.1, sustain: 1, release: 0.2, baseFrequency: 60, octaves: 1.5 },
        volume: -4,
      });

    case "pluck":
      // Snappy attack, no sustain, short release — the EDM pluck idiom.
      return new Tone.PolySynth(Tone.MonoSynth, {
        oscillator: { type: "square" },
        envelope: { attack: 0.001, decay: 0.15, sustain: 0.05, release: 0.2 },
        filter: { type: "lowpass", Q: 3 },
        filterEnvelope: { attack: 0.005, decay: 0.08, sustain: 0.1, release: 0.15, baseFrequency: 800, octaves: 2.5 },
        volume: -10,
      }) as unknown as ToneType.PolySynth;

    case "warm_pad":
      // Slow attack, long release, low cutoff — sits behind the lead. Detune
      // adds the analog shimmer.
      return new Tone.PolySynth(Tone.MonoSynth, {
        oscillator: { type: "sawtooth" },
        detune: 4,
        envelope: { attack: 0.8, decay: 0.4, sustain: 0.8, release: 1.6 },
        filter: { type: "lowpass", frequency: 1200, Q: 1 },
        filterEnvelope: { attack: 1.2, decay: 0.6, sustain: 0.6, release: 1.8, baseFrequency: 300, octaves: 2 },
        volume: -14,
      }) as unknown as ToneType.PolySynth;

    case "vocal_fx":
      // Bandpass-filtered square approximates the "eh! oh!" pitched-vocal
      // character of future bass. Short attack for 16th-note chops.
      return new Tone.PolySynth(Tone.MonoSynth, {
        oscillator: { type: "square" },
        detune: 3,
        envelope: { attack: 0.02, decay: 0.12, sustain: 0.3, release: 0.18 },
        filter: { type: "bandpass", frequency: 1500, Q: 4 },
        filterEnvelope: { attack: 0.02, decay: 0.2, sustain: 0.4, release: 0.2, baseFrequency: 1200, octaves: 1.5 },
        volume: -12,
      }) as unknown as ToneType.PolySynth;
  }
}
