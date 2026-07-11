import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const generatedSongSource = await readFile(new URL("../components/GeneratedSongBlock.tsx", import.meta.url), "utf8");
const pianoRollSource = await readFile(new URL("../components/PianoRoll.tsx", import.meta.url), "utf8");

test("generated song view gates the static piano roll behind a collapsed details panel", () => {
  assert.match(generatedSongSource, /<details[\s\S]*piano-roll-panel/);
  assert.match(generatedSongSource, /pianoRollOpen/);
  assert.match(generatedSongSource, /pianoRollOpen \? <PianoRoll song=\{song\} audibleTrackIds=\{audibleTrackIds\}/);
  assert.match(pianoRollSource, /buildTrackEvents/);
  assert.match(pianoRollSource, /secondsPerBar/);
});
