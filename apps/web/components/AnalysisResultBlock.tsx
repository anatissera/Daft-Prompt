import type { ReferenceProfile } from "@/lib/types";
import HarmonyTimeline from "@/components/HarmonyTimeline";
import {
  describeReferenceSummary,
  getAnalysisNotes,
  getKeyCandidateSummary,
  getLegacyEnergySections,
  getMainProgression,
  getTopChordEstimates,
} from "@/lib/referenceProfileView.mjs";

export default function AnalysisResultBlock({ profile }: { profile: ReferenceProfile }) {
  const audio = profile.audio;
  const summaryRows = describeReferenceSummary(profile);
  const chordEstimates = getTopChordEstimates(profile, 5);
  const keyCandidates = getKeyCandidateSummary(profile);
  const mainProgression = getMainProgression(profile);
  const analysisNotes = getAnalysisNotes(profile);
  const legacyEnergySections = getLegacyEnergySections(profile);

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

      {keyCandidates.length > 0 || mainProgression ? (
        <details className="details-panel" open>
          <summary className="details-summary">Harmony</summary>
          {keyCandidates.length > 0 ? (
            <ul className="chord-list">
              {keyCandidates.map((candidate) => (
                <li key={candidate.label} className="chord-row">
                  <span className="chord-label">{candidate.label}</span>
                  <span className="context-muted">{candidate.confidence}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {mainProgression ? (
            <div className="analysis-callout">
              <span className="chord-label">{mainProgression.label}</span>
              <span className="context-muted">
                {mainProgression.bars} · repeats {mainProgression.repetitions}x · {mainProgression.confidence}
              </span>
              {audio?.harmony?.harmonic_rhythm_label ? (
                <span className="context-muted">Harmonic rhythm: {audio.harmony.harmonic_rhythm_label}</span>
              ) : null}
            </div>
          ) : null}
        </details>
      ) : null}

      {audio?.structure?.sections.length ? (
        <details className="details-panel" open>
          <summary className="details-summary">A/B/C timeline</summary>
          <HarmonyTimeline profile={profile} />
        </details>
      ) : null}

      {chordEstimates.length > 0 ? (
        <details className="details-panel">
          <summary className="details-summary">Probable triads</summary>
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

      {analysisNotes.length > 0 ? (
        <details className="details-panel" open>
          <summary className="details-summary">Analysis notes</summary>
          <ul className="chord-list">
            {analysisNotes.map((note) => (
              <li key={`${note.label}-${note.message}`} className="chord-row">
                <span className="chord-label">{note.label}</span>
                <span className="context-muted">{note.message}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {legacyEnergySections.length > 0 ? (
        <details className="details-panel">
          <summary className="details-summary">Legacy energy</summary>
          <ul className="section-list">
            {legacyEnergySections.slice(0, 6).map((section) => (
              <li key={`${section.name}-${section.timeRange}`} className="section-row">
                <div className="section-row-main">
                  <span className="section-row-name">{section.name}</span>
                  <span className="context-muted">{section.timeRange}</span>
                </div>
                <div className="energy-meter" aria-label={`Energy ${section.energy} percent`}>
                  <span style={{ width: `${section.energy}%` }} />
                </div>
                <span className="context-muted">Energy {section.energy}% · {section.confidence}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
