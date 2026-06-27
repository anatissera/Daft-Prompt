import type { ReferenceProfile } from "@/lib/types";
import { getStructureTimeline } from "@/lib/referenceProfileView.mjs";

export default function HarmonyTimeline({ profile }: { profile: ReferenceProfile }) {
  const sections = getStructureTimeline(profile);
  if (sections.length === 0) return null;

  return (
    <div className="harmony-timeline" aria-label="A/B/C structure timeline">
      {sections.map((section) => (
        <div key={`${section.label}-${section.bars}`} className="harmony-timeline-section">
          <span className="harmony-section-label">{section.label}</span>
          <span className="context-muted">bars {section.bars}</span>
          {section.progression ? <span className="harmony-progression">{section.progression}</span> : null}
          <span className="context-muted">{section.confidence}</span>
        </div>
      ))}
    </div>
  );
}
