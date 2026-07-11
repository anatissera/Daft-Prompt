"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import type { RosterItem, SongState } from "@/lib/types";
import type { PlayerApi } from "@/lib/playerApi";
import { instrumentColor } from "@/lib/colors";
import {
  buildTrackEvents,
  getAudibleTrackIds,
  getSongDurationSeconds,
  type TrackEvent,
} from "@/lib/trackMixerLogic.mjs";
import { buildMidiWithChannels, loadSoundBank, usesNativeSynth, workletUrl } from "@/lib/spessasynthPlayer";
import { NativeSynthLayer } from "@/lib/nativeSynthLayer";

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
  /** Per-track volume 0..1 (default 1). Applied live to both engines. */
  trackGains?: Record<string, number>;
  onMutedChange?: (next: Set<string>) => void;
  onSoloChange?: (next: Set<string>) => void;
  /** Populated with an engine-agnostic clock handle so the piano roll can
   *  share this transport's playhead. See lib/playerApi.ts. */
  playerApiRef?: MutableRefObject<PlayerApi | null>;
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
  trackGains,
  onMutedChange,
  onSoloChange,
  playerApiRef,
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
  // Second engine for `synth_preset` tracks. Runs on the same AudioContext
  // as spessasynth so both share a clock and mix into the same destination.
  const nativeLayerRef = useRef<NativeSynthLayer | null>(null);
  const nativePartIdsRef = useRef<Set<string>>(new Set());
  // Playback-speed multiplier shared by both engines (sequencer playbackRate
  // + native layer's wall-clock scheduling).
  const rateRef = useRef(1);

  const audibleTrackIds = useMemo(
    () => getAudibleTrackIds(trackIds, mutedTrackIds, soloTrackIds),
    [trackIds, mutedTrackIds, soloTrackIds],
  );

  const applyMuteState = useCallback(() => {
    const synth = synthRef.current;
    const layer = nativeLayerRef.current;
    // A native-handled part is one where the Tone.js layer is up AND actually
    // instantiated a synth for it. Muted-on-SF3 while native plays it prevents
    // doubling; if native isn't up, SF3 keeps the part audible as GM fallback.
    const nativeActiveIds = layer ? nativePartIdsRef.current : new Set<string>();
    if (synth) {
      const map = channelMapRef.current;
      for (const [partId, ch] of map) {
        const nativeCoversThis = nativeActiveIds.has(partId);
        const audible = audibleTrackIds.has(partId) && !nativeCoversThis;
        const gain = trackGains?.[partId] ?? 1;
        try {
          synth.midiChannels[ch]?.setSystemParameter("isMuted", !audible);
          // Per-track volume rides MIDI CC7 so it survives note-ons.
          synth.controllerChange(ch, 7, Math.round(Math.max(0, Math.min(1, gain)) * 127));
        } catch { /* channel may not exist yet during first ready cycle */ }
      }
    }
    if (layer) {
      for (const partId of nativePartIdsRef.current) {
        const gain = trackGains?.[partId] ?? 1;
        layer.setAudible(partId, audibleTrackIds.has(partId), gain);
      }
    }
  }, [audibleTrackIds, trackGains]);

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
      try { nativeLayerRef.current?.pause(); } catch { /* noop */ }
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
    try { nativeLayerRef.current?.dispose(); } catch { /* noop */ }
    nativeLayerRef.current = null;
    nativePartIdsRef.current = new Set();
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

      if (!ctx.audioWorklet) {
        // Browsers only expose AudioWorklet in secure contexts. Plain-HTTP
        // access (http://<lan-ip>:3001) hits this; localhost and HTTPS
        // (e.g. the tailscale serve URL) are fine.
        throw new Error(
          "el audio necesita un contexto seguro — abrí la app por HTTPS " +
            "(o localhost), no por http://IP:puerto",
        );
      }
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
      if (process.env.NODE_ENV !== "production") {
        // Dev-only inspection hook: lets us assert from the console which
        // preset each channel actually resolved to in the soundfont.
        (window as unknown as Record<string, unknown>).__daftDebug = { synth, seq, channelByPartId };
      }

      // Prepare the Tone.js layer for any `synth_preset` tracks. Shares the
      // same AudioContext as spessasynth so both engines have one clock
      // and mix into the same destination.
      const wantsNative = song.roster.some((item) => usesNativeSynth(item));
      if (wantsNative) {
        try {
          const layer = new NativeSynthLayer(ctx);
          await layer.prepare(song);
          // Trust the layer's `coveredPartIds()`, not the roster's flag —
          // only parts whose synth actually got built get their SF3 channel
          // muted; the rest fall back to SF3 GM instead of going silent.
          if (layer.hasAnyTracks()) {
            nativeLayerRef.current = layer;
            nativePartIdsRef.current = layer.coveredPartIds();
          } else {
            layer.dispose();
          }
        } catch (err) {
          // Never let a Tone.js failure kill playback — SF3 alone is a
          // valid degraded state. Log so we can debug in dev.
          console.warn("NativeSynthLayer failed to prepare; falling back to SF3-only", err);
        }
      }
      applyMuteState();
    } finally {
      setLoading(false);
    }
  }

  async function togglePlayback() {
    setError(null);
    if (playing) {
      try { seqRef.current?.pause(); } catch { /* noop */ }
      try { nativeLayerRef.current?.pause(); } catch { /* noop */ }
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
    let startAt = position;
    if (position >= seq.duration - 0.01) {
      seq.currentTime = 0;
      setPosition(0);
      startAt = 0;
    } else if (Math.abs(seq.currentTime - position) > 0.02) {
      seq.currentTime = position;
    }
    applyMuteState();
    seq.play();
    // Native layer plays in lockstep: schedule from the same offset the
    // sequencer resumes at. Both engines share ctx.currentTime.
    try { nativeLayerRef.current?.play(startAt); } catch { /* noop */ }
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
    // Native layer has no seek — cancel scheduled sounds and reschedule
    // on next play. If we're already playing, restart the native tracks
    // from the new offset so they stay aligned with spessasynth.
    const layer = nativeLayerRef.current;
    if (layer) {
      layer.pause();
      if (playing) {
        try { layer.play(clamped, rateRef.current); } catch { /* noop */ }
      }
    }
  }

  // Publish the engine-agnostic transport handle for the piano roll. Times
  // are musical seconds: the Sequencer reports song time regardless of
  // playbackRate, so the roll and the transport display never diverge.
  useEffect(() => {
    const ref = playerApiRef;
    if (!ref) return;
    const api: PlayerApi = {
      getTime: () => {
        const seq = seqRef.current;
        if (seq) {
          try { return seq.currentHighResolutionTime; } catch { /* fall through */ }
        }
        return position;
      },
      getDuration: () => duration,
      isPlaying: () => playing,
      seek: (seconds) => seek(seconds),
      setRate: (rate) => {
        const clamped = Math.min(1.5, Math.max(0.5, rate));
        rateRef.current = clamped;
        const seq = seqRef.current;
        if (seq) {
          try { seq.playbackRate = clamped; } catch { /* noop */ }
        }
        // Re-anchor the native layer's wall-clock schedule at the new rate.
        const layer = nativeLayerRef.current;
        if (layer && playing) {
          const at = seq ? seq.currentHighResolutionTime : position;
          layer.pause();
          try { layer.play(at, clamped); } catch { /* noop */ }
        }
      },
      getRate: () => rateRef.current,
    };
    ref.current = api;
    return () => {
      if (ref.current === api) ref.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playerApiRef, duration, playing, position]);

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
