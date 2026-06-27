import type { ConfidenceLabel, ReferenceProfile } from "./types";

export interface DisplayChordEstimate {
  label: string;
  timeRange: string;
  confidence: string;
}

export interface DisplayKeyCandidate {
  label: string;
  confidence: string;
}

export interface DisplayProgression {
  label: string;
  bars: string;
  repetitions: number;
  confidence: string;
}

export interface DisplayStructureSection {
  label: string;
  bars: string;
  timeRange: string;
  progression: string;
  confidence: string;
}

export interface DisplayAnalysisNote {
  label: string;
  message: string;
}

export interface DisplayLegacyEnergySection {
  name: string;
  timeRange: string;
  energy: number;
  confidence: string;
}

export function formatDuration(seconds: number): string;

export function formatPercent(value: number): string;

export function formatConfidence(label: ConfidenceLabel, value: number): string;

export function describeReferenceSummary(profile: ReferenceProfile): string[];

export function getTopChordEstimates(profile: ReferenceProfile, limit?: number): DisplayChordEstimate[];

export function getKeyCandidateSummary(profile: ReferenceProfile, limit?: number): DisplayKeyCandidate[];

export function getMainProgression(profile: ReferenceProfile): DisplayProgression | null;

export function getStructureTimeline(profile: ReferenceProfile): DisplayStructureSection[];

export function getAnalysisNotes(profile: ReferenceProfile): DisplayAnalysisNote[];

export function getLegacyEnergySections(profile: ReferenceProfile): DisplayLegacyEnergySection[];

export function isReferenceQuestion(prompt: string): boolean;

export function answerReferenceQuestion(prompt: string, profile: ReferenceProfile): string;

export function confidenceLabel(value: number): ConfidenceLabel;
