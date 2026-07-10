const RESEARCH_RE = /\b(research|look\s*up|search|analy[sz]e|buscar|busc[aá]|investigar)\b/i;
const COMPOSE_RE = /\b(compose|generate|write|create|make\s+(?:a|an|me)|sketch|compon|gener|crear)\b/i;
const EDIT_RE = /\b(change|edit|revise|regenerate|make\s+it|less|more|faster|slower|sound|tone|cambi|edit|revis|regener|menos|m[aá]s|sonido|tono)\b/i;

export const WORKFLOW_STAGES = {
  research: [
    "Searching sources",
    "Reading evidence",
    "Extracting musical facts",
    "Building reference profile",
    "Preparing answer",
  ],
  composition: [
    "Planning arrangement",
    "Composing instrument parts",
    "Reviewing arrangement",
    "Rendering MIDI and notation",
  ],
  editing: [
    "Loading current composition",
    "Applying requested changes",
    "Validating preserved parts",
    "Re-rendering affected outputs",
  ],
  answering: [
    "Reviewing conversation context",
    "Reading available evidence",
    "Preparing answer",
  ],
};

export function classifyChatWorkflow(message, { hasCurrentSong = false } = {}) {
  if (RESEARCH_RE.test(message)) return "research";
  if (hasCurrentSong && EDIT_RE.test(message)) return "editing";
  if (COMPOSE_RE.test(message)) return "composition";
  return "answering";
}

export function workflowBusyLabel(workflow) {
  return {
    research: "Researching reference…",
    composition: "Composing sketch…",
    editing: "Updating composition…",
    answering: "Preparing answer…",
  }[workflow] ?? "Working…";
}

export function activeWorkflowStage(elapsedSeconds, stageCount) {
  if (stageCount <= 1) return 0;
  return Math.min(stageCount - 1, Math.floor(Math.max(0, elapsedSeconds) / 6));
}
