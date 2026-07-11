"use client";

import type { FormEvent } from "react";
import { shouldSubmitChatKey } from "@/lib/chatComposerKeys.mjs";

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
      <div className="chat-composer-pill">
        <label htmlFor="prompt-input" className="sr-only">Message</label>
        <textarea
          id="prompt-input"
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
          onKeyDown={(event) => {
            if (!shouldSubmitChatKey(event.nativeEvent)) return;
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }}
          placeholder="Ask about a song, request tabs, or describe a track to compose..."
          className="chat-input"
          rows={1}
        />
        <div className="composer-actions">
          <button type="submit" disabled={busy} className="send-button">
            {busy ? <span className="spinner" aria-hidden="true" /> : null}
            {busy ? "WORKING…" : <>SEND <span aria-hidden="true">▸</span></>}
          </button>
        </div>
      </div>
      <p className="chat-composer-caption">
        DIRECTOR-AGENT ORCHESTRATES · OUTPUT IS A SHORT MIDI SKETCH
      </p>
    </form>
  );
}
