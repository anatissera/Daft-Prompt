import type { ComposeEvent, ComposeResponse, Header, ReferenceProfile, TabExcerpt } from "@/lib/types";

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

export interface AnalysisChatMessage extends BaseChatMessage {
  kind: "analysis";
  profile: ReferenceProfile;
}

export interface TabChatMessage extends BaseChatMessage {
  kind: "tab";
  excerpt: TabExcerpt;
}

export interface CompositionChatMessage extends BaseChatMessage {
  kind: "composition";
  result: ComposeResponse;
  feed: FeedEvent[];
  header: Header | null;
  source: ComposeResponse["source"] | null;
}

export type ChatMessage = TextChatMessage | AnalysisChatMessage | TabChatMessage | CompositionChatMessage;
