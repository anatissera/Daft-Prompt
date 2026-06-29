export const ANALYSIS_STAGES = [
  ["searching_sources", "Source search"],
  ["fetching_pages", "Page fetch"],
  ["extracting_claims", "Claim extraction"],
  ["fusing_evidence", "Evidence fusion"],
];


export function createAnalysisProgress() {
  return ANALYSIS_STAGES.map(([id, label]) => ({
    id,
    label,
    status: "pending",
    elapsedSeconds: null,
    cacheHit: false,
  }));
}


export function updateAnalysisProgress(progress, event) {
  if (event.type === "accepted" || event.type === "research_keepalive") {
    return progress;
  }
  return progress.map((stage) => {
    if (stage.id !== event.type) return stage;
    return {
      ...stage,
      status: event.status === "completed" ? "completed" : "active",
      elapsedSeconds:
        event.status === "completed" && typeof event.elapsed_seconds === "number"
          ? event.elapsed_seconds
          : stage.elapsedSeconds,
      cacheHit: event.cache_hit === true || stage.cacheHit,
    };
  });
}
