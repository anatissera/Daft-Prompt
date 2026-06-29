import assert from "node:assert/strict";
import test from "node:test";

import { chooseChatAction, createTextMessage, createAnalysisMessage, createCompositionMessage } from "./chatActionAdapter.mjs";

test("chooseChatAction researches song questions when no profile is active", () => {
  assert.deepEqual(
    chooseChatAction({
      prompt: "what key is Every Breath You Take in?",
      hasReferenceProfile: false,
    }),
    { type: "research", messageText: "what key is Every Breath You Take in?" },
  );
});

test("chooseChatAction answers reference questions from the current profile", () => {
  assert.deepEqual(
    chooseChatAction({
      prompt: "What chords are probably in the chorus?",
      hasReferenceProfile: true,
    }),
    { type: "answer_reference", messageText: "What chords are probably in the chorus?" },
  );
});

test("chooseChatAction composes when there is no reference question", () => {
  assert.deepEqual(
    chooseChatAction({
      prompt: "",
      hasReferenceProfile: true,
    }),
    { type: "compose", messageText: "Compose a short song." },
  );
});

test("message helpers create stable enriched chat messages", () => {
  const text = createTextMessage("assistant", "Hello", 0);
  assert.equal(text.id, "assistant-0");
  assert.equal(text.kind, "text");
  assert.equal(text.text, "Hello");

  const analysis = createAnalysisMessage("assistant", "Done", { reference_id: "ref_1" }, 1);
  assert.equal(analysis.kind, "analysis");
  assert.equal(analysis.profile.reference_id, "ref_1");

  const composition = createCompositionMessage("assistant", "Generated", { job_id: "job_1" }, [], null, "director", 2);
  assert.equal(composition.kind, "composition");
  assert.equal(composition.result.job_id, "job_1");
});
