import type { ComposeEvent, ComposeResponse, Header, ReferenceProfile } from "@/lib/types";

export type FeedEvent = Extract<ComposeEvent, { type: "agent_pass" | "convergence" | "error" }>;

export type ChatRole = "user" | "assistant" | "system";

interface BaseChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  meta?: string;
}

export interface TextChatMessage extends BaseChatMessage {
  kind: "text";
}

export interface PlayableChord {
  chord: string;
  notes: string[];
  midi_notes: number[];
}

export interface PlayableChordSection {
  name: string;
  chords: PlayableChord[];
  confidence: number;
}

export interface PlayableChords {
  instrument: "piano" | "guitar";
  source_label: string;
  confidence: number;
  sections: PlayableChordSection[];
}

export interface ChordDiagramChatMessage extends BaseChatMessage {
  kind: "chord_diagram";
  playableChords: PlayableChords;
}

export interface AnalysisChatMessage extends BaseChatMessage {
  kind: "analysis";
  profile: ReferenceProfile;
}

export interface CompositionChatMessage extends BaseChatMessage {
  kind: "composition";
  result: ComposeResponse;
  feed: FeedEvent[];
  header: Header | null;
  source: ComposeResponse["source"] | null;
}

export type ChatMessage = TextChatMessage | ChordDiagramChatMessage | AnalysisChatMessage | CompositionChatMessage;
