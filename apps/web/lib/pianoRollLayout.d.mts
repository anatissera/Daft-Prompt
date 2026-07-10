import type { Header } from "./types";

export const KEYBOARD_LOW: number;
export const KEYBOARD_HIGH: number;
export const DEFAULT_PX_PER_SEC: number;

export interface KeyDescriptor {
  midi: number;
  black: boolean;
  whiteIndex: number;
}

export interface Keyboard {
  keys: KeyDescriptor[];
  whiteCount: number;
  low: number;
  high: number;
}

export interface KeyRect {
  midi: number;
  black: boolean;
  x: number;
  width: number;
  centerX: number;
}

export interface KeyboardGeometry {
  whiteWidth: number;
  blackWidth: number;
  keys: KeyRect[];
  byMidi: Map<number, KeyRect>;
}

export interface NoteRect {
  top: number;
  bottom: number;
  height: number;
}

export interface BarLine {
  bar: number;
  y: number;
}

export function isBlackKey(midi: number): boolean;
export function clampPitch(midi: number, low?: number, high?: number): number;
export function whiteKeyLetter(midi: number): string;
export function buildKeyboardKeys(low?: number, high?: number): Keyboard;
export function keyGeometry(
  keyboard: Keyboard,
  width: number,
  options?: { blackWidthRatio?: number },
): KeyboardGeometry;
export function noteColumn(
  geometry: KeyboardGeometry,
  midi: number,
  low?: number,
  high?: number,
): KeyRect | null;
export function noteRectY(
  startSeconds: number,
  durationSeconds: number,
  currentTime: number,
  hitLineY: number,
  pxPerSec: number,
): NoteRect;
export function lookaheadSeconds(hitLineY: number, pxPerSec: number): number;
export function isNoteVisible(
  startSeconds: number,
  durationSeconds: number,
  currentTime: number,
  hitLineY: number,
  pxPerSec: number,
): boolean;
export function isNoteActive(
  startSeconds: number,
  durationSeconds: number,
  currentTime: number,
): boolean;
export function secondsPerBar(header: Pick<Header, "tempo_bpm" | "time_signature">): number;
export function barLinesInView(
  header: Pick<Header, "tempo_bpm" | "time_signature">,
  currentTime: number,
  hitLineY: number,
  pxPerSec: number,
  totalBars?: number,
): BarLine[];
export function formatTime(value: number): string;
