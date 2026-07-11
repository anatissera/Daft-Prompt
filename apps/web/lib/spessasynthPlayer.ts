import { Midi } from "@tonejs/midi";
import type { SongState } from "@/lib/types";
import { buildTrackEvents } from "@/lib/trackMixerLogic.mjs";
import { resolveIsDrum, resolveProgram } from "@/lib/gmInstruments";

export function buildMidiWithChannels(
  song: SongState,
  options: { gains?: Record<string, number>; audible?: Set<string> } = {},
): {
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
  let nextMelodicChannel = 0;

  for (const [partId] of Object.entries(song.parts)) {
    if (options.audible && !options.audible.has(partId)) continue;

    const roster = rosterById.get(partId);
    const isDrum = roster ? resolveIsDrum(roster) : false;
    let channel: number;
    if (isDrum) {
      channel = 9;
    } else {
      if (nextMelodicChannel === 9) nextMelodicChannel += 1;
      if (nextMelodicChannel > 15) nextMelodicChannel = 0;
      channel = nextMelodicChannel;
      nextMelodicChannel += 1;
    }
    channelByPartId.set(partId, channel);

    const track = midi.addTrack();
    track.name = roster?.instrument ?? partId;
    track.channel = channel;
    if (roster && !isDrum) track.instrument.number = resolveProgram(roster);

    const gain = Math.max(0, Math.min(1, options.gains?.[partId] ?? 1));
    for (const event of events[partId] ?? []) {
      track.addNote({
        midi: event.pitch,
        time: event.startSeconds,
        duration: Math.max(0.05, event.durationSeconds),
        velocity: Math.max(0, Math.min(1, event.velocity * gain)),
      });
    }
  }

  return { bytes: midi.toArray(), channelByPartId };
}

const SOUNDFONT_URL = "/soundfonts/MuseScore_General.sf3";
const WORKLET_URL = "/spessasynth/spessasynth_processor.min.js";

let cachedSoundBankBytes: Promise<ArrayBuffer> | null = null;

export async function loadSoundBank(): Promise<ArrayBuffer> {
  if (!cachedSoundBankBytes) {
    cachedSoundBankBytes = fetch(SOUNDFONT_URL).then((response) => {
      if (!response.ok) throw new Error(`SoundFont fetch failed: ${response.status}`);
      return response.arrayBuffer();
    });
  }
  const bytes = await cachedSoundBankBytes;
  return bytes.slice(0);
}

export function workletUrl(): string {
  return WORKLET_URL;
}
