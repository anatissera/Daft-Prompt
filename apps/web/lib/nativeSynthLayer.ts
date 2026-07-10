/** Native synth playback layer for the five `synth_preset` patches
 * (supersaw_lead, sub_bass, pluck, warm_pad, vocal_fx). These are supposed
 * to be actual syntheses — routing them through the SF3 GM soundfont as
 * closest-approximation programs (lead_2_sawtooth, synth_bass_1, pad_2_warm,
 * synth_choir) is what made every EDM track sound like a flat electric-
 * piano keyboard. This layer runs alongside spessasynth on the SAME
 * AudioContext, plays synth-preset tracks with real detuned oscillators /
 * envelopes / filter LFOs, and is mute/solo aware. */

import type { SongState, RosterItem } from "@/lib/types";
import { buildTrackEvents, type TrackEvent } from "@/lib/trackMixerLogic.mjs";

type Tone = typeof import("tone");
type ToneCtor = InstanceType<Tone["Gain"]>;

// A track wraps: the source synth, a per-track gain node (for mute), and
// the events we need to schedule when playback starts.
interface NativeTrack {
  partId: string;
  preset: string;
  synth: {
    triggerAttackRelease: (note: number, dur: number, time: number, velocity: number) => void;
    releaseAll?: () => void;
    dispose: () => void;
  };
  gain: ToneCtor;
  events: TrackEvent[];
}

export class NativeSynthLayer {
  private tone: Tone | null = null;
  private ctx: AudioContext;
  private tracks: Map<string, NativeTrack> = new Map();
  private scheduledTimeouts: number[] = [];
  private playing = false;
  private mutedByDefault = false;

  constructor(ctx: AudioContext) {
    this.ctx = ctx;
  }

  private tempoBpm = 120;

  /** Build synths for every `synth_preset` track in the song. Call once
   * per song. Idempotent per partId. */
  async prepare(song: SongState): Promise<void> {
    if (!this.tone) {
      this.tone = await import("tone");
      // Tone's default context is a private one; splice ours so audio
      // graphs share the same AudioContext as spessasynth. This also
      // ensures ctx.currentTime is a single common clock.
      this.tone.setContext(this.ctx);
    }
    this.tempoBpm = song.header.tempo_bpm || 120;
    const rosterById = new Map(song.roster.map((r) => [r.id, r]));
    const events = buildTrackEvents(song);
    for (const [partId] of Object.entries(song.parts)) {
      const roster = rosterById.get(partId);
      if (!roster || !roster.synth_preset) continue;
      if (this.tracks.has(partId)) continue;
      const track = this.createTrack(roster, events[partId] ?? []);
      if (track) this.tracks.set(partId, track);
    }
  }

  /** Play from `offsetSec` in song time. Schedules note triggers via
   * `setTimeout` (for scheduling) + Tone's own ctx-anchored trigger
   * timing, so notes align with spessasynth's sequencer. */
  play(offsetSec: number): void {
    if (!this.tone) return;
    this.stopPending();
    this.playing = true;
    const t0Wall = performance.now();
    for (const track of this.tracks.values()) {
      for (const ev of track.events) {
        if (ev.startSeconds < offsetSec) continue;
        const delayMs = Math.max(0, (ev.startSeconds - offsetSec) * 1000);
        const dueWall = t0Wall + delayMs;
        const handle = window.setTimeout(() => {
          if (!this.playing) return;
          try {
            // triggerAttackRelease takes time in Tone's context clock; use
            // `+0` (now) since our setTimeout already handled the delay.
            track.synth.triggerAttackRelease(
              ev.pitch,
              Math.max(0.05, ev.durationSeconds),
              this.ctx.currentTime,
              Math.max(0, Math.min(1, ev.velocity)),
            );
          } catch { /* ignore transient synth errors */ }
        }, Math.max(0, dueWall - performance.now()));
        this.scheduledTimeouts.push(handle);
      }
    }
  }

