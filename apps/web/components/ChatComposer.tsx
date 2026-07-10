"use client";

import type { FormEvent, RefObject } from "react";

interface ChatComposerProps {
  busy: boolean;
  audioAttachmentEnabled: boolean;
  prompt: string;
  selectedFileName: string | null;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onPromptChange: (prompt: string) => void;
  onFileChange: (file: File | null) => void;
  onSubmit: (event: FormEvent) => void;
}

export default function ChatComposer({
  busy,
  audioAttachmentEnabled,
  prompt,
  selectedFileName,
  fileInputRef,
  onPromptChange,
  onFileChange,
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
          placeholder="Describe the track you want the studio to compose…"
          className="chat-input"
          rows={1}
        />
        <div className="composer-actions">
          {audioAttachmentEnabled ? (
            <>
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
            </>
          ) : null}
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
