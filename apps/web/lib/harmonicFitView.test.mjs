import assert from "node:assert/strict";
import test from "node:test";

import { harmonicFitView, harmonicFitLabel } from "./harmonicFitView.mjs";

test("returns null when fit is missing or malformed", () => {
  assert.equal(harmonicFitView(undefined), null);
  assert.equal(harmonicFitView({}), null);
  assert.equal(harmonicFitView({ bass: 0.5 }), null); // no _overall
});

test("computes overall percentage and worst-first per-instrument rows", () => {
  const view = harmonicFitView({ bass: 0.72, guitar: 0.94, keys: 0.5, _overall: 0.759 });
  assert.equal(view.overallPct, 76);
  assert.deepEqual(view.rows, [
    { id: "keys", pct: 50 },
    { id: "bass", pct: 72 },
    { id: "guitar", pct: 94 },
  ]);
});

test("drops the synthetic _overall key from the breakdown rows", () => {
  const view = harmonicFitView({ bass: 1, _overall: 1 });
  assert.deepEqual(view.rows, [{ id: "bass", pct: 100 }]);
});

test("labels fit bands", () => {
  assert.equal(harmonicFitLabel(90), "strong");
  assert.equal(harmonicFitLabel(75), "fair");
  assert.equal(harmonicFitLabel(60), "weak");
});
