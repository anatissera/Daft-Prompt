import test from "node:test";
import assert from "node:assert/strict";

import {
  createAnalysisProgress,
  updateAnalysisProgress,
} from "./analysisProgress.mjs";


test("progress marks stages active and completed without live counters", () => {
  let progress = createAnalysisProgress();
  progress = updateAnalysisProgress(progress, {
    type: "searching_sources",
    status: "started",
    message: "Searching sources.",
  });
  progress = updateAnalysisProgress(progress, {
    type: "searching_sources",
    status: "completed",
    message: "Searching sources.",
    elapsed_seconds: 344.2,
    cache_hit: false,
  });
  progress = updateAnalysisProgress(progress, {
    type: "fetching_pages",
    status: "started",
    message: "Fetching pages.",
  });

  assert.equal(progress.find((stage) => stage.id === "searching_sources").status, "completed");
  assert.equal(progress.find((stage) => stage.id === "searching_sources").elapsedSeconds, 344.2);
  assert.equal(progress.find((stage) => stage.id === "fetching_pages").status, "active");
});


test("cache hit sticks to completed research stages and keepalive adds no row", () => {
  let progress = createAnalysisProgress();
  progress = updateAnalysisProgress(progress, {
    type: "searching_sources",
    status: "completed",
    message: "Searching sources.",
    elapsed_seconds: 0.1,
    cache_hit: true,
  });
  const before = progress.length;
  progress = updateAnalysisProgress(progress, {
    type: "research_keepalive",
    status: "started",
    message: "Still researching.",
  });

  const stems = progress.find((stage) => stage.id === "searching_sources");
  assert.equal(progress.length, before);
  assert.equal(stems.cacheHit, true);
});
