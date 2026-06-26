import { isReferenceQuestion } from "./referenceProfileView.mjs";

export function chooseChatAction({ prompt, hasSelectedFile, hasReferenceProfile }) {
  const messageText = normalizeMessageText(prompt, hasSelectedFile);
  if (hasSelectedFile) return { type: "analyze", messageText };
  if (hasReferenceProfile && isReferenceQuestion(messageText)) {
    return { type: "answer_reference", messageText };
  }
  return { type: "compose", messageText };
}

export function normalizeMessageText(prompt, hasSelectedFile = false) {
  const trimmed = prompt.trim();
  if (trimmed) return trimmed;
  return hasSelectedFile ? "Analyze this audio." : "Compose a short song.";
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
