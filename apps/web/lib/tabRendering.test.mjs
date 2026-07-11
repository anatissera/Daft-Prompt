import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../components/TabExcerptBlock.tsx", import.meta.url), "utf8");

test("tab renderer displays string/fret content and an explicit failure attachment", () => {
  assert.match(source, /string \$\{event\.string\}/);
  assert.match(source, /fret \$\{event\.fret\}/);
  assert.match(source, /drumLabel/);
  assert.match(source, /kind === "piano"/);
  assert.match(source, /role="alert"/);
  assert.match(source, /Tab unavailable/);
});
