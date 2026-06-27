import type { ChatMessage } from "@/lib/chatTypes";
import AnalysisResultBlock from "@/components/AnalysisResultBlock";
import GeneratedSongBlock from "@/components/GeneratedSongBlock";
import Typewriter from "@/components/Typewriter";

interface ChatThreadProps {
  messages: ChatMessage[];
  busyLabel: string | null;
  busyElapsedMs?: number;
  onCancel?: () => void;
}

export default function ChatThread({ messages, busyLabel, busyElapsedMs, onCancel }: ChatThreadProps) {
  return (
    <div className="chat-thread" aria-live="polite">
      {messages.map((message) => (
        <article key={message.id} className={`chat-message chat-message-${message.role}`}>
          <span className="chat-role">{message.role}</span>
          <p>
            {message.role === "assistant"
              ? <Typewriter text={message.text} />
              : message.text}
          </p>
          {message.meta ? <span className="chat-meta">{message.meta}</span> : null}
          {message.kind === "analysis" ? <AnalysisResultBlock profile={message.profile} /> : null}
          {message.kind === "composition" ? <GeneratedSongBlock message={message} /> : null}
        </article>
      ))}
      {busyLabel ? (
        <article className="chat-message chat-message-system">
          <span className="chat-role">working</span>
          <p>
            {busyLabel}
            {typeof busyElapsedMs === "number" ? (
              <span className="chat-meta-inline"> · {(busyElapsedMs / 1000).toFixed(1)}s</span>
            ) : null}
            {onCancel ? (
              <button type="button" className="cancel-button" onClick={onCancel}>
                Stop
              </button>
            ) : null}
          </p>
        </article>
      ) : null}
    </div>
  );
}
