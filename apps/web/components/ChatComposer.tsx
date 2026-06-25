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
}

export default function ChatComposer({
  busy,
  prompt,
  selectedFileName,
  fileInputRef,
  onPromptChange,
  onFileChange,
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
        placeholder="Ask about a song, attach audio, or compose a slow blues..."
        className="chat-input"
        rows={2}
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
          Attach audio
        </label>
        {selectedFileName ? <span className="selected-file">{selectedFileName}</span> : null}
        <button type="submit" disabled={busy} className="send-button">
          {busy ? <span className="spinner" aria-hidden="true" /> : null}
          {busy ? "Working..." : "Send"}
        </button>
      </div>
    </form>
  );
}
