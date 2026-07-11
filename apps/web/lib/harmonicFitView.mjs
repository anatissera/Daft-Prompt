// Pure presentation logic for the harmonic-fit quality metric, kept out of React
// so it can be unit-tested directly (see AGENTS.md). `fit` is the backend's
// harmonic_fit map: { <instrumentId>: 0..1, _overall: 0..1 } (may be undefined on
// older responses).

const PCT = (x) => Math.round(x * 100);

/** Returns null when there's nothing to show, else { overallPct, rows } where rows
 *  is the per-instrument breakdown (the "_overall" synthetic key removed), sorted
 *  worst-fit first so the weakest instrument is easy to spot. */
export function harmonicFitView(fit) {
  if (!fit || typeof fit !== "object" || typeof fit._overall !== "number") {
    return null;
  }
  const rows = Object.entries(fit)
    .filter(([id]) => id !== "_overall")
    .map(([id, value]) => ({ id, pct: PCT(value) }))
    .sort((a, b) => a.pct - b.pct);
  return { overallPct: PCT(fit._overall), rows };
}

/** Qualitative band for coloring/labeling a fit percentage. */
export function harmonicFitLabel(pct) {
  if (pct >= 85) return "strong";
  if (pct >= 70) return "fair";
  return "weak";
}
