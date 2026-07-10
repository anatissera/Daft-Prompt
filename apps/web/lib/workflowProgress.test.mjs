import test from "node:test";
import assert from "node:assert/strict";
import { WORKFLOW_STAGES, classifyChatWorkflow, workflowBusyLabel } from "./workflowProgress.mjs";

test("research requests never receive composition progress", () => {
  assert.equal(classifyChatWorkflow("Look up Adiós by Gustavo Cerati"), "research");
  assert.deepEqual(WORKFLOW_STAGES.research, [
    "Searching sources", "Reading evidence", "Extracting musical facts",
    "Building reference profile", "Preparing answer",
  ]);
  assert.equal(WORKFLOW_STAGES.research.some((stage) => /director|instrument agents|MIDI/i.test(stage)), false);
});

test("composition and iterative editing get distinct progress contracts", () => {
  assert.equal(classifyChatWorkflow("Compose a punk sketch"), "composition");
  assert.equal(classifyChatWorkflow("Make the guitar less busy", { hasCurrentSong: true }), "editing");
  assert.match(workflowBusyLabel("editing"), /Updating/);
  assert.equal(WORKFLOW_STAGES.editing.includes("Validating preserved parts"), true);
});
