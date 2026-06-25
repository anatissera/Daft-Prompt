import type { ChatMessage } from "@/lib/chatTypes";
import AnalysisResultBlock from "@/components/AnalysisResultBlock";
import GeneratedSongBlock from "@/components/GeneratedSongBlock";

interface ChatThreadProps {
  messages: ChatMessage[];
  busyLabel: string | null;
}

export default function ChatThread({ messages, busyLabel }: ChatThreadProps) {
  return (
    <div className="chat-thread" aria-live="polite">
      {messages.map((message) => (
        <article key={message.id} className={`chat-message chat-message-${message.role}`}>
          <span className="chat-role">{message.role}</span>
          <p>{message.text}</p>
          {message.kind === "analysis" ? <AnalysisResultBlock profile={message.profile} /> : null}
          {message.kind === "composition" ? <GeneratedSongBlock message={message} /> : null}
        </article>
      ))}
      {busyLabel ? (
        <article className="chat-message chat-message-system">
          <span className="chat-role">working</span>
          <p>{busyLabel}</p>
        </article>
      ) : null}
    </div>
  );
}
