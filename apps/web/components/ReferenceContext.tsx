import type { ReferenceProfile } from "@/lib/types";
import {
  describeReferenceSummary,
  formatConfidence,
  formatDuration,
  getTopChordEstimates,
} from "@/lib/referenceProfileView.mjs";

interface ReferenceContextProps {
  profile: ReferenceProfile | null;
  analyzing: boolean;
  selectedQuery: string | null;
}

export default function ReferenceContext({ profile, analyzing, selectedQuery }: ReferenceContextProps) {
  if (analyzing) {
    return (
      <aside className="context-panel" aria-live="polite">
        <p className="section-title">Reference research</p>
        <div className="analysis-status">
          <span className="spinner" aria-hidden="true" />
          <div>
            <p className="context-heading">Researching song sources...</p>
            <p className="context-muted">
              {selectedQuery ? `Searching sources for ${selectedQuery}.` : "Extracting public musical evidence."}
            </p>
          </div>
        </div>
      </aside>
    );
  }

  if (!profile) {
    return (
      <aside className="context-panel context-panel-empty">
        <p className="section-title">Reference research</p>
        <p className="context-heading">No reference yet</p>
        <p className="context-muted">Ask about a song by name to see its musical profile here.</p>
      </aside>
    );
  }

  const music = profile.music;
  const summaryRows = describeReferenceSummary(profile);
  const chordEstimates = getTopChordEstimates(profile, 5);

  return (
    <aside className="context-panel">
      <p className="section-title">Reference research</p>
      <div className="reference-header">
        <div>
          <h2 className="context-heading">{profile.source.label}</h2>
          <p className="context-muted">{profile.summary || "Research profile ready."}</p>
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

      {music && music.sections.length > 0 ? (
        <section className="context-section">
          <h3 className="context-subtitle">Energy and sections</h3>
          <ul className="section-list">
            {music.sections.slice(0, 6).map((section) => (
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
        </section>
      ) : null}

      {chordEstimates.length > 0 ? (
        <section className="context-section">
          <h3 className="context-subtitle">Probable chords</h3>
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
        </section>
      ) : null}
    </aside>
  );
}
