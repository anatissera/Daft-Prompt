import type { SongState } from "@/lib/types";
import { buildMidiWithChannels, loadSoundBank, workletUrl } from "@/lib/spessasynthPlayer";

const SAMPLE_RATE = 44100;
const MP3_KBPS = 128;
const TAIL_SECONDS = 2; // reverb tail after last note.

async function renderSongToAudioBuffer(
  song: SongState,
  gains?: Record<string, number>,
  audible?: Set<string>,
): Promise<AudioBuffer> {
  // Include native-synth tracks with their GM fallback — offline render
  // can't run the Tone.js scheduler, so the MP3 falls back to sampled
  // approximations. Live preview still uses real synthesis. Knob volumes
  // are baked into velocities so the exported mix matches what you hear.
  const { bytes } = buildMidiWithChannels(song, { gains, audible });
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

async function audioBufferToMp3Blob(buf: AudioBuffer): Promise<Blob> {
  // Encoding happens in a Web Worker: lamejs is pure JS and a full song
  // used to freeze the page for seconds when run on the main thread.
  // Channel data is copied once (the AudioBuffer views aren't transferable)
  // and moved into the worker; the MP3 bytes are transferred back.
  const channels = Math.min(2, buf.numberOfChannels);
  const left = new Float32Array(buf.getChannelData(0));
  const right = channels > 1 ? new Float32Array(buf.getChannelData(1)) : null;

  const worker = new Worker(new URL("./mp3Encoder.worker.ts", import.meta.url));
  try {
    const bytes = await new Promise<Uint8Array>((resolve, reject) => {
      worker.onmessage = (e: MessageEvent<{ bytes?: Uint8Array; error?: string }>) => {
        if (e.data.error) reject(new Error(e.data.error));
        else resolve(e.data.bytes as Uint8Array);
      };
      worker.onerror = (e) => reject(new Error(e.message || "MP3 encoder worker failed"));
      const transfers: Transferable[] = [left.buffer];
      if (right) transfers.push(right.buffer);
      worker.postMessage(
        { left, right, sampleRate: buf.sampleRate, kbps: MP3_KBPS },
        transfers,
      );
    });
    return new Blob([bytes.buffer as ArrayBuffer], { type: "audio/mpeg" });
  } finally {
    worker.terminate();
  }
}

export async function renderSongToMp3Blob(
  song: SongState,
  gains?: Record<string, number>,
  audible?: Set<string>,
): Promise<Blob> {
  const audio = await renderSongToAudioBuffer(song, gains, audible);
  return audioBufferToMp3Blob(audio);
}

export async function triggerMp3Download(
  song: SongState,
  gains?: Record<string, number>,
  audible?: Set<string>,
): Promise<void> {
  const blob = await renderSongToMp3Blob(song, gains, audible);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const safeName = (song.header.genre || "song").replace(/[^a-z0-9-_]+/gi, "_").toLowerCase();
  a.href = url;
  a.download = `${safeName || "song"}.mp3`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
