export function shouldSubmitChatKey(event) {
  return event.key === "Enter" && !event.shiftKey && !event.isComposing;
}
