"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import type { CompositionChatMessage } from "@/lib/chatTypes";
import NegotiationFeed from "@/components/NegotiationFeed";
import RosterView from "@/components/RosterView";

const ScoreViewer = dynamic(() => import("@/components/ScoreViewer"), { ssr: false });
const TrackMixer = dynamic(() => import("@/components/TrackMixer"), { ssr: false });

function toggleSetItem(prev: Set<string>, id: string): Set<string> {
  const next = new Set(prev);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

export default function GeneratedSongBlock({ message }: { message: CompositionChatMessage }) {
  const result = message.result;
  const hasPlayableParts = Object.keys(result.song.parts).length > 0;
  const h = result.song.header;
  const partsCount = Object.keys(result.song.parts).length;

  // Lifted so Roster cards (display + buttons) and TrackMixer (audio gain)
  // share the same Mute/Solo state.
  const [mutedTrackIds, setMutedTrackIds] = useState<Set<string>>(() => new Set());
  const [soloTrackIds, setSoloTrackIds] = useState<Set<string>>(() => new Set());

  return (
    <section className="song-deck" aria-label="Generated song">
      <header className="song-deck-header">
        <div className="song-deck-stencil">
          <span className="song-deck-stencil-label">TRK</span>
          <span className="song-deck-stencil-number">001</span>
        </div>
        <div className="song-deck-title-block">
          <p className="song-deck-eyebrow">— Generated · {result.source} —</p>
          <h2 className="song-deck-title">{h.genre}</h2>
          <ul className="song-deck-specs">
            <li><span>KEY</span><strong>{h.key}</strong></li>
            <li><span>BPM</span><strong>{Math.round(h.tempo_bpm)}</strong></li>
            <li><span>METER</span><strong>{h.time_signature[0]}/{h.time_signature[1]}</strong></li>
            <li><span>BARS</span><strong>{h.num_bars}</strong></li>
            <li><span>AGENTS</span><strong>{partsCount}</strong></li>
          </ul>
        </div>
      </header>

      {message.header ? (
        <RosterView
          header={message.header}
          roster={result.song.roster}
          source={message.source ?? "canned"}
          embedded
          mutedTrackIds={mutedTrackIds}
          soloTrackIds={soloTrackIds}
          onToggleMute={(id) => setMutedTrackIds((prev) => toggleSetItem(prev, id))}
          onToggleSolo={(id) => setSoloTrackIds((prev) => toggleSetItem(prev, id))}
        />
      ) : null}

      {hasPlayableParts ? (
        <>
          <TrackMixer
            song={result.song}
            mutedTrackIds={mutedTrackIds}
            soloTrackIds={soloTrackIds}
            onMutedChange={setMutedTrackIds}
            onSoloChange={setSoloTrackIds}
          />
          <a className="artifact-link" href={result.artifacts.midi}>
            ↓ Download full MIDI
          </a>
        </>
      ) : (
        <p className="empty-note">
          {result.song.errors.length > 0
            ? "Composition stopped before any playable parts were produced."
            : "No notes were composed for this song. Try composing again."}
        </p>
      )}

      {hasPlayableParts ? (
        <details className="score-frame">
          <summary className="details-summary">◐ Score</summary>
          <ScoreViewer musicXmlUrl={result.artifacts.musicxml} />
        </details>
      ) : null}

      {message.feed.length > 0 ? (
        <details className="details-panel">
          <summary className="details-summary">Negotiation log · {message.feed.length}</summary>
          <NegotiationFeed events={message.feed} embedded />
        </details>
      ) : null}
    </section>
  );
}
