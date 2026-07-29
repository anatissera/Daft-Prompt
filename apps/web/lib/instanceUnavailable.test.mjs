import assert from "node:assert/strict";
import test from "node:test";

import { isRetryableInstanceUnavailable } from "./instanceUnavailable.mjs";

test("retries the cold-start 500 (Cloud Run plain text, not our JSON)", () => {
  assert.equal(
    isRetryableInstanceUnavailable(
      500,
      "The request was aborted because there was no available instance.",
      "text/plain",
    ),
    true,
  );
});

test("retries the max-instances 429 (Cloud Run plain text)", () => {
  assert.equal(isRetryableInstanceUnavailable(429, "Rate exceeded.", "text/plain"), true);
});

test("does not retry a real application error even at the same status", () => {
  assert.equal(
    isRetryableInstanceUnavailable(500, JSON.stringify({ detail: "compose failed: bad roster" }), "application/json"),
    false,
  );
  assert.equal(
    isRetryableInstanceUnavailable(429, JSON.stringify({ detail: "quota exceeded" }), "application/json"),
    false,
  );
});

test("does not retry client errors outside the infra-rejection family", () => {
  assert.equal(isRetryableInstanceUnavailable(401, "invalid or missing API key", "text/plain"), false);
  assert.equal(isRetryableInstanceUnavailable(404, "not found", "text/plain"), false);
});

test("treats JSON content-type with an unparsable body as still-retryable", () => {
  // Defensive: a mislabeled infra error shouldn't get mistaken for our app's shape.
  assert.equal(isRetryableInstanceUnavailable(503, "<html>Service Unavailable</html>", "application/json"), true);
});
