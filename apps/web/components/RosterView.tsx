import type { Header, RosterItem } from "@/lib/types";
import { instrumentColor } from "@/lib/colors";

interface RosterViewProps {
  header: Header;
  roster: RosterItem[];
  source: "director" | "canned";
  embedded?: boolean;
  mutedTrackIds?: Set<string>;
  soloTrackIds?: Set<string>;
  onToggleMute?: (id: string) => void;
  onToggleSolo?: (id: string) => void;
}

export default function RosterView({
  header,
  roster,
  source,
  embedded = false,
  mutedTrackIds,
  soloTrackIds,
  onToggleMute,
  onToggleSolo,
}: RosterViewProps) {
  const hasControls = Boolean(onToggleMute && onToggleSolo);

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
        {roster.map((r, idx) => {
          const muted = mutedTrackIds?.has(r.id) ?? false;
          const solo = soloTrackIds?.has(r.id) ?? false;
          return (
            <li key={`${r.id || "agent"}-${idx}`} className="roster-item">
              <span className="avatar" style={{ background: instrumentColor(r.id) }}>
                {r.instrument.slice(0, 1).toUpperCase()}
              </span>
              <span className="roster-item-body">
                <span className="roster-item-name">{r.instrument}</span>
                <span className="roster-item-role">{r.role}</span>
              </span>
              {hasControls ? (
                <span className="roster-item-controls">
                  <button
                    type="button"
                    className={`roster-toggle${muted ? " roster-toggle-mute" : ""}`}
                    onClick={() => onToggleMute?.(r.id)}
                    aria-pressed={muted}
                    title={muted ? "Unmute" : "Mute"}
                  >M</button>
                  <button
                    type="button"
                    className={`roster-toggle${solo ? " roster-toggle-solo" : ""}`}
                    onClick={() => onToggleSolo?.(r.id)}
                    aria-pressed={solo}
                    title={solo ? "Unsolo" : "Solo"}
                  >S</button>
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
