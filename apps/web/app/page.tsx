"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import type { ComposeEvent, ComposeResponse, Header, RosterItem } from "@/lib/types";
import NegotiationFeed from "@/components/NegotiationFeed";
import RosterView from "@/components/RosterView";

// client-only: both touch browser APIs / custom elements
const ScoreViewer = dynamic(() => import("@/components/ScoreViewer"), { ssr: false });
const TrackMixer = dynamic(() => import("@/components/TrackMixer"), { ssr: false });

type FeedEvent = Extract<ComposeEvent, { type: "agent_pass" | "convergence" | "error" }>;

export default function Home() {
  const [style, setStyle] = useState("Bee Gees-style disco");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<"director" | "canned" | null>(null);
  const [header, setHeader] = useState<Header | null>(null);
  const [roster, setRoster] = useState<RosterItem[]>([]);
  const [feed, setFeed] = useState<FeedEvent[]>([]);
  const [result, setResult] = useState<ComposeResponse | null>(null);

  async function compose(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSource(null);
    setHeader(null);
    setRoster([]);
    setFeed([]);
    setResult(null);

    try {
      const res = await fetch("/api/compose", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ style }),
      });
      if (!res.ok || !res.body) throw new Error(`backend error ${res.status}`);

      // Manual SSE parsing: EventSource can't send a POST body, so we read the
      // fetch body stream directly and split on the SSE "\n\n" event delimiter.
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          const event = JSON.parse(line.slice(5).trim()) as ComposeEvent;
          if (event.type === "director") {
            setSource(event.source);
            setHeader(event.header);
            setRoster(event.roster);
          } else if (event.type === "agent_pass" || event.type === "convergence" || event.type === "error") {
            setFeed((prev) => [...prev, event]);
            if (event.type === "error") {
              setError(event.message);
            }
          } else if (event.type === "done") {
            setResult(event);
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <p className="hero-eyebrow">
        <span className="hero-eyebrow-dot" aria-hidden="true" />
        Multi-agent composition
      </p>
      <h1 className="hero-title">Multiagent Band</h1>
      <p className="hero-subtitle">
        Describe a style and a band of agents composes and negotiates a song live.
      </p>

      <form onSubmit={compose} className="compose-form">
        <label htmlFor="style-input" className="sr-only">
          Musical style
        </label>
        <input
          id="style-input"
          value={style}
          onChange={(e) => setStyle(e.target.value)}
          placeholder="e.g. slow blues, Argentine cumbia…"
          className="compose-input"
        />
        <button type="submit" disabled={loading} className="compose-button">
          {loading && <span className="spinner" aria-hidden="true" />}
          {loading ? "Composing…" : "Compose"}
        </button>
      </form>

      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}

      {header && (
        <section className="results">
          <RosterView header={header} roster={roster} source={source ?? "canned"} />

          <NegotiationFeed events={feed} />

          {result && Object.keys(result.song.parts).length > 0 ? (
            <>
              <div className="card">
                <h2 className="section-title">Playback</h2>
                <TrackMixer song={result.song} />
                <a className="artifact-link" href={result.artifacts.midi}>
                  Download full MIDI
                </a>
              </div>

              <div className="card">
                <h2 className="section-title">Score</h2>
                <ScoreViewer musicXmlUrl={result.artifacts.musicxml} />
              </div>
            </>
          ) : result ? (
            <p className="empty-note">
              No notes were composed for this song — try composing again.
            </p>
          ) : null}
        </section>
      )}
    </main>
  );
}
