import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../components/ScoreViewer.tsx", import.meta.url), "utf8");

test("score rendering exposes loading, failure, and retry states", () => {
  assert.match(source, /response\.ok/);
  assert.match(source, /Notation is unavailable/);
  assert.match(source, /Retry score/);
  assert.match(source, /\.catch\(/);
});
