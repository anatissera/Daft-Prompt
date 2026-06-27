"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { RosterItem, SongState } from "@/lib/types";
import { instrumentColor } from "@/lib/colors";
import {
  buildTrackEvents,
  getAudibleTrackIds,
  getSongDurationSeconds,
  type TrackEvent,
} from "@/lib/trackMixerLogic.mjs";

interface ScheduledSource {
  stop: () => void;
}

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
  // Controlled when props provided; falls back to internal state otherwise.
  const [internalMuted, setInternalMuted] = useState<Set<string>>(() => new Set());
  const [internalSolo, setInternalSolo] = useState<Set<string>>(() => new Set());
  const mutedTrackIds = mutedProp ?? internalMuted;
  const soloTrackIds = soloProp ?? internalSolo;
  const setMutedTrackIds = (updater: (prev: Set<string>) => Set<string>) => {
    const next = updater(mutedTrackIds);
    if (onMutedChange) onMutedChange(next);
    else setInternalMuted(next);
  };
  const setSoloTrackIds = (updater: (prev: Set<string>) => Set<string>) => {
    const next = updater(soloTrackIds);
    if (onSoloChange) onSoloChange(next);
    else setInternalSolo(next);
  };
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const audioRef = useRef<AudioContext | null>(null);
  const startedAtRef = useRef(0);
  const offsetRef = useRef(0);
  const gainByTrackRef = useRef<Map<string, GainNode>>(new Map());
  const sourcesRef = useRef<ScheduledSource[]>([]);
  const timerRef = useRef<number | null>(null);

  const audibleTrackIds = useMemo(
    () => getAudibleTrackIds(trackIds, mutedTrackIds, soloTrackIds),
    [mutedTrackIds, soloTrackIds, trackIds],
  );

  useEffect(() => {
    updateTrackGains(gainByTrackRef.current, audibleTrackIds);
  }, [audibleTrackIds]);

  useEffect(() => {
    return () => {
      stopPlayback(false);
      void audioRef.current?.close();
      audioRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleMuted(trackId: string) {
    setMutedTrackIds((prev) => toggleSetItem(prev, trackId));
  }

  function toggleSolo(trackId: string) {
    setSoloTrackIds((prev) => toggleSetItem(prev, trackId));
  }

  async function togglePlayback() {
    if (playing) {
      stopPlayback(false);
      return;
    }

    const context = getAudioContext(audioRef);
    if (context.state === "suspended") {
      await context.resume();
    }

    const startOffset = position >= duration ? 0 : position;
    offsetRef.current = startOffset;
    startedAtRef.current = context.currentTime - startOffset;
    gainByTrackRef.current = createTrackGains(context, trackIds, audibleTrackIds);
    sourcesRef.current = scheduleSong(context, eventsByTrack, rows, gainByTrackRef.current, startOffset);
    setPlaying(true);
    startTimer(context, duration, stopPlayback, setPosition, timerRef, startedAtRef);
  }

  function stopPlayback(resetPosition: boolean) {
    stopSources(sourcesRef.current);
    sourcesRef.current = [];
    gainByTrackRef.current = new Map();
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setPlaying(false);
    if (resetPosition) setPosition(0);
  }

  function seek(nextValue: number) {
    const nextPosition = Math.min(duration, Math.max(0, nextValue));
    const wasPlaying = playing;
    if (wasPlaying) stopPlayback(false);
    setPosition(nextPosition);
    offsetRef.current = nextPosition;
  }

  return (
    <div className="track-mixer">
      <div className="mixer-transport">
        <button type="button" className="transport-button" onClick={togglePlayback} disabled={duration === 0}>
          {playing ? "Stop" : "Play"}
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
                  {row.roster.role || row.id} · {row.events.length} notes
                </span>
              </span>
              <span className="mixer-track-actions">
                <button
                  type="button"
                  className={`mixer-toggle ${muted ? "mixer-toggle-on" : ""}`}
                  onClick={() => toggleMuted(row.id)}
                  aria-pressed={muted}
                >
                  Mute
                </button>
                <button
                  type="button"
                  className={`mixer-toggle ${solo ? "mixer-toggle-on" : ""}`}
                  onClick={() => toggleSolo(row.id)}
                  aria-pressed={solo}
                >
                  Solo
                </button>
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
  const eventsByTrack = buildTrackEvents(song);

  return Object.entries(song.parts).map(([partId]) => {
    const roster = rosterById.get(partId) ?? {
      id: partId,
      instrument: partId,
      is_drum: false,
      midi_program: 0,
      midi_range: [0, 127],
      role: "",
    };
    return { id: partId, roster, events: eventsByTrack[partId] ?? [] };
  });
}

function getAudioContext(ref: React.MutableRefObject<AudioContext | null>) {
  if (!ref.current) {
    ref.current = new AudioContext();
  }
  return ref.current;
}

function createTrackGains(context: AudioContext, trackIds: string[], audibleTrackIds: Set<string>) {
  const gains = new Map<string, GainNode>();
  for (const trackId of trackIds) {
    const gain = context.createGain();
    gain.gain.value = audibleTrackIds.has(trackId) ? 0.85 : 0;
    gain.connect(context.destination);
    gains.set(trackId, gain);
  }
  return gains;
}

function updateTrackGains(gains: Map<string, GainNode>, audibleTrackIds: Set<string>) {
  for (const [trackId, gain] of gains) {
    gain.gain.setTargetAtTime(audibleTrackIds.has(trackId) ? 0.85 : 0, gain.context.currentTime, 0.01);
  }
}

function scheduleSong(
  context: AudioContext,
  eventsByTrack: Record<string, TrackEvent[]>,
  rows: TrackRow[],
  gains: Map<string, GainNode>,
  offsetSeconds: number,
) {
  const sources: ScheduledSource[] = [];
  const now = context.currentTime;

  for (const row of rows) {
    const trackGain = gains.get(row.id);
    if (!trackGain) continue;
    for (const event of eventsByTrack[row.id] ?? []) {
      if (event.startSeconds + event.durationSeconds <= offsetSeconds) continue;
      const startAt = now + Math.max(0, event.startSeconds - offsetSeconds);
      if (row.roster.is_drum) {
        sources.push(scheduleDrum(context, trackGain, event, startAt));
      } else {
        sources.push(scheduleTone(context, trackGain, event, startAt));
      }
    }
  }

  return sources;
}

function scheduleTone(context: AudioContext, destination: GainNode, event: TrackEvent, startAt: number): ScheduledSource {
  const osc = context.createOscillator();
  const gain = context.createGain();
  osc.type = "sine";
  osc.frequency.value = event.frequency;
  gain.gain.setValueAtTime(0.0001, startAt);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.02, event.velocity * 0.22), startAt + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + event.durationSeconds);
  osc.connect(gain);
  gain.connect(destination);
  osc.start(startAt);
  osc.stop(startAt + event.durationSeconds + 0.02);
  return osc;
}

function scheduleDrum(context: AudioContext, destination: GainNode, event: TrackEvent, startAt: number): ScheduledSource {
  const osc = context.createOscillator();
  const gain = context.createGain();
  osc.type = event.pitch === 42 ? "square" : "triangle";
  osc.frequency.value = drumFrequency(event.pitch);
  const duration = Math.min(0.18, event.durationSeconds);
  gain.gain.setValueAtTime(Math.max(0.03, event.velocity * 0.28), startAt);
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);
  osc.connect(gain);
  gain.connect(destination);
  osc.start(startAt);
  osc.stop(startAt + duration + 0.02);
  return osc;
}

