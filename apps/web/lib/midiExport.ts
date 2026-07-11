import { Midi } from "@tonejs/midi";
import type { SongState } from "@/lib/types";
import { buildTrackEvents } from "@/lib/trackMixerLogic.mjs";
import { resolveIsDrum, resolveProgram } from "@/lib/gmInstruments";

/** Serialize the song to a MIDI byte array, keeping only the parts whose
 *  ids are in `audible` (post Mute/Solo), with each part's velocities
 *  scaled by its knob volume in `gains` (0..1, default 1). Trivially equal
 *  to the backend's full file when nothing is muted/soloed/attenuated. */
export function buildFilteredMidi(
  song: SongState,
  audible: Set<string>,
  gains?: Record<string, number>,
): Uint8Array {
  const events = buildTrackEvents(song);
  const midi = new Midi();
  midi.header.setTempo(song.header.tempo_bpm);
  midi.header.timeSignatures.push({
    ticks: 0,
    timeSignature: [song.header.time_signature[0], song.header.time_signature[1]],
    measures: 0,
  });

  const rosterById = new Map(song.roster.map((r) => [r.id, r]));

  for (const [partId] of Object.entries(song.parts)) {
    if (!audible.has(partId)) continue;
    const gain = Math.max(0, Math.min(1, gains?.[partId] ?? 1));
    const roster = rosterById.get(partId);
    const track = midi.addTrack();
    track.name = roster?.instrument ?? partId;
    if (roster && resolveIsDrum(roster)) {
      track.channel = 9; // GM percussion
    } else if (roster) {
      track.instrument.number = resolveProgram(roster);
    }
    for (const ev of events[partId] ?? []) {
      track.addNote({
        midi: ev.pitch,
        time: ev.startSeconds,
        duration: Math.max(0.05, ev.durationSeconds),
        velocity: Math.max(0, Math.min(1, ev.velocity * gain)),
      });
    }
  }

  return midi.toArray();
}

export function triggerMidiDownload(
  song: SongState,
  audible: Set<string>,
  gains?: Record<string, number>,
): void {
  const bytes = buildFilteredMidi(song, audible, gains);
  // Re-wrap to satisfy the strict BlobPart type (Uint8Array<ArrayBufferLike>
  // isn't assignable to BlobPart directly in TS 5.7).
  const blob = new Blob([new Uint8Array(bytes).buffer as ArrayBuffer], { type: "audio/midi" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const safeName = (song.header.genre || "song").replace(/[^a-z0-9-_]+/gi, "_").toLowerCase();
  a.href = url;
  a.download = `${safeName || "song"}.mid`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
