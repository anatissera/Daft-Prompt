import type { AnalysisStageState } from "@/lib/analysisProgress.mjs";


export default function AnalysisProgressChecklist({
  stages,
}: {
  stages: AnalysisStageState[];
}) {
  return (
    <article className="chat-message chat-message-system analysis-progress" aria-label="Analysis progress">
      <span className="chat-role">working</span>
      <ol className="analysis-progress-list">
        {stages.map((stage) => (
          <li
            key={stage.id}
            className={`analysis-progress-stage analysis-progress-${stage.status}`}
          >
            <span className="analysis-progress-indicator" aria-hidden="true">
              {stage.status === "completed" ? "✓" : stage.status === "active" ? "●" : "○"}
            </span>
            <span>{stage.label}</span>
            {stage.cacheHit ? <span className="context-muted">reused local cache</span> : null}
            {stage.status === "completed" && stage.elapsedSeconds !== null ? (
              <span className="analysis-progress-time">{stage.elapsedSeconds.toFixed(1)} s</span>
            ) : null}
          </li>
        ))}
      </ol>
    </article>
  );
}
