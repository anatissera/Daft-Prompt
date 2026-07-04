import type { AnalysisProgressEvent } from "./types";

export interface AnalysisStageState {
  id: AnalysisProgressEvent["type"];
  label: string;
  status: "pending" | "active" | "completed";
  elapsedSeconds: number | null;
  cacheHit: boolean;
}

export const ANALYSIS_STAGES: ReadonlyArray<readonly [AnalysisStageState["id"], string]>;
export function createAnalysisProgress(): AnalysisStageState[];
export function updateAnalysisProgress(
  progress: AnalysisStageState[],
  event: AnalysisProgressEvent,
): AnalysisStageState[];
