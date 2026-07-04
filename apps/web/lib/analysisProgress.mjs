export const ANALYSIS_STAGES = [
  ["separating_stems", "Stem separation"],
  ["building_harmonic_source", "Harmonic source"],
  ["estimating_tempo_grid", "Tempo / grid"],
  ["estimating_key", "Key analysis"],
  ["estimating_chords", "Chord analysis"],
  ["extracting_stem_features", "Stem features"],
  ["detecting_structure", "Structure analysis"],
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
  if (event.type === "accepted" || event.type === "analysis_keepalive") {
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
