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

test("isBlackKey identifies the five sharps per octave", () => {
  assert.equal(isBlackKey(60), false); // C4
  assert.equal(isBlackKey(61), true); // C#4
  assert.equal(isBlackKey(69), false); // A4
  assert.equal(isBlackKey(70), true); // A#4
});

test("whiteKeyLetter labels naturals and blanks accidentals", () => {
  assert.equal(whiteKeyLetter(60), "C");
  assert.equal(whiteKeyLetter(69), "A");
  assert.equal(whiteKeyLetter(61), "");
});

test("buildKeyboardKeys spans 88 keys with 52 whites", () => {
  const kb = buildKeyboardKeys();
  assert.equal(kb.keys.length, 88);
  assert.equal(kb.whiteCount, 52);
  assert.equal(kb.keys[0].midi, 21);
  assert.equal(kb.keys[87].midi, 108);
});

test("keyGeometry tiles white keys edge-to-edge across the width", () => {
  const kb = buildKeyboardKeys();
  const geo = keyGeometry(kb, 520); // 10px per white key
  assert.equal(geo.whiteWidth, 10);
  const firstWhite = geo.keys.find((k) => !k.black);
  assert.equal(firstWhite.x, 0);
  assert.equal(firstWhite.width, 10);
  const lastWhite = [...geo.keys].reverse().find((k) => !k.black);
  assert.ok(Math.abs(lastWhite.x + lastWhite.width - 520) < 1e-9);
});

test("keyGeometry centres black keys on the white-key boundary", () => {
  const kb = buildKeyboardKeys();
  const geo = keyGeometry(kb, 520);
  const cSharp = geo.byMidi.get(61); // C#, boundary is after white index for C4
  assert.ok(cSharp.black);
  assert.ok(cSharp.width < geo.whiteWidth);
  // centerX equals the shared boundary between neighbouring white keys.
  assert.ok(Math.abs(cSharp.centerX - (cSharp.x + cSharp.width / 2)) < 1e-9);
});

test("noteColumn clamps out-of-range pitches into the keyboard", () => {
  const geo = keyGeometry(buildKeyboardKeys(), 520);
  assert.equal(noteColumn(geo, 5).midi, 21); // below A0 → A0
  assert.equal(noteColumn(geo, 127).midi, 108); // above C8 → C8
  assert.equal(clampPitch(200), 108);
});

test("noteRectY places the leading edge on the hit line at note start", () => {
  const hit = 300;
  const pps = 150;
  // At currentTime === start, the note's bottom sits exactly on the hit line.
  const atStart = noteRectY(2, 1, 2, hit, pps);
  assert.equal(atStart.bottom, hit);
  assert.equal(atStart.height, pps); // 1 second tall
  // One second earlier the whole rect is one screen-second above.
  const before = noteRectY(2, 1, 1, hit, pps);
  assert.equal(before.bottom, hit - pps);
});

test("isNoteVisible culls passed and not-yet-entered notes", () => {
  const hit = 300;
  const pps = 150; // lookahead horizon = 2 seconds
  assert.equal(isNoteVisible(2, 1, 2, hit, pps), true); // playing now
  assert.equal(isNoteVisible(0, 1, 5, hit, pps), false); // long gone
  assert.equal(isNoteVisible(10, 1, 2, hit, pps), false); // beyond horizon
  assert.equal(isNoteVisible(3.5, 1, 2, hit, pps), true); // within 2s horizon
});

test("isNoteActive is true only while the playhead is inside the span", () => {
  assert.equal(isNoteActive(2, 1, 2), true);
  assert.equal(isNoteActive(2, 1, 2.9), true);
  assert.equal(isNoteActive(2, 1, 3), false); // exclusive end
  assert.equal(isNoteActive(2, 1, 1.9), false);
});

test("secondsPerBar respects tempo and time signature", () => {
  assert.equal(secondsPerBar({ tempo_bpm: 120, time_signature: [4, 4] }), 2);
  assert.equal(secondsPerBar({ tempo_bpm: 120, time_signature: [3, 4] }), 1.5);
  assert.equal(secondsPerBar({ tempo_bpm: 60, time_signature: [6, 8] }), 3);
});

test("barLinesInView returns the bars within the viewport horizon", () => {
  const header = { tempo_bpm: 120, time_signature: [4, 4] }; // 2s per bar
  const lines = barLinesInView(header, 0, 300, 150); // horizon = 2s → bars 0 and 1
  assert.deepEqual(lines.map((l) => l.bar), [0, 1]);
  assert.equal(lines[0].y, 300); // bar 0 at the hit line
  assert.equal(lines[1].y, 0); // bar 1 at the top of the roll
});

test("barLinesInView stops at totalBars", () => {
  const header = { tempo_bpm: 120, time_signature: [4, 4] };
  const lines = barLinesInView(header, 0, 900, 150, 1); // horizon covers 3 bars, capped at 1
  assert.deepEqual(lines.map((l) => l.bar), [0, 1]);
});
