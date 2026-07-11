import { Midi } from "@tonejs/midi";
import type { SongState } from "@/lib/types";
import { buildTrackEvents } from "@/lib/trackMixerLogic.mjs";
import { resolveIsDrum, resolveProgram } from "@/lib/gmInstruments";

/** Returns true when this roster item plays through the native Tone.js
 *  synth layer instead of the SF3 GM soundfont. The five values in
 *  `synth_preset` (supersaw_lead, sub_bass, pluck, warm_pad, vocal_fx)
 *  were designed to be true syntheses, not GM samples — routing them
 *  through the SF3 fallback (lead_2_sawtooth, synth_bass_1, etc.) is
 *  what made every EDM patch sound like a flat Casio. */
export function usesNativeSynth(roster: { synth_preset?: string | null } | undefined): boolean {
  return !!(roster && roster.synth_preset);
}

/** Build a MIDI file where every non-drum track is on its own channel (0-15
 *  skipping 9). ALL tracks — including those with a native `synth_preset` —
 *  land in the MIDI stream so the SF3 sequencer always renders SOMETHING for
 *  every part. If `NativeSynthLayer` is up and has a preset for a part, the
 *  mixer mutes the SF3 channel for that part at playback time so the two
 *  engines don't double-play. If native is down (import failed, preset
 *  unrecognised, ctx race) the SF3 fallback keeps the part audible instead of
 *  producing silence — that regression was breaking every synth-heavy song
 *  (dubstep, EDM), which route ~5 of ~6 melodic parts to native presets.
 *  Returns bytes + a map from partId → SF3 channel used by the mute logic. */
export function buildMidiWithChannels(
  song: SongState,
  options: { gains?: Record<string, number>; audible?: Set<string> } = {},
): {
  bytes: Uint8Array;
  channelByPartId: Map<string, number>;
} {
  // `gains` bakes per-track knob volume into note velocities and `audible`
  // drops muted/non-solo tracks entirely. Only offline consumers (MP3
  // render) pass them — live playback leaves velocities raw and rides
  // CC7/channel-mute instead, so mixer changes apply without a rebuild.
  const gains = options.gains;
  const audible = options.audible;
  const events = buildTrackEvents(song);
  const midi = new Midi();
  midi.header.setTempo(song.header.tempo_bpm);
  midi.header.timeSignatures.push({
    ticks: 0,
    timeSignature: [song.header.time_signature[0], song.header.time_signature[1]],
    measures: 0,
  });

  const rosterById = new Map(song.roster.map((r) => [r.id, r]));
  const channelByPartId = new Map<string, number>();
  let nextMelodic = 0;

  for (const [partId] of Object.entries(song.parts)) {
    if (audible && !audible.has(partId)) continue;
    const roster = rosterById.get(partId);
    const isDrum = roster ? resolveIsDrum(roster) : false;
    let ch: number;
    if (isDrum) {
      ch = 9; // GM percussion
    } else {
      if (nextMelodic === 9) nextMelodic++;
      if (nextMelodic > 15) nextMelodic = 0; // wrap; unlikely with our small rosters
      ch = nextMelodic++;
    }
    channelByPartId.set(partId, ch);

    const track = midi.addTrack();
    track.name = roster?.instrument ?? partId;
    track.channel = ch;
    if (!isDrum && roster) track.instrument.number = resolveProgram(roster);

    const gain = Math.max(0, Math.min(1, gains?.[partId] ?? 1));
    for (const ev of events[partId] ?? []) {
      track.addNote({
        midi: ev.pitch,
        time: ev.startSeconds,
        duration: Math.max(0.05, ev.durationSeconds),
        velocity: Math.max(0, Math.min(1, ev.velocity * gain)),
      });
    }
  }

  return { bytes: midi.toArray(), channelByPartId };
}

// Self-hosted MuseScore_General SF3 (~38MB, LGPL). Broader/richer sample
// pool than the 8MB GeneralUserGS we shipped with — better acoustic
// timbres AND better GM synth patches. Native-synth patches
// (supersaw_lead, sub_bass, pluck, warm_pad, vocal_fx) bypass the SF3
// entirely via NativeSynthLayer, so the sf3 file is used for sampled
// instruments only.
const SOUNDFONT_URL = "/soundfonts/MuseScore_General.sf3";
const WORKLET_URL = "/spessasynth/spessasynth_processor.min.js";

// Spessasynth transfers the ArrayBuffer into the audio worklet, which
// detaches it. Returning the same cached buffer twice — e.g. when the user
// generates a second song in the same session — gives "attempting to access
// detached ArrayBuffer" on the second load. Cache the bytes and hand back a
// fresh copy every time.
let cachedSoundBankBytes: Promise<ArrayBuffer> | null = null;
export async function loadSoundBank(): Promise<ArrayBuffer> {
  if (!cachedSoundBankBytes) {
    cachedSoundBankBytes = fetch(SOUNDFONT_URL).then((r) => {
      if (!r.ok) throw new Error(`SoundFont fetch failed: ${r.status}`);
      return r.arrayBuffer();
    });
  }
  const bytes = await cachedSoundBankBytes;
  return bytes.slice(0);
}

export function workletUrl(): string {
  return WORKLET_URL;
}
