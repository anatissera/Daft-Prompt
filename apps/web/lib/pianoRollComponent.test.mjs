import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const generatedSongSource = await readFile(new URL("../components/GeneratedSongBlock.tsx", import.meta.url), "utf8");
const pianoRollSource = await readFile(new URL("../components/PianoRoll.tsx", import.meta.url), "utf8");

test("generated song view includes the static piano roll", () => {
  assert.match(generatedSongSource, /<PianoRoll song=\{song\} audibleTrackIds=\{audibleTrackIds\}/);
  assert.match(pianoRollSource, /buildTrackEvents/);
  assert.match(pianoRollSource, /secondsPerBar/);
});
