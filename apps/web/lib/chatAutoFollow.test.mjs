import test from "node:test";
import assert from "node:assert/strict";
import { distanceFromBottom, isNearConversationBottom } from "./chatAutoFollow.mjs";

test("near-bottom policy follows small growth but respects manual upward scrolling", () => {
  assert.equal(isNearConversationBottom({ scrollHeight: 1000, scrollTop: 420, clientHeight: 500 }), true);
  assert.equal(isNearConversationBottom({ scrollHeight: 1000, scrollTop: 200, clientHeight: 500 }), false);
  assert.equal(distanceFromBottom({ scrollHeight: 1000, scrollTop: 200, clientHeight: 500 }), 300);
});
