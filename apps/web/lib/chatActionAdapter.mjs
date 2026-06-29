import { isReferenceQuestion } from "./referenceProfileView.mjs";

export function chooseChatAction({ prompt, hasSelectedFile, hasReferenceProfile }) {
  const messageText = normalizeMessageText(prompt);
  if (hasReferenceProfile && isReferenceQuestion(messageText)) {
    return { type: "answer_reference", messageText };
  }
  if (isReferenceQuestion(messageText)) {
    return { type: "research", messageText };
  }
  return { type: "compose", messageText };
}

export function normalizeMessageText(prompt) {
  const trimmed = prompt.trim();
  if (trimmed) return trimmed;
  return "Compose a short song.";
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
