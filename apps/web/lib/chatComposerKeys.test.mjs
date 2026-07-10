import test from "node:test";
import assert from "node:assert/strict";
import { shouldSubmitChatKey } from "./chatComposerKeys.mjs";

test("Enter submits a chat message", () => {
  assert.equal(shouldSubmitChatKey({ key: "Enter", shiftKey: false, isComposing: false }), true);
});

test("Shift+Enter preserves multiline input", () => {
  assert.equal(shouldSubmitChatKey({ key: "Enter", shiftKey: true, isComposing: false }), false);
});

test("IME composition and other keys do not submit", () => {
  assert.equal(shouldSubmitChatKey({ key: "Enter", shiftKey: false, isComposing: true }), false);
  assert.equal(shouldSubmitChatKey({ key: "a", shiftKey: false, isComposing: false }), false);
});