function drumFrequency(pitch: number) {
  if (pitch === 36) return 80;
  if (pitch === 38) return 190;
  if (pitch === 42) return 1800;
  return 220;
}

function stopSources(sources: ScheduledSource[]) {
  for (const source of sources) {
    try {
      source.stop();
    } catch {
      // Already stopped by the Web Audio scheduler.
    }
  }
}

function startTimer(
  context: AudioContext,
  duration: number,
  stopPlayback: (resetPosition: boolean) => void,
  setPosition: (value: number) => void,
  timerRef: React.MutableRefObject<number | null>,
  startedAtRef: React.MutableRefObject<number>,
) {
  timerRef.current = window.setInterval(() => {
    const current = context.currentTime - startedAtRef.current;
    if (current >= duration) {
      setPosition(duration);
      stopPlayback(true);
      return;
    }
    setPosition(current);
  }, 50);
}

function toggleSetItem(prev: Set<string>, item: string) {
  const next = new Set(prev);
  if (next.has(item)) {
    next.delete(item);
  } else {
    next.add(item);
  }
  return next;
}

function formatTime(value: number) {
  const safeValue = Number.isFinite(value) ? Math.max(0, value) : 0;
  const minutes = Math.floor(safeValue / 60);
  const seconds = Math.floor(safeValue % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
