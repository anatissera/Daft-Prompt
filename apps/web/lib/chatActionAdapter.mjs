// Minimal client-side routing: attachment → analyze, otherwise → chat (backend
// runs its own intent classification on /chat).

export function chooseChatAction({ prompt, hasSelectedFile }) {
  const messageText = normalizeMessageText(prompt, hasSelectedFile);
  if (hasSelectedFile) return { type: "analyze", messageText };
  return { type: "chat", messageText };
}

export function normalizeMessageText(prompt, hasSelectedFile = false) {
  const trimmed = prompt.trim();
  if (trimmed) return trimmed;
  return hasSelectedFile ? "Analyze this audio." : "Hello.";
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
}) {
  const payload = { message, reference_id: activeReferenceId ?? null };
  if (currentSong) payload.current_song = currentSong;
  if (conversationContext) payload.conversation_context = conversationContext;
  return payload;
}
