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

test("chat proxy forwards artist style profiles to the backend", () => {
  assert.match(routeSource, /artist_style_profiles/);
  assert.match(routeSource, /artistStyleProfiles/);
  assert.match(routeSource, /Array\.isArray/);
});

test("chat proxy bounds and forwards compact conversation context", () => {
  assert.match(routeSource, /conversation_context/);
  assert.match(routeSource, /conversationContext/);
  assert.match(routeSource, /slice\(-1600\)/);
});
