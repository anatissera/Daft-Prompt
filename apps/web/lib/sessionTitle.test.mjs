import assert from "node:assert/strict";
import test from "node:test";

import { deriveSessionTitle } from "./sessionTitle.mjs";

test("title-cases the first few words of the message", () => {
  assert.equal(deriveSessionTitle("compose a slow blues in F minor"), "Compose a Slow Blues in");
});

test("keeps small words lowercase except when leading", () => {
  assert.equal(deriveSessionTitle("the funky bassline"), "The Funky Bassline");
});

test("strips punctuation and collapses whitespace", () => {
  assert.equal(deriveSessionTitle("  make me a flute song!!!  "), "Make Me a Flute Song");
});

test("returns empty string for empty or whitespace input", () => {
  assert.equal(deriveSessionTitle(""), "");
  assert.equal(deriveSessionTitle("   "), "");
});

test("returns empty string for non-string input", () => {
  assert.equal(deriveSessionTitle(undefined), "");
  assert.equal(deriveSessionTitle(null), "");
});

test("caps the title length", () => {
  const title = deriveSessionTitle("supercalifragilistic expialidocious antidisestablishmentarianism");
  assert.ok(title.length <= 60);
});
