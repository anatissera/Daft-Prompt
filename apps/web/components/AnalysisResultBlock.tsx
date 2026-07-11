import type { ReferenceProfile } from "@/lib/types";
import HarmonyTimeline from "@/components/HarmonyTimeline";
import {
  describeReferenceSummary,
  getAnalysisNotes,
  getKeyCandidateSummary,
  getLegacyEnergySections,
  getArrangement,
  getMainProgression,
  getStemListening,
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
  const stemListening = getStemListening(profile);
  const arrangement = getArrangement(profile);

  return (
    <section className="result-block" aria-label="Reference analysis result">
      <div className="result-block-header">
        <div>
          <p className="section-title">Reference analysis</p>
          <h2 className="result-title">{profile.source.label}</h2>
          <p className="context-muted">{profile.summary || "Evidence profile ready."}</p>
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
                  <span className="context-muted">{candidate.description} · {candidate.confidence}</span>
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

      {stemListening.length > 0 ? (
        <details className="details-panel" open>
          <summary className="details-summary">Deep listening</summary>
          <ul className="section-list">
            {stemListening.map((stem) => (
              <li key={stem.name} className="section-row">
                <div className="section-row-main">
                  <span className="section-row-name">{stem.name}</span>
                  <span className="listening-chips">
                    {stem.chips.map((chip) => (
                      <span key={`${stem.name}-${chip}`} className="listening-chip">{chip}</span>
                    ))}
                  </span>
                </div>
                {stem.callouts.length > 0 ? (
                  <span className="context-muted">{stem.callouts.join(" · ")}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {arrangement ? (
        <details className="details-panel" open>
          <summary className="details-summary">Arrangement</summary>
          <div className="arrangement-scroll">
            <table className="arrangement-grid">
              <thead>
                <tr>
                  <th scope="col" aria-label="Stem" />
                  {arrangement.columns.map((column) => (
                    <th key={`${column.section}-${column.bars}`} scope="col">
                      <span className="arrangement-section">{column.section}</span>
                      <span className="context-muted arrangement-bars">{column.bars}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {arrangement.stems.map((stem) => (
                  <tr key={stem}>
                    <th scope="row" className="arrangement-stem">{stem}</th>
                    {arrangement.columns.map((column) => {
                      const level = column.levels[stem] ?? "silent";
                      return (
                        <td key={`${stem}-${column.section}-${column.bars}`}>
                          <span
                            className={`arrangement-cell arrangement-${level}`}
                            title={`${stem}: ${level}`}
                            aria-label={`${stem} ${level} in ${column.section}`}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {arrangement.callouts.length > 0 ? (
            <p className="context-muted">{arrangement.callouts.join(" · ")}</p>
          ) : null}
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
