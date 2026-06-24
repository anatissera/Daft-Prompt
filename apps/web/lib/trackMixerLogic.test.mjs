import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildTrackEvents,
  getAudibleTrackIds,
  getSongDurationSeconds,
  midiToFrequency,
} from "./trackMixerLogic.mjs";

test("getAudibleTrackIds returns every non-muted track when no solo is active", () => {
  const result = getAudibleTrackIds(["lead", "bass", "drums"], new Set(["bass"]), new Set());

  assert.deepEqual(result, new Set(["lead", "drums"]));
});

test("getAudibleTrackIds returns solo tracks except muted solo tracks", () => {
  const result = getAudibleTrackIds(["lead", "bass", "drums"], new Set(["lead"]), new Set(["lead", "bass"]));

  assert.deepEqual(result, new Set(["bass"]));
});

test("buildTrackEvents converts SongState beats to seconds per track", () => {
  const events = buildTrackEvents({
    header: { tempo_bpm: 120, time_signature: [4, 4] },
    parts: {
      lead: {
        notes: [
          { bar: 1, start_beat: 2, dur: 1.5, pitch: 69, velocity: 64 },
          { bar: 0, start_beat: 0, dur: 1, pitch: null, velocity: 64 },
        ],
      },
    },
  });

  assert.equal(events.lead.length, 1);
  assert.deepEqual(events.lead[0], {
    durationSeconds: 0.75,
    frequency: 440,
    pitch: 69,
    startSeconds: 3,
    velocity: 64 / 127,
  });
});

test("getSongDurationSeconds includes the latest note end", () => {
  const duration = getSongDurationSeconds({
    header: { tempo_bpm: 60, time_signature: [3, 4] },
    parts: {
      a: { notes: [{ bar: 1, start_beat: 1, dur: 2, pitch: 60, velocity: 100 }] },
      b: { notes: [{ bar: 0, start_beat: 0, dur: 1, pitch: 62, velocity: 100 }] },
    },
  });

  assert.equal(duration, 6);
});

test("midiToFrequency maps A4 to 440 Hz", () => {
  assert.equal(midiToFrequency(69), 440);
});
