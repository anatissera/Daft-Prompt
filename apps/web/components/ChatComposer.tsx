"use client";

import type { FormEvent } from "react";

interface ChatComposerProps {
  busy: boolean;
  prompt: string;
  onPromptChange: (prompt: string) => void;
  onSubmit: (event: FormEvent) => void;
}

export default function ChatComposer({
  busy,
  prompt,
  onPromptChange,
  onSubmit,
}: ChatComposerProps) {
  return (
    <form onSubmit={onSubmit} className="chat-composer">
      <label htmlFor="prompt-input" className="sr-only">
        Message
      </label>
      <textarea
        id="prompt-input"
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        placeholder="Ask about a song, or compose with traits from songs you name..."
        className="chat-input"
        rows={2}
      />
      <div className="composer-actions">
        <button type="submit" disabled={busy} className="send-button">
          {busy ? (
            <span className="spinner" aria-hidden="true">
              <span />
            </span>
          ) : null}
          {busy ? "Processing..." : "Send"}
        </button>
      </div>
    </form>
  );
}
