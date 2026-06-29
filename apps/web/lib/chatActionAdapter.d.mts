import type { ChatMessage, FeedEvent } from "./chatTypes";
import type { ComposeResponse, Header, ReferenceProfile } from "./types";

export type ChatAction =
  | { type: "research"; messageText: string }
  | { type: "answer_reference"; messageText: string }
  | { type: "compose"; messageText: string };

export function chooseChatAction(input: {
  prompt: string;
  hasReferenceProfile: boolean;
}): ChatAction;

export function normalizeMessageText(prompt: string): string;

export function createTextMessage(role: ChatMessage["role"], text: string, index: number): ChatMessage;

export function createAnalysisMessage(
  role: ChatMessage["role"],
  text: string,
  profile: ReferenceProfile,
  index: number,
): ChatMessage;

export function createCompositionMessage(
  role: ChatMessage["role"],
  text: string,
  result: ComposeResponse,
  feed: FeedEvent[],
  header: Header | null,
  source: ComposeResponse["source"] | null,
  index: number,
): ChatMessage;
