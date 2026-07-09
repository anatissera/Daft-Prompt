"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RosterItem, SongState } from "@/lib/types";
import { instrumentColor } from "@/lib/colors";
import {
  buildTrackEvents,
  getAudibleTrackIds,
  getSongDurationSeconds,
  type TrackEvent,
} from "@/lib/trackMixerLogic.mjs";
import { buildMidiWithChannels, loadSoundBank, workletUrl } from "@/lib/spessasynthPlayer";

type WorkletSynth = import("spessasynth_lib").WorkletSynthesizer;
type SeqType = import("spessasynth_lib").Sequencer;

interface TrackRow {
  id: string;
  roster: RosterItem;
  events: TrackEvent[];
}

interface TrackMixerProps {
  song: SongState;
  mutedTrackIds?: Set<string>;
  soloTrackIds?: Set<string>;
  onMutedChange?: (next: Set<string>) => void;
  onSoloChange?: (next: Set<string>) => void;
}

function buildRows(song: SongState): TrackRow[] {
  const rosterById = new Map(song.roster.map((item) => [item.id, item]));
  const events = buildTrackEvents(song);
  return Object.entries(song.parts).map(([partId]) => {
    const roster = rosterById.get(partId) ?? {
      id: partId, instrument: partId, is_drum: false,
      midi_program: 0, role: "",
    };
    return { id: partId, roster, events: events[partId] ?? [] };
  });
}

