import type { SongState } from "@/lib/types";
import { buildMidiWithChannels, loadSoundBank, workletUrl } from "@/lib/spessasynthPlayer";

const SAMPLE_RATE = 44100;
const MP3_KBPS = 128;
const MP3_FRAME = 1152; // lamejs encodes 1152 samples per MP3 frame.
const TAIL_SECONDS = 2; // reverb tail after last note.

async function renderSongToAudioBuffer(song: SongState, gains?: Record<string, number>): Promise<AudioBuffer> {
  // Include native-synth tracks with their GM fallback — offline render
  // can't run the Tone.js scheduler, so the MP3 falls back to sampled
  // approximations. Live preview still uses real synthesis. Knob volumes
  // are baked into velocities so the exported mix matches what you hear.
  const { bytes } = buildMidiWithChannels(song, { gains });
  const arrayBuf = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;

  const [spessa, core, sfBuf] = await Promise.all([
    import("spessasynth_lib"),
    import("spessasynth_core"),
    loadSoundBank(),
  ]);

  const midi = core.BasicMIDI.fromArrayBuffer(arrayBuf);
  const totalSeconds = midi.duration + TAIL_SECONDS;
  const offCtx = new OfflineAudioContext(
    2,
    Math.ceil(SAMPLE_RATE * totalSeconds),
    SAMPLE_RATE,
  );
  await offCtx.audioWorklet.addModule(workletUrl());
  const synth = new spessa.WorkletSynthesizer(offCtx);
  synth.connect(offCtx.destination);
  // Per spessasynth docs: no other synth methods allowed before this call.
  await synth.startOfflineRender({
    midiSequence: midi,
    loopCount: 0,
    soundBankList: [{ bankOffset: 0, soundBankBuffer: sfBuf }],
  });
  return offCtx.startRendering();
}

function floatToInt16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const v = Math.max(-1, Math.min(1, input[i]));
    out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  return out;
}

async function audioBufferToMp3Blob(buf: AudioBuffer): Promise<Blob> {
  const lame = await import("@breezystack/lamejs");
  const channels = Math.min(2, buf.numberOfChannels);
  const encoder = new lame.Mp3Encoder(channels, buf.sampleRate, MP3_KBPS);
  const left = floatToInt16(buf.getChannelData(0));
  const right = channels > 1 ? floatToInt16(buf.getChannelData(1)) : left;

  const chunks: Uint8Array[] = [];
  for (let i = 0; i < left.length; i += MP3_FRAME) {
    const l = left.subarray(i, i + MP3_FRAME);
    const r = right.subarray(i, i + MP3_FRAME);
    const frame = encoder.encodeBuffer(l, r);
    if (frame.length > 0) chunks.push(frame);
  }
  const tail = encoder.flush();
  if (tail.length > 0) chunks.push(tail);
  // Blob() accepts BlobPart[] — Uint8Array is one of them.
  return new Blob(chunks as unknown as BlobPart[], { type: "audio/mpeg" });
}

export async function renderSongToMp3Blob(song: SongState, gains?: Record<string, number>): Promise<Blob> {
  const audio = await renderSongToAudioBuffer(song, gains);
  return audioBufferToMp3Blob(audio);
}

export async function triggerMp3Download(song: SongState, gains?: Record<string, number>): Promise<void> {
  const blob = await renderSongToMp3Blob(song, gains);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const safeName = (song.header.genre || "song").replace(/[^a-z0-9-_]+/gi, "_").toLowerCase();
  a.href = url;
  a.download = `${safeName || "song"}.mp3`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
