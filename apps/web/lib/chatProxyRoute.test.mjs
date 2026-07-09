import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { resolve } from "node:path";

const routeSource = readFileSync(resolve("app/api/chat/route.ts"), "utf8");

test("chat proxy uses native fetch without an incompatible undici dispatcher", () => {
  assert.equal(routeSource.includes('from "undici"'), false);
  assert.equal(routeSource.includes("dispatcher:"), false);
});

test("chat proxy preserves the long-running route duration", () => {
  assert.match(routeSource, /export const maxDuration = 300/);
});

test("chat proxy forwards current song context to the backend", () => {
  assert.match(routeSource, /current_song/);
  assert.match(routeSource, /currentSong/);
});
