"use client";

import dynamic from "next/dynamic";
import type { CompositionChatMessage } from "@/lib/chatTypes";
import NegotiationFeed from "@/components/NegotiationFeed";
import RosterView from "@/components/RosterView";

const ScoreViewer = dynamic(() => import("@/components/ScoreViewer"), { ssr: false });
const TrackMixer = dynamic(() => import("@/components/TrackMixer"), { ssr: false });

export default function GeneratedSongBlock({ message }: { message: CompositionChatMessage }) {
  const result = message.result;
  const hasPlayableParts = Object.keys(result.song.parts).length > 0;

  return (
    <section className="result-block" aria-label="Generated song">
      <div className="result-block-header">
        <div>
          <p className="section-title">Generated song</p>
          <h2 className="result-title">
            {result.song.header.genre} · {result.song.header.tempo_bpm} BPM
          </h2>
          <p className="context-muted">
            {hasPlayableParts
              ? "Playable sketch ready. Mixer and export controls are available below."
              : "The composition finished without playable parts."}
          </p>
        </div>
        <span className="reference-kind">{result.source}</span>
      </div>

      {hasPlayableParts ? (
        <>
          <TrackMixer song={result.song} />
          <a className="artifact-link" href={result.artifacts.midi}>
            Download full MIDI
          </a>
        </>
      ) : (
        <p className="empty-note">
          {result.song.errors.length > 0
            ? "Composition stopped before any playable parts were produced."
            : "No notes were composed for this song. Try composing again."}
        </p>
      )}

      {message.header ? (
        <details className="details-panel">
          <summary className="details-summary">Agents and arrangement</summary>
          <RosterView header={message.header} roster={result.song.roster} source={message.source ?? "canned"} embedded />
        </details>
      ) : null}

      {message.feed.length > 0 ? (
        <details className="details-panel">
          <summary className="details-summary">Negotiation details</summary>
          <NegotiationFeed events={message.feed} embedded />
        </details>
      ) : null}

      {hasPlayableParts ? (
        <details className="details-panel">
          <summary className="details-summary">Score</summary>
          <ScoreViewer musicXmlUrl={result.artifacts.musicxml} />
        </details>
      ) : null}
    </section>
  );
}
