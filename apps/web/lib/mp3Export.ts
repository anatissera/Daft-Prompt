import type { SongState } from "@/lib/types";
import { buildMidiWithChannels, loadSoundBank, workletUrl } from "@/lib/spessasynthPlayer";

const SAMPLE_RATE = 44100;
const MP3_KBPS = 128;
const MP3_FRAME = 1152;
const TAIL_SECONDS = 2;

async function renderSongToAudioBuffer(
  song: SongState,
  gains?: Record<string, number>,
  audible?: Set<string>,
): Promise<AudioBuffer> {
  const { bytes } = buildMidiWithChannels(song, { gains, audible });
  const midiBuffer = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;

  const [spessa, core, soundBankBuffer] = await Promise.all([
    import("spessasynth_lib"),
    import("spessasynth_core"),
    loadSoundBank(),
  ]);

  const midi = core.BasicMIDI.fromArrayBuffer(midiBuffer);
  const totalSeconds = Math.max(0.1, midi.duration + TAIL_SECONDS);
  const offlineContext = new OfflineAudioContext(
    2,
    Math.ceil(SAMPLE_RATE * totalSeconds),
    SAMPLE_RATE,
  );
  await offlineContext.audioWorklet.addModule(workletUrl());
  const synth = new spessa.WorkletSynthesizer(offlineContext);
  synth.connect(offlineContext.destination);
  await synth.startOfflineRender({
    midiSequence: midi,
    loopCount: 0,
    soundBankList: [{ bankOffset: 0, soundBankBuffer }],
  });
  return offlineContext.startRendering();
}

function floatToInt16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const value = Math.max(-1, Math.min(1, input[index]));
    output[index] = value < 0 ? value * 0x8000 : value * 0x7fff;
  }
  return output;
}

async function audioBufferToMp3Blob(buffer: AudioBuffer): Promise<Blob> {
  const lame = await import("@breezystack/lamejs");
  const channels = Math.min(2, buffer.numberOfChannels);
  const encoder = new lame.Mp3Encoder(channels, buffer.sampleRate, MP3_KBPS);
  const left = floatToInt16(buffer.getChannelData(0));
  const right = channels > 1 ? floatToInt16(buffer.getChannelData(1)) : left;

  const chunks: Uint8Array[] = [];
  for (let index = 0; index < left.length; index += MP3_FRAME) {
    const frame = encoder.encodeBuffer(
      left.subarray(index, index + MP3_FRAME),
      right.subarray(index, index + MP3_FRAME),
    );
    if (frame.length > 0) chunks.push(frame);
  }
  const tail = encoder.flush();
  if (tail.length > 0) chunks.push(tail);
  return new Blob(chunks as unknown as BlobPart[], { type: "audio/mpeg" });
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
  const anchor = document.createElement("a");
  const safeName = (song.header.genre || "song").replace(/[^a-z0-9-_]+/gi, "_").toLowerCase();
  anchor.href = url;
  anchor.download = `${safeName || "song"}.mp3`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
