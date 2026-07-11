export const KEYBOARD_LOW: number;
export const KEYBOARD_HIGH: number;
export const DEFAULT_PX_PER_SEC: number;

export interface KeyboardKey {
  midi: number;
  black: boolean;
  whiteIndex: number;
}

export interface Keyboard {
  keys: KeyboardKey[];
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

export function isBlackKey(midi: number): boolean;
export function clampPitch(midi: number, low?: number, high?: number): number;
export function whiteKeyLetter(midi: number): string;
export function buildKeyboardKeys(low?: number, high?: number): Keyboard;
export function keyGeometry(keyboard: Keyboard, width: number, options?: { blackWidthRatio?: number }): KeyboardGeometry;
export function noteColumn(geometry: KeyboardGeometry, midi: number, low?: number, high?: number): KeyRect | null;
export function noteRectY(
  startSeconds: number,
  durationSeconds: number,
  currentTime: number,
  hitLineY: number,
  pxPerSec: number,
): { top: number; bottom: number; height: number };
export function lookaheadSeconds(hitLineY: number, pxPerSec: number): number;
export function isNoteVisible(
  startSeconds: number,
  durationSeconds: number,
  currentTime: number,
  hitLineY: number,
  pxPerSec: number,
): boolean;
export function isNoteActive(startSeconds: number, durationSeconds: number, currentTime: number): boolean;
export function secondsPerBar(header: { tempo_bpm: number; time_signature: [number, number] }): number;
export function barLinesInView(
  header: { tempo_bpm: number; time_signature: [number, number] },
  currentTime: number,
  hitLineY: number,
  pxPerSec: number,
  totalBars?: number,
): Array<{ bar: number; y: number }>;
export function formatTime(value: number): string;
