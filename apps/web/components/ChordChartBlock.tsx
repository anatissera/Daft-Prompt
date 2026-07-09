import type { ChordChartRow } from "@/lib/types";

export default function ChordChartBlock({ rows }: { rows: ChordChartRow[] }) {
  return <section className="chord-chart" aria-label="Probable chord chart">
    <header><p>Probable chords</p><span>Estimated from local audio</span></header>
    <ol>{rows.map((row) => <li key={row.label}><strong>{row.label}</strong><div>{row.chords.map((chord) => <b key={chord}>{chord}</b>)}</div><small>{Math.round(row.confidence * 100)}% confidence</small></li>)}</ol>
  </section>;
}
