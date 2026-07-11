import assert from "node:assert/strict";
import { test } from "node:test";

import {
  barLinesInView,
  buildKeyboardKeys,
  clampPitch,
  isBlackKey,
  isNoteActive,
  isNoteVisible,
  keyGeometry,
  noteColumn,
  noteRectY,
  secondsPerBar,
  whiteKeyLetter,
} from "./pianoRollLayout.mjs";

test("isBlackKey identifies the five accidentals per octave", () => {
  assert.equal(isBlackKey(60), false);
  assert.equal(isBlackKey(61), true);
  assert.equal(isBlackKey(69), false);
  assert.equal(isBlackKey(70), true);
});

test("whiteKeyLetter labels naturals and blanks accidentals", () => {
  assert.equal(whiteKeyLetter(60), "C");
  assert.equal(whiteKeyLetter(69), "A");
  assert.equal(whiteKeyLetter(61), "");
});

test("buildKeyboardKeys spans 88 keys with 52 whites", () => {
  const keyboard = buildKeyboardKeys();

  assert.equal(keyboard.keys.length, 88);
  assert.equal(keyboard.whiteCount, 52);
  assert.equal(keyboard.keys[0].midi, 21);
  assert.equal(keyboard.keys[87].midi, 108);
});

test("keyGeometry tiles white keys edge-to-edge across the width", () => {
  const geometry = keyGeometry(buildKeyboardKeys(), 520);
  const firstWhite = geometry.keys.find((key) => !key.black);
  const lastWhite = [...geometry.keys].reverse().find((key) => !key.black);

  assert.equal(geometry.whiteWidth, 10);
  assert.equal(firstWhite.x, 0);
  assert.equal(firstWhite.width, 10);
  assert.ok(Math.abs(lastWhite.x + lastWhite.width - 520) < 1e-9);
});

test("noteColumn clamps out-of-range pitches into the keyboard", () => {
  const geometry = keyGeometry(buildKeyboardKeys(), 520);

  assert.equal(noteColumn(geometry, 5).midi, 21);
  assert.equal(noteColumn(geometry, 127).midi, 108);
  assert.equal(clampPitch(200), 108);
});

test("noteRectY places the leading edge on the hit line at note start", () => {
  const atStart = noteRectY(2, 1, 2, 300, 150);
  const before = noteRectY(2, 1, 1, 300, 150);

  assert.equal(atStart.bottom, 300);
  assert.equal(atStart.height, 150);
  assert.equal(before.bottom, 150);
});

test("isNoteVisible culls passed and not-yet-entered notes", () => {
  assert.equal(isNoteVisible(2, 1, 2, 300, 150), true);
  assert.equal(isNoteVisible(0, 1, 5, 300, 150), false);
  assert.equal(isNoteVisible(10, 1, 2, 300, 150), false);
  assert.equal(isNoteVisible(3.5, 1, 2, 300, 150), true);
});

test("isNoteActive is true only while the playhead is inside the span", () => {
  assert.equal(isNoteActive(2, 1, 2), true);
  assert.equal(isNoteActive(2, 1, 2.9), true);
  assert.equal(isNoteActive(2, 1, 3), false);
  assert.equal(isNoteActive(2, 1, 1.9), false);
});

test("secondsPerBar respects tempo and time signature", () => {
  assert.equal(secondsPerBar({ tempo_bpm: 120, time_signature: [4, 4] }), 2);
  assert.equal(secondsPerBar({ tempo_bpm: 120, time_signature: [3, 4] }), 1.5);
  assert.equal(secondsPerBar({ tempo_bpm: 60, time_signature: [6, 8] }), 3);
});

test("barLinesInView returns the bars within the viewport horizon", () => {
  const header = { tempo_bpm: 120, time_signature: [4, 4] };
  const lines = barLinesInView(header, 0, 300, 150);

  assert.deepEqual(lines.map((line) => line.bar), [0, 1]);
  assert.equal(lines[0].y, 300);
  assert.equal(lines[1].y, 0);
});

test("barLinesInView stops at totalBars", () => {
  const header = { tempo_bpm: 120, time_signature: [4, 4] };
  const lines = barLinesInView(header, 0, 900, 150, 1);

  assert.deepEqual(lines.map((line) => line.bar), [0, 1]);
});
