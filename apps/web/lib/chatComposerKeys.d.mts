export interface ChatKeyEvent {
  key: string;
  shiftKey: boolean;
  isComposing: boolean;
}

export function shouldSubmitChatKey(event: ChatKeyEvent): boolean;