  pause(): void {
    this.playing = false;
    this.stopPending();
    for (const track of this.tracks.values()) {
      try { track.synth.releaseAll?.(); } catch { /* noop */ }
    }
  }

  /** Set audible/muted plus per-track volume (0..1, default 1) for a single
   * track. Passes through to the per-track gain node so both take effect
   * mid-playback. */
  setAudible(partId: string, audible: boolean, gain: number = 1): void {
    const track = this.tracks.get(partId);
    if (!track) return;
    const target = audible ? Math.max(0, Math.min(1, gain)) : 0;
    try {
      // Ramp to avoid clicks.
      track.gain.gain.cancelScheduledValues(this.ctx.currentTime);
      track.gain.gain.linearRampToValueAtTime(target, this.ctx.currentTime + 0.01);
    } catch { /* noop */ }
  }

  /** True iff this song has at least one native-synth part — the mixer
   * skips this layer entirely when false to avoid the Tone.js import. */
  hasAnyTracks(): boolean {
    return this.tracks.size > 0;
  }

  /** Part ids for which a synth was successfully constructed. The mixer uses
   * this — not the roster's `synth_preset` field — to decide which SF3
   * channels to mute, so a failed preset (unknown name, ctor throw) falls
   * back to the SF3 GM approximation instead of going silent. */
  coveredPartIds(): Set<string> {
    return new Set(this.tracks.keys());
  }

  dispose(): void {
    this.stopPending();
    this.playing = false;
    for (const track of this.tracks.values()) {
      try { track.synth.dispose(); } catch { /* noop */ }
      try { track.gain.dispose(); } catch { /* noop */ }
    }
    this.tracks.clear();
  }

  // --- private -----------------------------------------------------------

  private stopPending(): void {
    for (const h of this.scheduledTimeouts) window.clearTimeout(h);
    this.scheduledTimeouts = [];
  }

  private createTrack(roster: RosterItem, events: TrackEvent[]): NativeTrack | null {
    if (!this.tone) return null;
    const T = this.tone;
    const preset = String(roster.synth_preset);
    const gain = new T.Gain(this.mutedByDefault ? 0 : 1).toDestination();
    let synth: NativeTrack["synth"];

    switch (preset) {
      case "supersaw_lead":
        synth = this.makeSupersawLead(T, gain);
        break;
      case "sub_bass":
        synth = this.makeSubBass(T, gain);
        break;
      case "pluck":
        synth = this.makePluck(T, gain);
        break;
      case "warm_pad":
        synth = this.makeWarmPad(T, gain);
        break;
      case "vocal_fx":
        synth = this.makeVocalFx(T, gain);
        break;
      case "wobble_bass":
        synth = this.makeWobbleBass(T, gain);
        break;
      default:
        return null;
    }
    return { partId: roster.id, preset, synth, gain, events };
  }

