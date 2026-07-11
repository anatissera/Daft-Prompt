// Minimal client-side routing: always send user text to the backend chat
// router. Song knowledge is gathered through public evidence connectors.

export function chooseChatAction({ prompt }) {
  const messageText = normalizeMessageText(prompt);
  return { type: "chat", messageText };
}

export function normalizeMessageText(prompt) {
  const trimmed = prompt.trim();
  if (trimmed) return trimmed;
  return "Hello.";
}

export function createTextMessage(role, text, index) {
  return {
    id: `${role}-${index}`,
    kind: "text",
    role,
    text,
  };
}

export function createAnalysisMessage(role, text, profile, index) {
  return {
    id: `${role}-${index}`,
    kind: "analysis",
    role,
    text,
    profile,
  };
}

export function createTabMessage(role, text, excerpt, index) {
  return {
    id: `${role}-${index}`,
    kind: "tab",
    role,
    text,
    excerpt,
  };
}

export function createMelodyMessage(role, text, melody, index) {
  return {
    id: `${role}-${index}`,
    kind: "melody",
    role,
    text,
    melody,
  };
}
export function createChordMessage(role, text, rows, index) { return { id: `${role}-${index}`, kind: "chords", role, text, rows }; }

export function createCompositionMessage(role, text, result, feed, header, source, index) {
  return {
    id: `${role}-${index}`,
    kind: "composition",
    role,
    text,
    result,
    feed,
    header,
    source,
  };
}

export function referenceMemoryFromChatResponse(response, fallbackLabel = "Current reference") {
  if (!response || !response.reference_id) return null;
  const label = response.reference_label || fallbackLabel || response.reference_id;
  return { referenceId: response.reference_id, label };
}

const MAX_CONTEXT_TURNS = 6;
const MAX_CONTEXT_CHARS = 1200;
const MAX_TURN_CHARS = 240;

export function buildConversationContext(messages) {
  if (!Array.isArray(messages)) return "";
  const lines = messages
    .filter((message) => message && (message.role === "user" || message.role === "assistant"))
    .slice(-MAX_CONTEXT_TURNS)
    .map((message) => {
      const text = typeof message.text === "string"
        ? message.text.replace(/\s+/g, " ").trim().slice(0, MAX_TURN_CHARS)
        : "";
      if (!text) return "";
      return `${message.role === "user" ? "User" : "Assistant"}: ${text}`;
    })
    .filter(Boolean);
  return lines.join("\n").slice(-MAX_CONTEXT_CHARS);
}

export function buildChatRequestPayload({
  message,
  activeReferenceId = null,
  currentSong = null,
  conversationContext = "",
  artistStyleProfiles = [],
}) {
  const payload = { message, reference_id: activeReferenceId ?? null };
  if (currentSong) payload.current_song = currentSong;
  if (conversationContext) payload.conversation_context = conversationContext;
  if (artistStyleProfiles.length) payload.artist_style_profiles = artistStyleProfiles;
  return payload;
}
