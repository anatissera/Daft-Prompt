// Pure geometry helpers for piano-roll views. No DOM or audio state lives here.

export const KEYBOARD_LOW = 21; // A0
export const KEYBOARD_HIGH = 108; // C8
export const DEFAULT_PX_PER_SEC = 150;

const WHITE_SEMITONES = new Set([0, 2, 4, 5, 7, 9, 11]);
const WHITE_LETTERS = ["C", "D", "E", "F", "G", "A", "B"];

export function isBlackKey(midi) {
  return !WHITE_SEMITONES.has(((midi % 12) + 12) % 12);
}

export function clampPitch(midi, low = KEYBOARD_LOW, high = KEYBOARD_HIGH) {
  if (midi < low) return low;
  if (midi > high) return high;
  return midi;
}

export function whiteKeyLetter(midi) {
  const semitone = ((midi % 12) + 12) % 12;
  if (!WHITE_SEMITONES.has(semitone)) return "";
  const order = [0, -1, 1, -1, 2, 3, -1, 4, -1, 5, -1, 6];
  return WHITE_LETTERS[order[semitone]];
}

export function buildKeyboardKeys(low = KEYBOARD_LOW, high = KEYBOARD_HIGH) {
  const keys = [];
  let whiteIndex = -1;
  for (let midi = low; midi <= high; midi += 1) {
    const black = isBlackKey(midi);
    if (!black) whiteIndex += 1;
    keys.push({ midi, black, whiteIndex });
  }
  return { keys, whiteCount: whiteIndex + 1, low, high };
}

export function keyGeometry(keyboard, width, options = {}) {
  const whiteWidth = keyboard.whiteCount > 0 ? width / keyboard.whiteCount : width;
  const blackWidth = whiteWidth * (options.blackWidthRatio ?? 0.62);
  const keys = [];
  const byMidi = new Map();
  for (const key of keyboard.keys) {
    let rect;
    if (!key.black) {
      const x = key.whiteIndex * whiteWidth;
      rect = { midi: key.midi, black: false, x, width: whiteWidth, centerX: x + whiteWidth / 2 };
    } else {
      const boundary = (key.whiteIndex + 1) * whiteWidth;
      rect = { midi: key.midi, black: true, x: boundary - blackWidth / 2, width: blackWidth, centerX: boundary };
    }
    keys.push(rect);
    byMidi.set(key.midi, rect);
  }
  return { whiteWidth, blackWidth, keys, byMidi };
}

export function noteColumn(geometry, midi, low = KEYBOARD_LOW, high = KEYBOARD_HIGH) {
  return geometry.byMidi.get(clampPitch(midi, low, high)) ?? null;
}

export function noteRectY(startSeconds, durationSeconds, currentTime, hitLineY, pxPerSec) {
  const bottom = hitLineY - (startSeconds - currentTime) * pxPerSec;
  const top = bottom - durationSeconds * pxPerSec;
  return { top, bottom, height: bottom - top };
}

export function lookaheadSeconds(hitLineY, pxPerSec) {
  return pxPerSec > 0 ? hitLineY / pxPerSec : 0;
}

export function isNoteVisible(startSeconds, durationSeconds, currentTime, hitLineY, pxPerSec) {
  return (
    startSeconds + durationSeconds > currentTime
    && startSeconds < currentTime + lookaheadSeconds(hitLineY, pxPerSec)
  );
}

export function isNoteActive(startSeconds, durationSeconds, currentTime) {
  return startSeconds <= currentTime && currentTime < startSeconds + durationSeconds;
}

export function secondsPerBar(header) {
  const secondsPerBeat = 60 / header.tempo_bpm;
  const [numerator, denominator] = header.time_signature;
  return numerator * (4 / denominator) * secondsPerBeat;
}

export function barLinesInView(header, currentTime, hitLineY, pxPerSec, totalBars) {
  const spBar = secondsPerBar(header);
  if (!(spBar > 0)) return [];
  const horizon = currentTime + lookaheadSeconds(hitLineY, pxPerSec);
  const lines = [];
  const firstBar = Math.max(0, Math.floor(currentTime / spBar));
  for (let bar = firstBar; bar * spBar <= horizon; bar += 1) {
    if (totalBars != null && bar > totalBars) break;
    lines.push({ bar, y: hitLineY - (bar * spBar - currentTime) * pxPerSec });
  }
  return lines;
}

export function formatTime(value) {
  const safe = Number.isFinite(value) ? Math.max(0, value) : 0;
  const minutes = Math.floor(safe / 60);
  const seconds = Math.floor(safe % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
