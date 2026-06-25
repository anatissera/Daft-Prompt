import type { ComposeEvent, ComposeResponse, Header, ReferenceProfile } from "@/lib/types";

export type FeedEvent = Extract<ComposeEvent, { type: "agent_pass" | "convergence" | "error" }>;

export type ChatRole = "user" | "assistant" | "system";

interface BaseChatMessage {
  id: string;
  role: ChatRole;
  text: string;
}

export interface TextChatMessage extends BaseChatMessage {
  kind: "text";
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

export type ChatMessage = TextChatMessage | AnalysisChatMessage | CompositionChatMessage;
