"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import type { CompositionChatMessage } from "@/lib/chatTypes";
import type { Part, RosterItem, SongState } from "@/lib/types";
import { getAudibleTrackIds } from "@/lib/trackMixerLogic.mjs";
import { harmonicFitView, harmonicFitLabel } from "@/lib/harmonicFitView.mjs";
import { triggerMidiDownload } from "@/lib/midiExport";
import { triggerMp3Download } from "@/lib/mp3Export";
import NegotiationFeed from "@/components/NegotiationFeed";
import RosterView from "@/components/RosterView";

const ScoreViewer = dynamic(() => import("@/components/ScoreViewer"), { ssr: false });
const TrackMixer = dynamic(() => import("@/components/TrackMixer"), { ssr: false });

function hasMixState(muted: Set<string>, solo: Set<string>): boolean {
  return muted.size > 0 || solo.size > 0;
}

function toggleSetItem(prev: Set<string>, id: string): Set<string> {
  const next = new Set(prev);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/** Director-LLM occasionally emits empty or duplicated instrument ids. Re-key
 *  every roster item to something unique and re-bind matching parts so the
 *  mute/solo state shared between Roster and TrackMixer references the same
 *  key set. */
function normalizeSong(song: SongState): SongState {
  const used = new Set<string>();
  const newRoster: RosterItem[] = [];
  const remap: Array<{ from: string; to: string }> = [];
  song.roster.forEach((r, idx) => {
    const base = (r.id || r.instrument || `agent_${idx}`).trim() || `agent_${idx}`;
    let candidate = base;
    let n = 2;
    while (used.has(candidate)) candidate = `${base}_${n++}`;
    used.add(candidate);
    newRoster.push({ ...r, id: candidate });
    remap.push({ from: r.id, to: candidate });
  });
  // Map each part key onto the first roster item that originally claimed it,
  // preserving order so duplicates land on the first matching renamed id.
  const newParts: Record<string, Part> = {};
  const claimedFrom = new Set<string>();
  Object.entries(song.parts).forEach(([partKey, part]) => {
    const match = remap.find((m) => m.from === partKey && !claimedFrom.has(m.to));
    const newKey = match ? match.to : (partKey || `part_${Object.keys(newParts).length}`);
    if (match) claimedFrom.add(match.to);
    newParts[newKey] = { ...part, instrument_id: newKey };
  });
  return { ...song, roster: newRoster, parts: newParts };
}

export default function GeneratedSongBlock({ message }: { message: CompositionChatMessage }) {
  const result = message.result;
  const song = useMemo(() => normalizeSong(result.song), [result.song]);
  const hasPlayableParts = Object.keys(song.parts).length > 0;
  const h = song.header;
  const partsCount = Object.keys(song.parts).length;
  const fit = useMemo(() => harmonicFitView(result.harmonic_fit), [result.harmonic_fit]);

  // Lifted so Roster cards (display + buttons) and TrackMixer (audio gain)
  // share the same Mute/Solo state.
  const [mutedTrackIds, setMutedTrackIds] = useState<Set<string>>(() => new Set());
  const [soloTrackIds, setSoloTrackIds] = useState<Set<string>>(() => new Set());
  const [mp3State, setMp3State] = useState<"idle" | "rendering" | "error">("idle");
  const [mp3Error, setMp3Error] = useState<string | null>(null);

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
            {fit ? (
              <li title="Fraction of notes that fit the active chord">
                <span>HARMONY</span>
                <strong data-fit={harmonicFitLabel(fit.overallPct)}>{fit.overallPct}%</strong>
              </li>
            ) : null}
          </ul>
        </div>
      </header>

      {message.header ? (
        <RosterView
          header={message.header}
          roster={song.roster}
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
            song={song}
            mutedTrackIds={mutedTrackIds}
            soloTrackIds={soloTrackIds}
            onMutedChange={setMutedTrackIds}
            onSoloChange={setSoloTrackIds}
          />
          <div className="artifact-link-row">
            <button
              type="button"
              className="artifact-link"
              onClick={() => {
                const partIds = Object.keys(song.parts);
                const audible = getAudibleTrackIds(partIds, mutedTrackIds, soloTrackIds);
                triggerMidiDownload(song, audible);
              }}
            >
              ↓ Download MIDI ({hasMixState(mutedTrackIds, soloTrackIds) ? "audible tracks" : "full"})
            </button>
            <button
              type="button"
              className="artifact-link"
              disabled={mp3State === "rendering"}
              onClick={async () => {
                setMp3State("rendering");
                setMp3Error(null);
                try {
                  await triggerMp3Download(song);
                  setMp3State("idle");
                } catch (e) {
                  setMp3Error(String((e as Error).message ?? e));
                  setMp3State("error");
                }
              }}
            >
              {mp3State === "rendering" ? "Rendering MP3…" : "↓ Download MP3"}
            </button>
          </div>
          {mp3Error ? <p className="empty-note">MP3 render failed: {mp3Error}</p> : null}
        </>
      ) : (
        <p className="empty-note">
          {result.song.errors.length > 0
            ? "Composition stopped before any playable parts were produced."
            : "No notes were composed for this song. Try composing again."}
        </p>
      )}

      {fit && fit.rows.length > 0 ? (
        <details className="details-panel">
          <summary className="details-summary">
            Harmonic fit · {fit.overallPct}% chord tones
          </summary>
          <ul className="harmony-fit-list">
            {fit.rows.map((row) => (
              <li key={row.id} className="harmony-fit-row">
                <span className="harmony-fit-id">{row.id}</span>
                <span className="harmony-fit-bar" aria-hidden="true">
                  <span
                    className="harmony-fit-bar-fill"
                    data-fit={harmonicFitLabel(row.pct)}
                    style={{ width: `${row.pct}%` }}
                  />
                </span>
                <span className="harmony-fit-pct">{row.pct}%</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

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
