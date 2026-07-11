import assert from "node:assert/strict";
import test from "node:test";

import { renderTabAscii } from "./tabAsciiRenderer.mjs";

test("renders guitar events as six-line high-to-low ASCII tab", () => {
  const output = renderTabAscii({
    instrument: "guitar",
    tuning: ["E4", "B3", "G3", "D3", "A2", "E2"],
    measures: [{
      index: 0,
      marker: "Intro",
      events: [
        { beat_index: 0, duration: "1/4", string: 1, fret: 2 },
        { beat_index: 1, duration: "1/4", string: 2, fret: 10 },
        { beat_index: 2, duration: "1/4", string: 6, fret: 0, rest: false },
        { beat_index: 3, duration: "1/4", string: 3, fret: 5, rest: true },
      ],
    }],
  });

  const lines = output.split("\n");
  assert.equal(lines[0], "m. 1 · Intro");
  assert.equal(lines.slice(1).filter((line) => /^[EBGDA]\|/.test(line)).length, 6);
  assert.match(output, /E\|.*2/);
  assert.match(output, /B\|.*10/);
  assert.match(output, /E\|.*0/);
  assert.doesNotMatch(output, /S[0-9]|F[0-9]/);
});

test("renders bass on four strings and omits rests", () => {
  const output = renderTabAscii({
    instrument: "bass",
    tuning: ["G2", "D2", "A1", "E1"],
    measures: [{
      index: 2,
      events: [
        { beat_index: 0, duration: "1/4", string: 3, fret: 5 },
        { beat_index: 1, duration: "1/4", string: 4, fret: 12, rest: true },
      ],
    }],
  });

  assert.equal(output.split("\n").filter((line) => /^[GDAE]\|/.test(line)).length, 4);
  assert.match(output, /A\|.*5/);
  assert.doesNotMatch(output, /12/);
});
