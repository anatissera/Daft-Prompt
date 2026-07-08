import type { ChatMessage } from "@/lib/chatTypes";
import AnalysisResultBlock from "@/components/AnalysisResultBlock";
import GeneratedSongBlock from "@/components/GeneratedSongBlock";
import Typewriter from "@/components/Typewriter";

export type PipelineStageIdx = 0 | 1 | 2 | 3;

/** Real-time pipeline signal driven by SSE events from /api/chat/stream.
 * When present, the stage list uses this instead of the time-based fallback,
 * and `substep` overrides the rotating hint (e.g. the actual instrument name
 * from an `agent_pass` event). */
export interface PipelineState {
  stageIdx: PipelineStageIdx;
  substep: string | null;
}

interface ChatThreadProps {
  messages: ChatMessage[];
  busyLabel: string | null;
  busyElapsedMs?: number;
  onCancel?: () => void;
  pipeline?: PipelineState | null;
}

// Rough timeline of the compose pipeline used as a fallback when we don't have
// real SSE events (e.g. the analyze flow). Kept short-ish so it doesn't lie for
// too long on slow local models — real events, when present, take precedence.
const PIPELINE_REVEAL_AFTER_SEC = 9;     // longer than the 8s classifier timeout
const SUBSTEP_SECONDS = 3.5;
const PIPELINE_STAGES: Array<{ label: string; details: string[]; atSec: number }> = [
  {
    label: "Director arranging the band",
    details: [
      "reading the style prompt…",
      "googling the artist on DuckDuckGo…",
      "parsing tempo / key from search hits…",
      "retrieving Lakh corpus examples…",
      "picking key, tempo, form…",
      "assigning instruments + playing styles…",
    ],
    atSec: PIPELINE_REVEAL_AFTER_SEC,
  },
  {
    label: "Instrument agents composing parts",
    details: [
      "sampling Groove drum patterns…",
      "drums composing…",
      "bass composing…",
      "harmony composing…",
      "lead / texture composing…",
      "peer summaries between waves…",
    ],
    atSec: PIPELINE_REVEAL_AFTER_SEC + 30,
  },
  {
    label: "Arbiter finalizing the arrangement",
    details: [
      "scoring harmonic fit per bar…",
      "checking bass on chord tones…",
      "repairing off-chord notes…",
      "collapsing split drum kits…",
    ],
    atSec: PIPELINE_REVEAL_AFTER_SEC + 170,
  },
  {
    label: "Rendering MIDI + score",
    details: [
      "writing MIDI tracks…",
      "rendering the score…",
      "packaging the download…",
    ],
    atSec: PIPELINE_REVEAL_AFTER_SEC + 220,
  },
];

function stageDetail(
  stageIdx: number,
  activeIdx: number,
  elapsedSec: number,
  substepOverride: string | null,
): string {
  const stage = PIPELINE_STAGES[stageIdx];
  if (stageIdx === activeIdx && substepOverride) return substepOverride;
  if (stageIdx < activeIdx) return stage.details[stage.details.length - 1];
  if (stageIdx > activeIdx) return stage.details[0];
  const sub = Math.max(0, elapsedSec - stage.atSec);
  const idx = Math.floor(sub / SUBSTEP_SECONDS) % stage.details.length;
  return stage.details[idx];
}

function fallbackActiveIndex(elapsedSec: number): number {
  for (let i = PIPELINE_STAGES.length - 1; i >= 0; i--) {
    if (elapsedSec >= PIPELINE_STAGES[i].atSec) return i;
  }
  return 0;
}

export default function ChatThread({ messages, busyLabel, busyElapsedMs, onCancel, pipeline }: ChatThreadProps) {
  const elapsedSec = (busyElapsedMs ?? 0) / 1000;
  const activeIdx = pipeline ? pipeline.stageIdx : fallbackActiveIndex(elapsedSec);
  const substepOverride = pipeline?.substep ?? null;
  const showPipeline = pipeline
    ? true
    : busyLabel === "Thinking…" && elapsedSec >= PIPELINE_REVEAL_AFTER_SEC;
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
            {showPipeline ? (
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
                      <span className="pipeline-step-detail">
                        <Typewriter
                          text={stageDetail(idx, activeIdx, elapsedSec, substepOverride)}
                          charsPerTick={1}
                          tickMs={22}
                        />
                      </span>
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
