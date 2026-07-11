// Pure geometry for the falling-notes piano roll. No DOM, no audio — every
// function here is a plain calculation so the rendering component stays thin
// and the math is unit-tested in isolation (see pianoRollLayout.test.mjs).
//
// Coordinate convention: the keyboard sits at the bottom of the stage and the
// hit line runs across its top edge at y = hitLineY. Notes fall downward, so a
// point in time `tau` maps to y(tau) = hitLineY - (tau - currentTime) * pxPerSec.
// A note occupies [start, start + duration] in time, so its leading (lower)
// edge touches the hit line exactly when currentTime === start.

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

/** White-key letter (no octave) for labelling the keyboard, or "" for blacks. */
export function whiteKeyLetter(midi) {
  const semitone = ((midi % 12) + 12) % 12;
  if (!WHITE_SEMITONES.has(semitone)) return "";
  // Index into the white-letter sequence starting at C.
  const order = [0, -1, 1, -1, 2, 3, -1, 4, -1, 5, -1, 6];
  return WHITE_LETTERS[order[semitone]];
}

/** Ordered key descriptors across [low, high]. Black keys carry the index of
 *  the white key immediately to their left so they can be centred on the gap. */
export function buildKeyboardKeys(low = KEYBOARD_LOW, high = KEYBOARD_HIGH) {
  const keys = [];
  let whiteIndex = -1;
  for (let midi = low; midi <= high; midi++) {
    const black = isBlackKey(midi);
    if (!black) whiteIndex += 1;
    keys.push({ midi, black, whiteIndex });
  }
  return { keys, whiteCount: whiteIndex + 1, low, high };
}

/** Turn a keyboard into pixel rectangles for a given total width. Returns each
 *  key's x/width/centerX plus a Map from midi → rect for O(1) note lookup. */
export function keyGeometry(keyboard, width, options = {}) {
  const whiteWidth = keyboard.whiteCount > 0 ? width / keyboard.whiteCount : width;
  const blackWidth = whiteWidth * (options.blackWidthRatio ?? 0.62);
  const keys = [];
  const byMidi = new Map();
  for (const k of keyboard.keys) {
    let rect;
    if (!k.black) {
      const x = k.whiteIndex * whiteWidth;
      rect = { midi: k.midi, black: false, x, width: whiteWidth, centerX: x + whiteWidth / 2 };
    } else {
      const boundary = (k.whiteIndex + 1) * whiteWidth;
      rect = { midi: k.midi, black: true, x: boundary - blackWidth / 2, width: blackWidth, centerX: boundary };
    }
    keys.push(rect);
    byMidi.set(k.midi, rect);
  }
  return { whiteWidth, blackWidth, keys, byMidi };
}

/** Column (x/width) a falling note should occupy, clamped into the keyboard. */
export function noteColumn(geometry, midi, low = KEYBOARD_LOW, high = KEYBOARD_HIGH) {
  return geometry.byMidi.get(clampPitch(midi, low, high)) ?? null;
}

/** Vertical extent of a note rectangle at the current playback time. */
export function noteRectY(startSeconds, durationSeconds, currentTime, hitLineY, pxPerSec) {
  const bottom = hitLineY - (startSeconds - currentTime) * pxPerSec;
  const top = bottom - durationSeconds * pxPerSec;
  return { top, bottom, height: bottom - top };
}

/** How many seconds of future notes fit between the top of the roll and the
 *  hit line — the culling horizon. */
export function lookaheadSeconds(hitLineY, pxPerSec) {
  return pxPerSec > 0 ? hitLineY / pxPerSec : 0;
}

/** A note is on-screen when it has not fully passed and has not-yet-entered. */
export function isNoteVisible(startSeconds, durationSeconds, currentTime, hitLineY, pxPerSec) {
  return (
    startSeconds + durationSeconds > currentTime &&
    startSeconds < currentTime + lookaheadSeconds(hitLineY, pxPerSec)
  );
}

/** A note's key is lit while the playhead is inside its span. */
export function isNoteActive(startSeconds, durationSeconds, currentTime) {
  return startSeconds <= currentTime && currentTime < startSeconds + durationSeconds;
}

export function secondsPerBar(header) {
  const secondsPerBeat = 60 / header.tempo_bpm;
  const [numerator, denominator] = header.time_signature;
  return numerator * (4 / denominator) * secondsPerBeat;
}

/** Bar lines (with their bar number) currently within the roll viewport. */
export function barLinesInView(header, currentTime, hitLineY, pxPerSec, totalBars) {
  const spBar = secondsPerBar(header);
  if (!(spBar > 0)) return [];
  const horizon = currentTime + lookaheadSeconds(hitLineY, pxPerSec);
  const lines = [];
  const firstBar = Math.max(0, Math.floor(currentTime / spBar));
  for (let bar = firstBar; bar * spBar <= horizon; bar++) {
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
