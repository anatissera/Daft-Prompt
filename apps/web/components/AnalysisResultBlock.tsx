import type { ReferenceProfile } from "@/lib/types";
import {
  describeReferenceSummary,
  formatConfidence,
  formatDuration,
  getTopChordEstimates,
} from "@/lib/referenceProfileView.mjs";

export default function AnalysisResultBlock({ profile }: { profile: ReferenceProfile }) {
  const audio = profile.audio;
  const summaryRows = describeReferenceSummary(profile);
  const chordEstimates = getTopChordEstimates(profile, 5);

  return (
    <section className="result-block" aria-label="Reference analysis result">
      <div className="result-block-header">
        <div>
          <p className="section-title">Reference analysis</p>
          <h2 className="result-title">{profile.source.label}</h2>
          <p className="context-muted">{profile.summary || "Local audio profile ready."}</p>
        </div>
        <span className="reference-kind">{profile.source.kind}</span>
      </div>

      <dl className="profile-metrics">
        {summaryRows.map((row) => {
          const [label, ...valueParts] = row.split(" ");
          return (
            <div key={row} className="profile-metric">
              <dt>{label}</dt>
              <dd>{valueParts.join(" ")}</dd>
            </div>
          );
        })}
      </dl>

      {audio && audio.sections.length > 0 ? (
        <details className="details-panel" open>
          <summary className="details-summary">Energy and sections</summary>
          <ul className="section-list">
            {audio.sections.slice(0, 6).map((section) => (
              <li key={`${section.name}-${section.start_seconds}`} className="section-row">
                <div className="section-row-main">
                  <span className="section-row-name">{section.name}</span>
                  <span className="context-muted">
                    {formatDuration(section.start_seconds)}-{formatDuration(section.end_seconds)}
                  </span>
                </div>
                <div className="energy-meter" aria-label={`Energy ${Math.round((section.energy ?? 0) * 100)} percent`}>
                  <span style={{ width: `${Math.round((section.energy ?? 0) * 100)}%` }} />
                </div>
                <span className="context-muted">
                  Energy {section.energy === null ? "unknown" : `${Math.round(section.energy * 100)}%`} ·{" "}
                  {formatConfidence(section.energy_confidence >= 0.75 ? "high" : section.energy_confidence >= 0.5 ? "medium" : "low", section.energy_confidence)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {chordEstimates.length > 0 ? (
        <details className="details-panel">
          <summary className="details-summary">Probable chords</summary>
          <ul className="chord-list">
            {chordEstimates.map((estimate) => (
              <li key={`${estimate.timeRange}-${estimate.label}`} className="chord-row">
                <span className="chord-label">{estimate.label}</span>
                <span className="context-muted">
                  {estimate.timeRange} · {estimate.confidence}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
