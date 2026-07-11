import assert from "node:assert/strict";
import test from "node:test";

import {
  buildChatRequestPayload,
  buildConversationContext,
  chooseChatAction,
  createAnalysisMessage,
  createCompositionMessage,
  createMelodyMessage,
  createTextMessage,
  createTabMessage,
  referenceMemoryFromChatResponse,
} from "./chatActionAdapter.mjs";

test("chooseChatAction analyzes when a local file is attached", () => {
  assert.deepEqual(
    chooseChatAction({ prompt: "what key is this in?", hasSelectedFile: true }),
    { type: "analyze", messageText: "what key is this in?" },
  );
});

test("chooseChatAction defaults to chat for plain prompts", () => {
  assert.deepEqual(
    chooseChatAction({ prompt: "compose a slow blues", hasSelectedFile: false }),
    { type: "chat", messageText: "compose a slow blues" },
  );
});

test("normalizeMessageText fills in a default for empty prompts", () => {
  assert.equal(normalizeText(""), "Hello.");
  assert.equal(normalizeText("", true), "Analyze this audio.");
});

function normalizeText(prompt, hasFile = false) {
  return chooseChatAction({ prompt, hasSelectedFile: hasFile }).messageText;
}

test("message helpers create stable enriched chat messages", () => {
  const text = createTextMessage("assistant", "Hello", 0);
  assert.equal(text.id, "assistant-0");
  assert.equal(text.kind, "text");
  assert.equal(text.text, "Hello");

  const analysis = createAnalysisMessage("assistant", "Done", { reference_id: "ref_1" }, 1);
  assert.equal(analysis.kind, "analysis");
  assert.equal(analysis.profile.reference_id, "ref_1");

  const composition = createCompositionMessage("assistant", "Generated", { job_id: "job_1" }, [], null, "director", 2);
  assert.equal(composition.kind, "composition");
  assert.equal(composition.result.job_id, "job_1");
});

test("createTabMessage keeps a native tab excerpt attached to the chat turn", () => {
  const excerpt = { instrument: "bass", measures: [] };

  assert.deepEqual(createTabMessage("assistant", "Here is the bass tab.", excerpt, 3), {
    id: "assistant-3",
    kind: "tab",
    role: "assistant",
    text: "Here is the bass tab.",
    excerpt,
  });
});

test("createMelodyMessage keeps a native melody preview attached to the chat turn", () => {
  const melody = { note_count: 2, representative_events: [] };

  assert.deepEqual(createMelodyMessage("assistant", "Here is the riff.", melody, 4), {
    id: "assistant-4",
    kind: "melody",
    role: "assistant",
    text: "Here is the riff.",
    melody,
  });
});

test("referenceMemoryFromChatResponse remembers researched references", () => {
  assert.deepEqual(
    referenceMemoryFromChatResponse(
      { reference_id: "ref_song", reply: "Research found source-backed claims." },
      "Look up Paranoid by Black Sabbath",
    ),
    { referenceId: "ref_song", label: "Look up Paranoid by Black Sabbath" },
  );
  assert.equal(referenceMemoryFromChatResponse({ reply: "No reference" }, "Hello"), null);
});

test("buildChatRequestPayload includes active reference, style profile, and current song when available", () => {
  const currentSong = { request: "compose rock", parts: {} };
  const artistStyleProfile = { profile_id: "artist_fixture", artist_name: "Fixture Band" };
  assert.deepEqual(
    buildChatRequestPayload({
      message: "What instruments are loaded for this song?",
      activeReferenceId: "ref_song",
      currentSong,
      conversationContext: "User: Make it darker",
      artistStyleProfiles: [artistStyleProfile],
    }),
    {
      message: "What instruments are loaded for this song?",
      reference_id: "ref_song",
      current_song: currentSong,
      conversation_context: "User: Make it darker",
      artist_style_profiles: [artistStyleProfile],
    },
  );
});

test("buildConversationContext keeps a bounded, user and assistant-only session summary", () => {
  const context = buildConversationContext([
    { role: "system", text: "internal event" },
    { role: "user", text: "Compose a disco groove" },
    { role: "assistant", text: "I will start with drums and bass." },
    { role: "user", text: "Make it darker\nwith more space." },
  ]);

  assert.equal(
    context,
    "User: Compose a disco groove\nAssistant: I will start with drums and bass.\nUser: Make it darker with more space.",
  );
  assert.equal(context.includes("internal event"), false);
});
