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

// Rough timeline of the compose pipeline — the backend doesn't stream
// per-step progress, so we mark stages by elapsed time as a heuristic.
const PIPELINE_STAGES: Array<{ label: string; atSec: number }> = [
  { label: "Classifying your intent",                 atSec: 0 },
  { label: "Director arranging the band",             atSec: 4 },
  { label: "Instrument agents composing parts",       atSec: 40 },
  { label: "Arbiter finalizing the arrangement",      atSec: 180 },
  { label: "Rendering MIDI + score",                  atSec: 230 },
];

function activeStageIndex(elapsedSec: number): number {
  for (let i = PIPELINE_STAGES.length - 1; i >= 0; i--) {
    if (elapsedSec >= PIPELINE_STAGES[i].atSec) return i;
  }
  return 0;
}

export default function ChatThread({ messages, busyLabel, busyElapsedMs, onCancel }: ChatThreadProps) {
  const elapsedSec = (busyElapsedMs ?? 0) / 1000;
  const activeIdx = activeStageIndex(elapsedSec);
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
          <div className="busy-block">
            <p className="busy-header">
              <span className="sound-wave" aria-hidden="true">
                <span /><span /><span /><span /><span />
                <span /><span /><span /><span /><span />
                <span /><span /><span /><span /><span />
              </span>
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
            <ol className="pipeline-steps">
              {PIPELINE_STAGES.map((stage, idx) => {
                const state =
                  idx < activeIdx ? "done" : idx === activeIdx ? "active" : "pending";
                return (
                  <li key={stage.label} className={`pipeline-step pipeline-step-${state}`}>
                    <span className="pipeline-step-marker" aria-hidden="true">
                      {state === "done" ? "✓" : state === "active" ? "›" : "·"}
                    </span>
                    <span className="pipeline-step-label">{stage.label}</span>
                  </li>
                );
              })}
            </ol>
          </div>
        </article>
      ) : null}
    </div>
  );
}
