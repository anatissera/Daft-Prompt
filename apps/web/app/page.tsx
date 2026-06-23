"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import type { ComposeResponse } from "@/lib/types";

// client-only: both touch browser APIs / custom elements
const ScoreViewer = dynamic(() => import("@/components/ScoreViewer"), { ssr: false });
const MidiPlayer = dynamic(() => import("@/components/MidiPlayer"), { ssr: false });

export default function Home() {
  const [style, setStyle] = useState("Bee Gees-style disco");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ComposeResponse | null>(null);

  async function compose(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/compose", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ style }),
      });
      if (!res.ok) throw new Error(`backend error ${res.status}`);
      setResult((await res.json()) as ComposeResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 860, margin: "0 auto", padding: "3rem 1.25rem" }}>
      <h1 style={{ marginBottom: 4 }}>Multi-agent Band 🎵</h1>
      <p style={{ opacity: 0.7, marginTop: 0 }}>
        Describe a style and a band of agents composes a song. (Phase 1: canned
        output — proves the pipeline end-to-end.)
      </p>

      <form onSubmit={compose} style={{ display: "flex", gap: 8, margin: "1.5rem 0" }}>
        <input
          value={style}
          onChange={(e) => setStyle(e.target.value)}
          placeholder="e.g. slow blues, Argentine cumbia…"
          style={{
            flex: 1,
            padding: "0.6rem 0.8rem",
            borderRadius: 8,
            border: "1px solid #333",
            background: "#15151c",
            color: "inherit",
          }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: "0.6rem 1.1rem",
            borderRadius: 8,
            border: "none",
            background: loading ? "#444" : "#6d5dfc",
            color: "#fff",
            cursor: loading ? "default" : "pointer",
          }}
        >
          {loading ? "Composing…" : "Compose"}
        </button>
      </form>

      {error && <p style={{ color: "#ff6b6b" }}>⚠ {error}</p>}

      {result && (
        <section style={{ display: "grid", gap: "1.5rem" }}>
          <div>
            <h2 style={{ marginBottom: 8 }}>
              Roster{" "}
              <span style={{ fontSize: 12, opacity: 0.6, fontWeight: 400 }}>
                ({result.source === "director" ? "reasoned by director" : "canned demo"})
              </span>
            </h2>
            <ul>
              {result.song.roster.map((r) => (
                <li key={r.id}>
                  <strong>{r.instrument}</strong> — {r.role}
                </li>
              ))}
            </ul>
          </div>

          {Object.keys(result.song.parts).length > 0 ? (
            <>
              <div>
                <h2 style={{ marginBottom: 8 }}>Playback</h2>
                <MidiPlayer midiUrl={result.artifacts.midi} />
              </div>

              <div>
                <h2 style={{ marginBottom: 8 }}>Score</h2>
                <ScoreViewer musicXmlUrl={result.artifacts.musicxml} />
              </div>
            </>
          ) : (
            <p style={{ opacity: 0.6 }}>
              The director set the arrangement; instrument agents compose the notes
              in a later phase.
            </p>
          )}
        </section>
      )}
    </main>
  );
}
