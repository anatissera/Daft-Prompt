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

export function createChordDiagramMessage(role, text, playableChords, index) {
  return {
    id: `${role}-${index}`,
    kind: "chord_diagram",
    role,
    text,
    playableChords,
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
