// Derive a short session title from the user's first message — client-side, no
// LLM. Takes the first few words, Title Cases them, and caps the length. Returns
// "" when there's nothing usable so callers keep their default title.

const MAX_WORDS = 5;
const MAX_CHARS = 60;
const SMALL_WORDS = new Set(["a", "an", "and", "the", "of", "in", "on", "to", "for"]);

function titleCaseWord(word, isFirst) {
  if (!isFirst && SMALL_WORDS.has(word)) return word;
  return word.charAt(0).toUpperCase() + word.slice(1);
}

export function deriveSessionTitle(message) {
  if (typeof message !== "string") return "";
  const words = message
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, MAX_WORDS);
  if (words.length === 0) return "";
  return words
    .map((word, i) => titleCaseWord(word, i === 0))
    .join(" ")
    .slice(0, MAX_CHARS);
}