function toggleSetItem(prev: Set<string>, id: string): Set<string> {
  const next = new Set(prev);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

function formatTime(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function TrackMixer({
  song,
  mutedTrackIds: mutedProp,
  soloTrackIds: soloProp,
  onMutedChange,
  onSoloChange,
}: TrackMixerProps) {
  const rows = useMemo(() => buildRows(song), [song]);
  const trackIds = useMemo(() => rows.map((row) => row.id), [rows]);
  const eventsByTrack = useMemo(() => buildTrackEvents(song), [song]);
  const duration = useMemo(() => getSongDurationSeconds(song), [song]);

  const [internalMuted, setInternalMuted] = useState<Set<string>>(() => new Set());
  const [internalSolo, setInternalSolo] = useState<Set<string>>(() => new Set());
  const mutedTrackIds = mutedProp ?? internalMuted;
  const soloTrackIds = soloProp ?? internalSolo;

  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const ctxRef = useRef<AudioContext | null>(null);
  const synthRef = useRef<WorkletSynth | null>(null);
  const seqRef = useRef<SeqType | null>(null);
  const channelMapRef = useRef<Map<string, number>>(new Map());
  const rafRef = useRef<number | null>(null);
  const engineSongRef = useRef<SongState | null>(null);

  const audibleTrackIds = useMemo(
    () => getAudibleTrackIds(trackIds, mutedTrackIds, soloTrackIds),
    [trackIds, mutedTrackIds, soloTrackIds],
  );

  const applyMuteState = useCallback(() => {
    const synth = synthRef.current;
    if (!synth) return;
    const map = channelMapRef.current;
    for (const [partId, ch] of map) {
      const audible = audibleTrackIds.has(partId);
      try {
        synth.midiChannels[ch]?.setSystemParameter("isMuted", !audible);
      } catch { /* channel may not exist yet during first ready cycle */ }
    }
  }, [audibleTrackIds]);

  useEffect(() => { applyMuteState(); }, [applyMuteState]);

  const stopRaf = () => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  };

  const tick = useCallback(() => {
    const seq = seqRef.current;
    if (!seq) return;
    const t = seq.currentHighResolutionTime;
    setPosition(t);
    if (seq.isFinished || t >= seq.duration - 0.01) {
      seq.pause();
      seq.currentTime = 0;
      setPosition(0);
      setPlaying(false);
      stopRaf();
      return;
    }
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const teardown = useCallback(() => {
    stopRaf();
    try { seqRef.current?.pause(); } catch { /* noop */ }
    seqRef.current = undefined as unknown as SeqType;
    seqRef.current = null;
    const ctx = ctxRef.current;
    if (ctx && ctx.state !== "closed") ctx.close().catch(() => { /* noop */ });
    ctxRef.current = null;
    synthRef.current = null;
    channelMapRef.current = new Map();
    engineSongRef.current = null;
  }, []);

  useEffect(() => () => teardown(), [teardown]);

  // Rebuild the sequencer when the song identity changes while the engine is
  // already up.
  useEffect(() => {
    if (!engineSongRef.current) return;
    if (engineSongRef.current === song) return;
    // Song changed while paused/idle — tear down; next Play boots fresh.
    teardown();
    setPlaying(false);
    setPosition(0);
  }, [song, teardown]);

  async function ensureEngine(): Promise<void> {
    if (synthRef.current && seqRef.current && engineSongRef.current === song) return;
    setLoading(true);
    try {
      // AudioContext must be created after a user gesture; togglePlayback
      // funnels that through Play button. Recycle if we already have one.
      if (!ctxRef.current || ctxRef.current.state === "closed") {
        ctxRef.current = new AudioContext();
      }
      const ctx = ctxRef.current;
      if (ctx.state === "suspended") await ctx.resume();

      const spessa = await import("spessasynth_lib");
      // addModule is idempotent per URL — safe to call each engine boot.
      await ctx.audioWorklet.addModule(workletUrl());

      const sfBuf = await loadSoundBank();
      const synth = new spessa.WorkletSynthesizer(ctx);
      synth.connect(ctx.destination);
      // SoundFontManager wants its own copy — cache is reused; slice not needed.
      await synth.soundBankManager.addSoundBank(sfBuf, "main");
      await synth.isReady;

      const { bytes, channelByPartId } = buildMidiWithChannels(song);
      const seq = new spessa.Sequencer(synth, { skipToFirstNoteOn: true });
      // Sequencer autoplays on load; pause immediately so the play/pause
      // button owns the "did the user click play yet" state.
      const arrayBuf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
      seq.loadNewSongList([{ binary: arrayBuf }]);
      seq.pause();
      seq.currentTime = 0;
      seq.loopCount = 0;

      synthRef.current = synth;
      seqRef.current = seq;
      channelMapRef.current = channelByPartId;
      engineSongRef.current = song;
      applyMuteState();
    } finally {
      setLoading(false);
    }
  }

  async function togglePlayback() {
    setError(null);
    if (playing) {
      try { seqRef.current?.pause(); } catch { /* noop */ }
      stopRaf();
      setPlaying(false);
      return;
    }
    try {
      await ensureEngine();
    } catch (e) {
      setError(String((e as Error).message ?? e));
      return;
    }
    const seq = seqRef.current;
    const ctx = ctxRef.current;
    if (!seq || !ctx) return;
    if (ctx.state === "suspended") await ctx.resume();
    // If we're resuming from the end, restart from 0.
    if (position >= seq.duration - 0.01) {
      seq.currentTime = 0;
      setPosition(0);
    } else if (Math.abs(seq.currentTime - position) > 0.02) {
      seq.currentTime = position;
    }
    applyMuteState();
    seq.play();
    setPlaying(true);
    stopRaf();
    rafRef.current = requestAnimationFrame(tick);
  }

  function seek(value: number) {
    const clamped = Math.max(0, Math.min(duration, value));
    setPosition(clamped);
    const seq = seqRef.current;
    if (seq) {
      try { seq.currentTime = clamped; } catch { /* noop */ }
    }
  }

  const toggleMuted = useCallback(
    (id: string) => {
      const next = toggleSetItem(mutedTrackIds, id);
      if (onMutedChange) onMutedChange(next);
      else setInternalMuted(next);
    },
    [mutedTrackIds, onMutedChange],
  );
  const toggleSolo = useCallback(
    (id: string) => {
      const next = toggleSetItem(soloTrackIds, id);
      if (onSoloChange) onSoloChange(next);
      else setInternalSolo(next);
    },
    [soloTrackIds, onSoloChange],
  );

  return (
    <div className="track-mixer">
      <div className="mixer-transport">
        <button
          type="button"
          className="transport-button"
          onClick={togglePlayback}
          disabled={duration === 0 || loading}
        >
          {loading ? "Loading…" : playing ? "Pause" : "Play"}
        </button>
        <span className="transport-time">{formatTime(position)}</span>
        <input
          className="transport-range"
          type="range"
          min={0}
          max={Math.max(duration, 0.001)}
          step={0.01}
          value={Math.min(position, duration)}
          onChange={(event) => seek(Number(event.target.value))}
          aria-label="Playback position"
        />
        <span className="transport-time">{formatTime(duration)}</span>
      </div>

      {error ? <div className="mixer-error">Playback error: {error}</div> : null}

      <ul className="mixer-track-list">
        {rows.map((row) => {
          const muted = mutedTrackIds.has(row.id);
          const solo = soloTrackIds.has(row.id);
          const audible = audibleTrackIds.has(row.id);
          return (
            <li key={row.id} className={`mixer-track ${audible ? "mixer-track-active" : ""}`}>
              <span className="avatar" style={{ background: instrumentColor(row.id) }}>
                {row.roster.instrument.slice(0, 1).toUpperCase()}
              </span>
              <span className="mixer-track-body">
                <span className="roster-item-name">{row.roster.instrument}</span>
                <span className="roster-item-role">
                  {row.roster.role || row.id} · {(eventsByTrack[row.id] ?? []).length} notes
                </span>
              </span>
              <span className="mixer-track-actions">
                <button type="button" className={`mixer-toggle ${muted ? "mixer-toggle-on" : ""}`} onClick={() => toggleMuted(row.id)} aria-pressed={muted}>Mute</button>
                <button type="button" className={`mixer-toggle ${solo ? "mixer-toggle-on" : ""}`} onClick={() => toggleSolo(row.id)} aria-pressed={solo}>Solo</button>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
