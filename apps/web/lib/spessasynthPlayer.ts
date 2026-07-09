import { Midi } from "@tonejs/midi";
import type { SongState } from "@/lib/types";
import { buildTrackEvents } from "@/lib/trackMixerLogic.mjs";
import { resolveIsDrum, resolveProgram } from "@/lib/gmInstruments";

/** Build a MIDI file where every non-drum track is on its own channel (0-15
 *  skipping 9). Returns bytes + a map from partId → channel so the mixer can
 *  address per-track mute against the sequencer's synth. */
export function buildMidiWithChannels(song: SongState): {
  bytes: Uint8Array;
  channelByPartId: Map<string, number>;
} {
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

    for (const ev of events[partId] ?? []) {
      track.addNote({
        midi: ev.pitch,
        time: ev.startSeconds,
        duration: Math.max(0.05, ev.durationSeconds),
        velocity: Math.max(0, Math.min(1, ev.velocity)),
      });
    }
  }

  return { bytes: midi.toArray(), channelByPartId };
}

// Publicly hosted, CORS-enabled General MIDI SoundFont maintained by the
// spessasynth author. ~8MB SF3, cached by the browser after first fetch.
const SOUNDFONT_URL = "https://spessasus.github.io/SpessaSynth/soundfonts/GeneralUserGS.sf3";
const WORKLET_URL = "/spessasynth/spessasynth_processor.min.js";

let cachedSoundBank: Promise<ArrayBuffer> | null = null;
export function loadSoundBank(): Promise<ArrayBuffer> {
  if (!cachedSoundBank) {
    cachedSoundBank = fetch(SOUNDFONT_URL).then((r) => {
      if (!r.ok) throw new Error(`SoundFont fetch failed: ${r.status}`);
      return r.arrayBuffer();
    });
  }
  return cachedSoundBank;
}

export function workletUrl(): string {
  return WORKLET_URL;
}
