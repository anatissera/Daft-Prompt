import type { ChatMessage, FeedEvent } from "./chatTypes";
import type { ComposeResponse, Header, MelodyProfile, ReferenceProfile, SongState, TabExcerpt } from "./types";

export type ChatAction =
  | { type: "analyze"; messageText: string }
  | { type: "chat"; messageText: string };

export function chooseChatAction(input: {
  prompt: string;
  hasSelectedFile: boolean;
  hasReferenceProfile?: boolean;
}): ChatAction;

export function normalizeMessageText(prompt: string, hasSelectedFile?: boolean): string;

export function createTextMessage(role: ChatMessage["role"], text: string, index: number): ChatMessage;

export function createAnalysisMessage(
  role: ChatMessage["role"],
  text: string,
  profile: ReferenceProfile,
  index: number,
): ChatMessage;

export function createTabMessage(
  role: ChatMessage["role"],
  text: string,
  excerpt: TabExcerpt,
  index: number,
): ChatMessage;

export function createMelodyMessage(
  role: ChatMessage["role"],
  text: string,
  melody: MelodyProfile,
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

export function referenceMemoryFromChatResponse(
  response: { reference_id?: string | null; reference_label?: string | null },
  fallbackLabel?: string,
): { referenceId: string; label: string } | null;

export function buildConversationContext(messages: Array<Pick<ChatMessage, "role" | "text">>): string;

export function buildChatRequestPayload(input: {
  message: string;
  activeReferenceId?: string | null;
  currentSong?: SongState | null;
  conversationContext?: string;
}): {
  message: string;
  reference_id: string | null;
  current_song?: SongState;
  conversation_context?: string;
};
