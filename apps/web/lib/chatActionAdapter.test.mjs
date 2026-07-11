import assert from "node:assert/strict";
import test from "node:test";

import {
  chooseChatAction,
  createTextMessage,
  createAnalysisMessage,
  createChordDiagramMessage,
  createCompositionMessage,
} from "./chatActionAdapter.mjs";

test("chooseChatAction analyzes when a local file is attached", () => {
  assert.deepEqual(
    chooseChatAction({ prompt: "what key is this in?", hasSelectedFile: true }),
    { type: "analyze", messageText: "what key is this in?" },
  );
});

test("chooseChatAction defaults to chat for plain prompts", () => {
  assert.deepEqual(
    chooseChatAction({ prompt: "compose a slow blues", hasSelectedFile: false }),
    { type: "chat", messageText: "compose a slow blues" },
  );
});

test("normalizeMessageText fills in a default for empty prompts", () => {
  assert.equal(normalizeText(""), "Hello.");
  assert.equal(normalizeText("", true), "Analyze this audio.");
});

function normalizeText(prompt, hasFile = false) {
  return chooseChatAction({ prompt, hasSelectedFile: hasFile }).messageText;
}

test("message helpers create stable enriched chat messages", () => {
  const text = createTextMessage("assistant", "Hello", 0);
  assert.equal(text.id, "assistant-0");
  assert.equal(text.kind, "text");
  assert.equal(text.text, "Hello");

  const analysis = createAnalysisMessage("assistant", "Done", { reference_id: "ref_1" }, 1);
  assert.equal(analysis.kind, "analysis");
  assert.equal(analysis.profile.reference_id, "ref_1");

  const chords = createChordDiagramMessage("assistant", "Chords", {
    instrument: "piano",
    source_label: "Clocks by Coldplay",
    confidence: 0.8,
    sections: [
      {
        name: "intro",
        confidence: 0.8,
        chords: [{ chord: "Eb", notes: ["Eb", "G", "Bb"], midi_notes: [63, 67, 70] }],
      },
    ],
  }, 2);
  assert.equal(chords.kind, "chord_diagram");
  assert.equal(chords.playableChords.sections[0].chords[0].chord, "Eb");

  const composition = createCompositionMessage("assistant", "Generated", { job_id: "job_1" }, [], null, "director", 3);
  assert.equal(composition.kind, "composition");
  assert.equal(composition.result.job_id, "job_1");
});
