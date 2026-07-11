import type { ChatMessage, FeedEvent, PlayableChords } from "./chatTypes";
import type { ComposeResponse, Header, ReferenceProfile } from "./types";

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

export function createChordDiagramMessage(
  role: ChatMessage["role"],
  text: string,
  playableChords: PlayableChords,
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
