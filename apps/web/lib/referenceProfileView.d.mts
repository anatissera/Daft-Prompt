import type { ConfidenceLabel, ReferenceProfile } from "./types";

export interface DisplayChordEstimate {
  label: string;
  timeRange: string;
  confidence: string;
}

export function formatDuration(seconds: number): string;

export function formatPercent(value: number): string;

export function formatConfidence(label: ConfidenceLabel, value: number): string;

export function describeReferenceSummary(profile: ReferenceProfile): string[];

export function getTopChordEstimates(profile: ReferenceProfile, limit?: number): DisplayChordEstimate[];

export function isReferenceQuestion(prompt: string): boolean;

export function answerReferenceQuestion(prompt: string, profile: ReferenceProfile): string;

export function confidenceLabel(value: number): ConfidenceLabel;
