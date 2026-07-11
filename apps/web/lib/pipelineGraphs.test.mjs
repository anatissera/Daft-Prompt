import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";

const source = readFileSync(resolve("components/PipelineGraphs.tsx"), "utf8");

test("pipeline graphs describe connector-backed song knowledge", () => {
  assert.match(source, /Songsterr/);
  assert.match(source, /EvidenceClaim/);
  assert.match(source, /PlayablePart/);
  assert.match(source, /ToneProfile/);
  assert.match(source, /SongKnowledgeProfile/);
  assert.match(source, /ArtistStyleProfile/);
});

test("pipeline graphs describe the current composition graph and LLM schemas", () => {
  assert.match(source, /CompositionBrief/);
  assert.match(source, /StateGraph\(BandState\)/);
  assert.match(source, /director/);
  assert.match(source, /instrument_turn/);
  assert.match(source, /arbiter/);
  assert.match(source, /FallbackChatModel/);
  assert.match(source, /with_structured_output/);
  assert.match(source, /DirectorOutput/);
  assert.match(source, /InstrumentRevisionOutput/);
  assert.match(source, /piano roll/);
});

test("pipeline graphs stay centered on public evidence and generated-song projections", () => {
  assert.equal(/local audio|user-uploaded|file analysis/i.test(source), false);
  assert.match(source, /source attributed/);
  assert.match(source, /confidence kept visible/);
  assert.match(source, /tabs, piano keys, and piano roll/);
});