  private makeSupersawLead(T: Tone, out: ToneCtor): NativeTrack["synth"] {
    // Detuned-saw stack driven by a shared low-pass filter with a subtle
    // resonance peak — the classic "hoover" flavor. PolySynth allows chord
    // stabs; each voice is a 3-osc detuned saw via FMSynth abuse would
    // be muddy, so we use a plain Synth with a lightly-detuned oscillator
    // count via the internal `partials` / `count` trick.
    const filter = new T.Filter({ type: "lowpass", frequency: 4200, Q: 1.4 }).connect(out);
    const poly = new T.PolySynth(T.Synth, {
      oscillator: { type: "sawtooth" },
      envelope: { attack: 0.006, decay: 0.18, sustain: 0.65, release: 0.14 },
      volume: -8,
    });
    poly.connect(filter);
    // A second slightly-detuned poly layered underneath gives the "super"
    // in supersaw. Tone's PolySynth doesn't expose per-voice detune easily,
    // so we run two layers with opposite detune. Cheap trick, sounds huge.
    const polyB = new T.PolySynth(T.Synth, {
      oscillator: { type: "sawtooth" },
      envelope: { attack: 0.006, decay: 0.18, sustain: 0.65, release: 0.14 },
      volume: -10,
      detune: 12,
    });
    polyB.connect(filter);
    const polyC = new T.PolySynth(T.Synth, {
      oscillator: { type: "sawtooth" },
      envelope: { attack: 0.006, decay: 0.18, sustain: 0.65, release: 0.14 },
      volume: -10,
      detune: -12,
    });
    polyC.connect(filter);
    return {
      triggerAttackRelease: (note, dur, time, velocity) => {
        const freq = T.Frequency(note, "midi").toFrequency();
        poly.triggerAttackRelease(freq, dur, time, velocity);
        polyB.triggerAttackRelease(freq, dur, time, velocity);
        polyC.triggerAttackRelease(freq, dur, time, velocity);
      },
      releaseAll: () => { poly.releaseAll(); polyB.releaseAll(); polyC.releaseAll(); },
      dispose: () => { poly.dispose(); polyB.dispose(); polyC.dispose(); filter.dispose(); },
    };
  }

  private makeSubBass(T: Tone, out: ToneCtor): NativeTrack["synth"] {
    // Pure sine with a touch of soft-clip saturation for warmth and a
    // slow-ish attack so short subs still articulate. Mono so 8th-note
    // sub lines glide instead of pile up.
    const distortion = new T.Distortion({ distortion: 0.08, wet: 0.35 }).connect(out);
    const synth = new T.MonoSynth({
      oscillator: { type: "sine" },
      envelope: { attack: 0.01, decay: 0.2, sustain: 0.9, release: 0.15 },
      filterEnvelope: { attack: 0.02, decay: 0.1, sustain: 1, release: 0.2, baseFrequency: 220, octaves: 2 },
      volume: -4,
    }).connect(distortion);
    return {
      triggerAttackRelease: (note, dur, time, velocity) => {
        synth.triggerAttackRelease(T.Frequency(note, "midi").toFrequency(), dur, time, velocity);
      },
      releaseAll: () => { synth.triggerRelease(); },
      dispose: () => { synth.dispose(); distortion.dispose(); },
    };
  }

  private makePluck(T: Tone, out: ToneCtor): NativeTrack["synth"] {
    // Physical-model pluck for the classic short staccato that fills
    // between other hits.
    const synth = new T.PluckSynth({
      attackNoise: 0.9,
      dampening: 4200,
      resonance: 0.72,
      volume: -6,
    }).connect(out);
    return {
      triggerAttackRelease: (note, _dur, time, _velocity) => {
        // PluckSynth is monophonic string-model; triggerAttack ignores
        // duration and velocity — the physical model's dampening handles
        // decay naturally.
        synth.triggerAttack(T.Frequency(note, "midi").toFrequency(), time);
      },
      dispose: () => { synth.dispose(); },
    };
  }

  private makeWarmPad(T: Tone, out: ToneCtor): NativeTrack["synth"] {
    // Slow-attack pad with a filter LFO for movement — the "atmosphere"
    // sound the roster keeps picking for texture layers.
    const filter = new T.Filter({ type: "lowpass", frequency: 1400, Q: 0.7 }).connect(out);
    const lfo = new T.LFO({ frequency: 0.18, min: 800, max: 2400 }).start();
    lfo.connect(filter.frequency);
    const pad = new T.PolySynth(T.Synth, {
      oscillator: { type: "triangle" },
      envelope: { attack: 0.6, decay: 0.4, sustain: 0.8, release: 1.4 },
      volume: -10,
    }).connect(filter);
    return {
      triggerAttackRelease: (note, dur, time, velocity) => {
        pad.triggerAttackRelease(T.Frequency(note, "midi").toFrequency(), dur, time, velocity);
      },
      releaseAll: () => { pad.releaseAll(); },
      dispose: () => { pad.dispose(); filter.dispose(); lfo.dispose(); },
    };
  }

