import type { Header, RosterItem } from "@/lib/types";
import { instrumentColor } from "@/lib/colors";

export default function RosterView({
  header,
  roster,
  source,
  embedded = false,
}: {
  header: Header;
  roster: RosterItem[];
  source: "director" | "canned";
  embedded?: boolean;
}) {
  return (
    <div className={embedded ? "embedded-panel" : "card"}>
      <h2 className="section-title">
        Roster{" "}
        <span className="source-tag">
          ({source === "director" ? "reasoned by director" : "canned demo"})
        </span>
      </h2>

      <div className="header-meta">
        <span className="meta-pill">{header.genre}</span>
        <span className="meta-pill">{header.key}</span>
        <span className="meta-pill">{header.tempo_bpm} bpm</span>
        <span className="meta-pill">{header.num_bars} bars</span>
      </div>

      <ul className="roster-list">
        {roster.map((r) => (
          <li key={r.id} className="roster-item">
            <span className="avatar" style={{ background: instrumentColor(r.id) }}>
              {r.instrument.slice(0, 1).toUpperCase()}
            </span>
            <span className="roster-item-body">
              <span className="roster-item-name">{r.instrument}</span>
              <span className="roster-item-role">{r.role}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
