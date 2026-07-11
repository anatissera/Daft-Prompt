"use client";

import type { FormEvent, RefObject } from "react";

interface ChatComposerProps {
  busy: boolean;
  prompt: string;
  selectedFileName: string | null;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onPromptChange: (prompt: string) => void;
  onFileChange: (file: File | null) => void;
  onSubmit: (event: FormEvent) => void;
  queuedPrompts?: string[];
  onCancelQueued?: (index: number) => void;
}

export default function ChatComposer({
  busy,
  prompt,
  selectedFileName,
  fileInputRef,
  onPromptChange,
  onFileChange,
  onSubmit,
  queuedPrompts = [],
  onCancelQueued,
}: ChatComposerProps) {
  const canSubmit = prompt.trim().length > 0 || selectedFileName !== null;
  return (
    <form onSubmit={onSubmit} className="chat-composer">
      {queuedPrompts.length > 0 ? (
        <div className="chat-composer-queue" aria-label="Queued prompts">
          <span className="chat-composer-queue-label">QUEUED · {queuedPrompts.length}</span>
          {queuedPrompts.map((q, i) => (
            <span key={i} className="chat-composer-queue-item" title={q}>
              {q.length > 60 ? `${q.slice(0, 60)}…` : q}
              {onCancelQueued ? (
                <button
                  type="button"
                  className="chat-composer-queue-cancel"
                  onClick={() => onCancelQueued(i)}
                  aria-label="Remove from queue"
                >×</button>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}
      <div className="chat-composer-pill">
        <label htmlFor="prompt-input" className="sr-only">Message</label>
        <textarea
          id="prompt-input"
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
          onKeyDown={(event) => {
            // Enter submits (or queues when the studio is busy). Shift+Enter
            // still inserts a newline. IME composition is ignored so people
            // typing accented chars / kana don't send half-composed text.
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={busy
            ? "Studio is busy — Enter to queue this prompt for after…"
            : "Describe the track you want the studio to compose… (Enter to send, Shift+Enter for newline)"}
          className="chat-input"
          rows={1}
        />
        <div className="composer-actions">
          <input
            ref={fileInputRef}
            id="audio-file"
            type="file"
            accept="audio/*,.mp3,.wav,.flac,.m4a,.ogg,.aiff,.aif"
            className="sr-only"
            onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
          />
          <label htmlFor="audio-file" className="attach-button">
            <span className="attach-icon" aria-hidden="true">♪</span> Attach audio
          </label>
          {selectedFileName ? <span className="selected-file">{selectedFileName}</span> : null}
          <button type="submit" disabled={!canSubmit} className="send-button">
            {busy ? <span className="spinner" aria-hidden="true" /> : null}
            {busy ? <>QUEUE <span aria-hidden="true">▸</span></> : <>SEND <span aria-hidden="true">▸</span></>}
          </button>
        </div>
      </div>
      <p className="chat-composer-caption">
        DIRECTOR-AGENT ORCHESTRATES · OUTPUT IS A SHORT MIDI SKETCH
      </p>
    </form>
  );
}