  private makeWobbleBass(T: Tone, out: ToneCtor): NativeTrack["synth"] {
    // The dubstep/brostep "wub": detuned saw+square stack through a low-pass
    // whose cutoff is swept by a tempo-synced LFO. The LFO rate is an eighth-
    // note at the song tempo (140 BPM → ~4.7 Hz), the classic 1/8 wobble.
    // A sine sub an octave below keeps the low end solid while the filter
    // chews the mids. MIDI itself stays plain notes — the movement lives here.
    const lfoHz = (this.tempoBpm / 60) * 2; // eighth-note rate
    const filter = new T.Filter({ type: "lowpass", frequency: 900, Q: 6 }).connect(out);
    const lfo = new T.LFO({ frequency: lfoHz, min: 90, max: 2600, type: "sine" }).start();
    lfo.connect(filter.frequency);
    const growl = new T.MonoSynth({
      oscillator: { type: "fatsawtooth", count: 3, spread: 25 } as never,
      envelope: { attack: 0.01, decay: 0.1, sustain: 0.95, release: 0.08 },
      filterEnvelope: { attack: 0.01, decay: 0.05, sustain: 1, release: 0.1, baseFrequency: 2000, octaves: 0 },
      volume: -7,
    }).connect(filter);
    const square = new T.MonoSynth({
      oscillator: { type: "square" },
      envelope: { attack: 0.01, decay: 0.1, sustain: 0.95, release: 0.08 },
      filterEnvelope: { attack: 0.01, decay: 0.05, sustain: 1, release: 0.1, baseFrequency: 2000, octaves: 0 },
      volume: -12,
    }).connect(filter);
    const sub = new T.MonoSynth({
      oscillator: { type: "sine" },
      envelope: { attack: 0.01, decay: 0.15, sustain: 0.9, release: 0.1 },
      filterEnvelope: { attack: 0.01, decay: 0.1, sustain: 1, release: 0.1, baseFrequency: 300, octaves: 0 },
      volume: -6,
    }).connect(out);
    return {
      triggerAttackRelease: (note, dur, time, velocity) => {
        const freq = T.Frequency(note, "midi").toFrequency();
        const subFreq = T.Frequency(Math.max(0, note - 12), "midi").toFrequency();
        growl.triggerAttackRelease(freq, dur, time, velocity);
        square.triggerAttackRelease(freq, dur, time, velocity * 0.8);
        sub.triggerAttackRelease(subFreq, dur, time, velocity);
      },
      releaseAll: () => { growl.triggerRelease(); square.triggerRelease(); sub.triggerRelease(); },
      dispose: () => { growl.dispose(); square.dispose(); sub.dispose(); filter.dispose(); lfo.dispose(); },
    };
  }

  private makeVocalFx(T: Tone, out: ToneCtor): NativeTrack["synth"] {
    // FM voice with a formant-flavored filter and short chops via a
    // per-note amp envelope. Not a real vocal (impossible in-browser
    // without samples), but reads as "chopped pitched vocal" against
    // the other synths.
    const filter = new T.Filter({ type: "bandpass", frequency: 900, Q: 3.2 }).connect(out);
    const synth = new T.PolySynth(T.FMSynth, {
      harmonicity: 2,
      modulationIndex: 3.5,
      envelope: { attack: 0.02, decay: 0.12, sustain: 0.4, release: 0.18 },
      modulation: { type: "sine" },
      modulationEnvelope: { attack: 0.01, decay: 0.05, sustain: 0.5, release: 0.15 },
      volume: -10,
    }).connect(filter);
    return {
      triggerAttackRelease: (note, dur, time, velocity) => {
        synth.triggerAttackRelease(T.Frequency(note, "midi").toFrequency(), dur, time, velocity);
      },
      releaseAll: () => { synth.releaseAll(); },
      dispose: () => { synth.dispose(); filter.dispose(); },
    };
  }
}
