import test from "node:test";
import assert from "node:assert/strict";

import {
  createAnalysisProgress,
  updateAnalysisProgress,
} from "./analysisProgress.mjs";


test("progress marks stages active and completed without live counters", () => {
  let progress = createAnalysisProgress();
  progress = updateAnalysisProgress(progress, {
    type: "separating_stems",
    status: "started",
    message: "Separating stems.",
  });
  progress = updateAnalysisProgress(progress, {
    type: "separating_stems",
    status: "completed",
    message: "Separating stems.",
    elapsed_seconds: 344.2,
    cache_hit: false,
  });
  progress = updateAnalysisProgress(progress, {
    type: "estimating_tempo_grid",
    status: "started",
    message: "Estimating tempo.",
  });

  assert.equal(progress.find((stage) => stage.id === "separating_stems").status, "completed");
  assert.equal(progress.find((stage) => stage.id === "separating_stems").elapsedSeconds, 344.2);
  assert.equal(progress.find((stage) => stage.id === "estimating_tempo_grid").status, "active");
});


test("cache hit changes the completed stem label and keepalive adds no row", () => {
  let progress = createAnalysisProgress();
  progress = updateAnalysisProgress(progress, {
    type: "separating_stems",
    status: "completed",
    message: "Separating stems.",
    elapsed_seconds: 0.1,
    cache_hit: true,
  });
  const before = progress.length;
  progress = updateAnalysisProgress(progress, {
    type: "analysis_keepalive",
    status: "started",
    message: "Still analyzing.",
  });

  const stems = progress.find((stage) => stage.id === "separating_stems");
  assert.equal(progress.length, before);
  assert.equal(stems.cacheHit, true);
});
