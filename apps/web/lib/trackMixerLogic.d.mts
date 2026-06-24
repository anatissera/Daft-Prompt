import type { SongState } from "./types";

export interface TrackEvent {
  durationSeconds: number;
  frequency: number;
  pitch: number;
  startSeconds: number;
  velocity: number;
}

export function getAudibleTrackIds(
  trackIds: string[],
  mutedTrackIds: Set<string>,
  soloTrackIds: Set<string>,
): Set<string>;

export function midiToFrequency(pitch: number): number;

export function buildTrackEvents(song: Pick<SongState, "header" | "parts">): Record<string, TrackEvent[]>;

export function getSongDurationSeconds(song: Pick<SongState, "header" | "parts">): number;
