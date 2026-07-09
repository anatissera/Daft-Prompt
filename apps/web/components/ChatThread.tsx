import type { ChatMessage } from "@/lib/chatTypes";
import AnalysisResultBlock from "@/components/AnalysisResultBlock";
import TabExcerptBlock from "@/components/TabExcerptBlock";
import GeneratedSongBlock from "@/components/GeneratedSongBlock";
import Typewriter from "@/components/Typewriter";
import AnalysisProgressChecklist from "@/components/AnalysisProgressChecklist";
import type { AnalysisStageState } from "@/lib/analysisProgress.mjs";

interface ChatThreadProps {
  messages: ChatMessage[];
  busyLabel: string | null;
  busyElapsedMs?: number;
  onCancel?: () => void;
  analysisProgress?: AnalysisStageState[] | null;
}

// Rough timeline of the compose pipeline. We can't show this list until the
// classifier on the server has decided the prompt is in scope (music) — until
// then the request might bounce back as off-topic in < 1s and we'd flash a
// fake list of stages. Wait until the classifier window has clearly passed
// AND the busy label is the "Thinking…" one (analyze uses its own label).
const PIPELINE_REVEAL_AFTER_SEC = 9;     // longer than the 8s classifier timeout
const PIPELINE_STAGES: Array<{ label: string; atSec: number }> = [
  { label: "Director arranging the band",             atSec: PIPELINE_REVEAL_AFTER_SEC },
  { label: "Instrument agents composing parts",       atSec: PIPELINE_REVEAL_AFTER_SEC + 30 },
  { label: "Arbiter finalizing the arrangement",      atSec: PIPELINE_REVEAL_AFTER_SEC + 170 },
  { label: "Rendering MIDI + score",                  atSec: PIPELINE_REVEAL_AFTER_SEC + 220 },
];

function activeStageIndex(elapsedSec: number): number {
  for (let i = PIPELINE_STAGES.length - 1; i >= 0; i--) {
    if (elapsedSec >= PIPELINE_STAGES[i].atSec) return i;
  }
  return 0;
}

export default function ChatThread({ messages, busyLabel, busyElapsedMs, onCancel, analysisProgress }: ChatThreadProps) {
  const elapsedSec = (busyElapsedMs ?? 0) / 1000;
  const activeIdx = activeStageIndex(elapsedSec);
  const showPipeline =
    busyLabel === "Thinking…" && elapsedSec >= PIPELINE_REVEAL_AFTER_SEC;
  return (
    <div className="chat-thread" aria-live="polite">
      {messages.map((message) => (
        <article key={message.id} className={`chat-message chat-message-${message.role}`}>
          <span className="chat-role">{message.role}</span>
          <p>
            <span className="bubble-sparkle" aria-hidden="true">✦</span>
            {message.role === "assistant"
              ? <Typewriter text={message.text} />
              : message.text}
          </p>
          {message.meta ? <span className="chat-meta">{message.meta}</span> : null}
          {message.kind === "analysis" ? <AnalysisResultBlock profile={message.profile} /> : null}
          {message.kind === "tab" ? <TabExcerptBlock excerpt={message.excerpt} /> : null}
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
            {analysisProgress ? (
              <AnalysisProgressChecklist stages={analysisProgress} />
            ) : null}
            {showPipeline && !analysisProgress ? (
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
            ) : null}
          </div>
        </article>
      ) : null}
    </div>
  );
}
