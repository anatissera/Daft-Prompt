/// <reference lib="webworker" />
// MP3 encoding worker. lamejs encodes ~3 minutes of 44.1kHz stereo in pure
// JS — run on the main thread that froze the whole page for seconds every
// time the user hit the MP3 button. The float→int16 conversion and the
// frame loop both live here now; the page only ships Float32Array channel
// copies in and receives the finished MP3 bytes back (both transferred,
// not cloned).

import { Mp3Encoder } from "@breezystack/lamejs";

const MP3_FRAME = 1152;

interface EncodeRequest {
  left: Float32Array;
  right: Float32Array | null;
  sampleRate: number;
  kbps: number;
}

function floatToInt16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const v = Math.max(-1, Math.min(1, input[i]));
    out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  return out;
}

self.onmessage = (event: MessageEvent<EncodeRequest>) => {
  try {
    const { left, right, sampleRate, kbps } = event.data;
    const channels = right ? 2 : 1;
    const encoder = new Mp3Encoder(channels, sampleRate, kbps);
    const l16 = floatToInt16(left);
    const r16 = right ? floatToInt16(right) : l16;

    const chunks: Uint8Array[] = [];
    for (let i = 0; i < l16.length; i += MP3_FRAME) {
      const frame = encoder.encodeBuffer(
        l16.subarray(i, i + MP3_FRAME),
        r16.subarray(i, i + MP3_FRAME),
      );
      if (frame.length > 0) chunks.push(frame);
    }
    const tail = encoder.flush();
    if (tail.length > 0) chunks.push(tail);

    let total = 0;
    for (const c of chunks) total += c.length;
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const c of chunks) {
      bytes.set(c, offset);
      offset += c.length;
    }
    (self as unknown as Worker).postMessage({ bytes }, [bytes.buffer]);
  } catch (err) {
    (self as unknown as Worker).postMessage({ error: String((err as Error).message ?? err) });
  }
};
