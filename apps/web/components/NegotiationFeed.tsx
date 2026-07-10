import type { ComposeEvent } from "@/lib/types";
import { instrumentColor } from "@/lib/colors";

type FeedEvent = Extract<ComposeEvent, { type: "agent_pass" | "convergence" | "error" }>;

function stageDuration(event: Extract<FeedEvent, { type: "agent_pass" | "convergence" }>): string {
  return typeof event.stage_elapsed_seconds === "number"
    ? ` · ${event.stage_elapsed_seconds.toFixed(1)}s`
    : "";
}

function CheckIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3 8.5L6.2 11.5L13 4.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function XIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3.5 3.5L12.5 12.5M12.5 3.5L3.5 12.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3 8H13M9 4L13 8L9 12"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function NegotiationFeed({ events, embedded = false }: { events: FeedEvent[]; embedded?: boolean }) {
  if (events.length === 0) return null;

  return (
    <div className={embedded ? "embedded-panel" : "card"}>
      <h2 className="section-title">Negotiation</h2>
      <ul className="feed-list">
        {events.map((e, i) =>
          e.type === "error" ? (
            <li key={i} className="feed-entry">
              <span className="feed-rail">
                <span
                  className="avatar"
                  style={{
                    background: "var(--color-danger)",
                    width: 24,
                    height: 24,
                    fontSize: 11,
                  }}
                >
                  !
                </span>
              </span>
              <span className="feed-body">
                <span className="feed-header">
                  <span className="feed-instrument">model error</span>
                  <span className="feed-round">{e.provider ?? "provider"}</span>
                </span>
                <p className="feed-summary">{e.message}</p>
              </span>
            </li>
          ) : e.type === "agent_pass" ? (
            <li key={i} className="feed-entry">
              <span className="feed-rail">
                <span
                  className="avatar"
                  style={{
                    background: instrumentColor(e.instrument_id),
                    width: 24,
                    height: 24,
                    fontSize: 11,
                  }}
                >
                  {e.instrument_id.slice(0, 1).toUpperCase()}
                </span>
              </span>
              <span className="feed-body">
                <span className="feed-header">
                  <span className="feed-instrument">{e.instrument_id}</span>
                  <span className="feed-round">round {e.round}{stageDuration(e)}</span>
                </span>
                <p className="feed-summary">{e.notes_summary}</p>

                {(e.new_requests.length > 0 || e.resolved_requests.length > 0) && (
                  <ul className="feed-sub-list">
                    {e.new_requests.map((r) => (
                      <li key={r.id} className="feed-chip">
                        <span className="feed-chip-icon" style={{ color: "var(--color-accent)" }}>
                          <ArrowIcon />
                        </span>
                        <span>
                          asked <strong>{r.to}</strong>: {r.request}
                        </span>
                      </li>
                    ))}
                    {e.resolved_requests.map((r) => (
                      <li key={r.id} className="feed-chip">
                        <span
                          className="feed-chip-icon"
                          style={{
                            color: r.status === "resolved" ? "var(--color-success)" : "var(--color-danger)",
                          }}
                        >
                          {r.status === "resolved" ? <CheckIcon /> : <XIcon />}
                        </span>
                        <span>
                          {r.request} — {r.resolution}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </span>
            </li>
          ) : (
            <li key={i} className="feed-convergence">
              <span className="feed-convergence-line" />
              <span>
                Round {e.round} converged{stageDuration(e)}
                {e.resolved_requests.length > 0
                  ? ` — arbiter resolved ${e.resolved_requests.length} request(s)`
                  : ""}
              </span>
              <span className="feed-convergence-line" />
            </li>
          )
        )}
      </ul>
    </div>
  );
}
