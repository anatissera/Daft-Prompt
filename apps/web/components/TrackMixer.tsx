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

interface SpessaChannel {
  setSystemParameter?: (name: string, value: boolean | number | string) => void;
}

interface SpessaSynth {
  connect(destination: AudioNode): void;
  soundBankManager: {
    addSoundBank(buffer: ArrayBuffer, name?: string): Promise<unknown> | unknown;
  };
  isReady: Promise<unknown>;
  midiChannels?: SpessaChannel[];
  controllerChange?: (channel: number, controller: number, value: number) => void;
}

interface SpessaSequencer {
  currentHighResolutionTime: number;
  currentTime: number;
  duration: number;
  isFinished: boolean;
  loopCount: number;
  loadNewSongList(songs: Array<{ binary: ArrayBuffer }>): void;
  pause(): void;
  play(): void;
}

interface SpessaModule {
  WorkletSynthesizer: new (context: BaseAudioContext) => SpessaSynth;
  Sequencer: new (synth: SpessaSynth, options?: { skipToFirstNoteOn?: boolean }) => SpessaSequencer;
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

  const contextRef = useRef<AudioContext | null>(null);
  const synthRef = useRef<SpessaSynth | null>(null);
  const sequencerRef = useRef<SpessaSequencer | null>(null);
  const channelByPartIdRef = useRef<Map<string, number>>(new Map());
  const frameRef = useRef<number | null>(null);
  const engineSongRef = useRef<SongState | null>(null);

  const audibleTrackIds = useMemo(
    () => getAudibleTrackIds(trackIds, mutedTrackIds, soloTrackIds),
    [trackIds, mutedTrackIds, soloTrackIds],
  );

  const stopAnimation = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }, []);

  const applyMuteState = useCallback(() => {
    const synth = synthRef.current;
    if (!synth) return;
    for (const [partId, channel] of channelByPartIdRef.current) {
      const audible = audibleTrackIds.has(partId);
      try {
        synth.midiChannels?.[channel]?.setSystemParameter?.("isMuted", !audible);
        synth.controllerChange?.(channel, 7, audible ? 114 : 0);
      } catch {
        // A channel can be briefly unavailable during worklet startup.
      }
    }
  }, [audibleTrackIds]);

  useEffect(() => {
    applyMuteState();
  }, [applyMuteState]);

  const teardown = useCallback(() => {
    stopAnimation();
    try { sequencerRef.current?.pause(); } catch { /* noop */ }
    sequencerRef.current = null;
    synthRef.current = null;
    channelByPartIdRef.current = new Map();
    engineSongRef.current = null;
    const context = contextRef.current;
    contextRef.current = null;
    if (context && context.state !== "closed") {
      context.close().catch(() => { /* noop */ });
    }
  }, [stopAnimation]);

  useEffect(() => () => teardown(), [teardown]);

  useEffect(() => {
    if (!engineSongRef.current || engineSongRef.current === song) return;
    teardown();
    setPlaying(false);
    setPosition(0);
  }, [song, teardown]);

  const tick = useCallback(() => {
    const sequencer = sequencerRef.current;
    if (!sequencer) return;
    const current = Math.max(0, sequencer.currentHighResolutionTime || sequencer.currentTime || 0);
    setPosition(Math.min(duration, current));
    if (sequencer.isFinished || current >= Math.max(0, sequencer.duration - 0.01)) {
      sequencer.pause();
      sequencer.currentTime = 0;
      setPosition(0);
      setPlaying(false);
      stopAnimation();
      return;
    }
    frameRef.current = requestAnimationFrame(tick);
  }, [duration, stopAnimation]);

  async function ensureEngine(): Promise<void> {
    if (synthRef.current && sequencerRef.current && engineSongRef.current === song) return;
    setLoading(true);
    try {
      if (!contextRef.current || contextRef.current.state === "closed") {
        contextRef.current = new AudioContext();
      }
      const context = contextRef.current;
      if (context.state === "suspended") await context.resume();

      const [spessa, soundBankBuffer] = await Promise.all([
        import("spessasynth_lib").then((module) => module as unknown as SpessaModule),
        loadSoundBank(),
      ]);
      await context.audioWorklet.addModule(workletUrl());

      const synth = new spessa.WorkletSynthesizer(context);
      synth.connect(context.destination);
      await synth.soundBankManager.addSoundBank(soundBankBuffer, "main");
      await synth.isReady;

      const { bytes, channelByPartId } = buildMidiWithChannels(song);
      const sequencer = new spessa.Sequencer(synth, { skipToFirstNoteOn: true });
      const midiBuffer = bytes.buffer.slice(
        bytes.byteOffset,
        bytes.byteOffset + bytes.byteLength,
      ) as ArrayBuffer;
      sequencer.loadNewSongList([{ binary: midiBuffer }]);
      sequencer.pause();
      sequencer.currentTime = 0;
      sequencer.loopCount = 0;

      synthRef.current = synth;
      sequencerRef.current = sequencer;
      channelByPartIdRef.current = channelByPartId;
      engineSongRef.current = song;
      applyMuteState();
    } finally {
      setLoading(false);
    }
  }

  async function togglePlayback() {
    setError(null);
    const sequencer = sequencerRef.current;
    if (playing) {
      try { sequencer?.pause(); } catch { /* noop */ }
      stopAnimation();
      setPlaying(false);
      return;
    }

    try {
      await ensureEngine();
    } catch (err) {
      setError(String((err as Error).message ?? err));
      return;
    }

    const nextSequencer = sequencerRef.current;
    const context = contextRef.current;
    if (!nextSequencer || !context) return;
    if (context.state === "suspended") await context.resume();
    if (position >= duration - 0.01) {
      nextSequencer.currentTime = 0;
      setPosition(0);
    } else if (Math.abs(nextSequencer.currentTime - position) > 0.02) {
      nextSequencer.currentTime = position;
    }
    applyMuteState();
    nextSequencer.play();
    setPlaying(true);
    stopAnimation();
    frameRef.current = requestAnimationFrame(tick);
  }

  function seek(value: number) {
    const next = Math.min(duration, Math.max(0, value));
    setPosition(next);
    const sequencer = sequencerRef.current;
    if (sequencer) {
      try { sequencer.currentTime = next; } catch { /* noop */ }
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
          {loading ? "Loading..." : playing ? "Pause" : "Play"}
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

      {error ? <p className="mixer-error">Playback error: {error}</p> : null}

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

function buildRows(song: SongState): TrackRow[] {
  const rosterById = new Map(song.roster.map((item) => [item.id, item]));
  const events = buildTrackEvents(song);
  return Object.entries(song.parts).map(([partId]) => {
    const roster = rosterById.get(partId) ?? {
      id: partId,
      instrument: partId,
      is_drum: false,
      midi_program: 0,
      midi_range: [0, 127] as [number, number],
      role: "",
      playing_style: "",
    };
    return { id: partId, roster, events: events[partId] ?? [] };
  });
}

function toggleSetItem(prev: Set<string>, item: string): Set<string> {
  const next = new Set(prev);
  if (next.has(item)) next.delete(item);
  else next.add(item);
  return next;
}

function formatTime(value: number) {
  const safe = Number.isFinite(value) ? Math.max(0, value) : 0;
  const minutes = Math.floor(safe / 60);
  const seconds = Math.floor(safe % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
