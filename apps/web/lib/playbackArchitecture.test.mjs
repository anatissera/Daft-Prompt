import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../components/TrackMixer.tsx", import.meta.url), "utf8");

test("generated-song playback has no runtime soundfont or sample-host dependency", () => {
  assert.doesNotMatch(source, /gleitz\.github\.io|FLUIDR3_BASE|Tone\.Sampler|baseUrl/);
  assert.match(source, /makeLocalVoice/);
  assert.match(source, /Tone\.PolySynth/);
});
