import assert from "node:assert/strict";
import test from "node:test";

import { analyzeEndpoint } from "./apiBase.mjs";

test("targets the backend directly when a public base is configured", () => {
  assert.equal(
    analyzeEndpoint("https://api.example.com"),
    "https://api.example.com/references/analyze/stream",
  );
});

test("falls back to the proxy route when no base is configured", () => {
  assert.equal(analyzeEndpoint(""), "/api/references/analyze");
  assert.equal(analyzeEndpoint(undefined), "/api/references/analyze");
});

test("tolerates a trailing slash on the configured base", () => {
  assert.equal(
    analyzeEndpoint("https://api.example.com/"),
    "https://api.example.com/references/analyze/stream",
  );
  assert.equal(
    analyzeEndpoint("https://api.example.com///"),
    "https://api.example.com/references/analyze/stream",
  );
});

test("treats a whitespace-only base as unset", () => {
  assert.equal(analyzeEndpoint("   "), "/api/references/analyze");
});

test("trims surrounding whitespace", () => {
  assert.equal(
    analyzeEndpoint("  https://api.example.com  "),
    "https://api.example.com/references/analyze/stream",
  );
});

test("ignores a non-string base", () => {
  assert.equal(analyzeEndpoint(null), "/api/references/analyze");
  assert.equal(analyzeEndpoint(42), "/api/references/analyze");
});
