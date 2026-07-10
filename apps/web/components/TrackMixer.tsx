"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import type * as ToneType from "tone";
import type { RosterItem, SongState } from "@/lib/types";
import type { PlayerApi } from "@/lib/playerApi";
import { instrumentColor } from "@/lib/colors";
import {
  buildTrackEvents,
  getAudibleTrackIds,
  getSongDurationSeconds,
  type TrackEvent,
} from "@/lib/trackMixerLogic.mjs";
import {
  FLUIDR3_BASE,
  PERCUSSION_MAX,
  PERCUSSION_MIN,
  folderForProgram,
  midiToFileName,
  midiToName,
  resolveIsDrum,
  resolveProgram,
} from "@/lib/gmInstruments";

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
  // Populated with an engine-agnostic clock handle so a piano roll can share
  // this transport's playhead. See lib/playerApi.ts.
  playerApiRef?: MutableRefObject<PlayerApi | null>;
}

// Lazy import keeps Tone.js out of the initial bundle.
async function loadTone(): Promise<typeof ToneType> {
  return (await import("tone")) as unknown as typeof ToneType;
}

// Notes are scheduled in tempo-derived seconds against the transport at this
// base tempo; speed changes then scale wall-clock via Transport.bpm while the
// tick timeline (and thus musical seconds below) stays fixed.
const BASE_BPM = 120;

// Musical seconds = the tempo timeline buildTrackEvents produced, read straight
// from the transport tick counter so it is invariant to the playback rate.
function musicalSeconds(Tone: typeof ToneType): number {
  const ticksPerSecond = (Tone.Transport.PPQ * BASE_BPM) / 60;
  return ticksPerSecond > 0 ? Tone.Transport.ticks / ticksPerSecond : 0;
}

function musicalSecondsToTicks(Tone: typeof ToneType, seconds: number): number {
  return Math.round((seconds * Tone.Transport.PPQ * BASE_BPM) / 60);
}

// 5 sparse base notes give Tone.Sampler enough anchors to pitch-shift smoothly.
const MELODIC_ANCHORS = ["C2", "C3", "C4", "C5", "C6"];
// FluidR3 percussion folder uses letter-note names mapped to drum keys.
const DRUM_KEYS: number[] = [];
for (let n = PERCUSSION_MIN; n <= PERCUSSION_MAX; n++) DRUM_KEYS.push(n);

function melodicUrls(): Record<string, string> {
  const urls: Record<string, string> = {};
  // Anchors are natural notes only, so file name == Tone key.
  for (const n of MELODIC_ANCHORS) urls[n] = `${n}.mp3`;
  return urls;
}

function drumUrls(): Record<string, string> {
  const urls: Record<string, string> = {};
  // Tone needs `C#2`-style keys; FluidR3 ships `Cs2.mp3` files.
  for (const k of DRUM_KEYS) urls[midiToName(k)] = `${midiToFileName(k)}.mp3`;
  return urls;
}

export default function TrackMixer({
  song,
  mutedTrackIds: mutedProp,
  soloTrackIds: soloProp,
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

  const [loadingSamples, setLoadingSamples] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const toneRef = useRef<typeof ToneType | null>(null);
  // One sampler + gain per ROW (not per samplerKey) so two channels with the
  // same MIDI program still get independent mute/solo control.
  const samplersRef = useRef<Map<string, ToneType.Sampler>>(new Map());
  const gainsRef = useRef<Map<string, ToneType.Gain>>(new Map());
  const timerRef = useRef<number | null>(null);
  const rateRef = useRef(1);

  const audibleTrackIds = useMemo(
    () => getAudibleTrackIds(trackIds, mutedTrackIds, soloTrackIds),
    [trackIds, mutedTrackIds, soloTrackIds],
  );

  // Push gain changes live whenever mute/solo state shifts.
  useEffect(() => {
    for (const [id, gain] of gainsRef.current) {
      gain.gain.rampTo(audibleTrackIds.has(id) ? 0.9 : 0, 0.05);
    }
  }, [audibleTrackIds]);

  useEffect(() => () => stopAndCleanup(true), []);

  // Publish an engine-agnostic handle so a piano roll can read this transport's
  // playhead and scrub through it. getTime is the tick-derived musical clock, so
  // the roll and the transport time display never diverge.
  useEffect(() => {
    const ref = playerApiRef;
    if (!ref) return;
    const api: PlayerApi = {
      getTime: () => {
        const Tone = toneRef.current;
        return Tone ? musicalSeconds(Tone) : 0;
      },
      getDuration: () => duration,
      isPlaying: () => playing,
      seek: (seconds) => seek(seconds),
      setRate: (rate) => {
        const clamped = Math.min(1.5, Math.max(0.5, rate));
        rateRef.current = clamped;
        const Tone = toneRef.current;
        if (Tone && playing) Tone.Transport.bpm.value = BASE_BPM * clamped;
      },
      getRate: () => rateRef.current,
    };
    ref.current = api;
    return () => {
      if (ref.current === api) ref.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playerApiRef, duration, playing]);

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

  function stopAndCleanup(resetPosition: boolean) {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    const Tone = toneRef.current;
    if (Tone) {
      Tone.Transport.pause();
      Tone.Transport.cancel(0);
      for (const s of samplersRef.current.values()) {
        try { s.releaseAll(); } catch { /* noop */ }
      }
    }
    if (resetPosition && Tone) Tone.Transport.seconds = 0;
    if (resetPosition) setPosition(0);
    setPlaying(false);
  }

  async function ensureSamplers(Tone: typeof ToneType) {
    setLoadingSamples(true);
    try {
      // Per-row samplers; drop any whose row id no longer exists.
      const wanted = new Set(rows.map((r) => r.id));
      for (const [id, s] of samplersRef.current) {
        if (!wanted.has(id)) {
          s.disconnect();
          samplersRef.current.delete(id);
          gainsRef.current.get(id)?.disconnect();
          gainsRef.current.delete(id);
        }
      }
      const created: Array<Promise<unknown>> = [];
      for (const row of rows) {
        if (samplersRef.current.has(row.id)) continue;
        const gain = new Tone.Gain(audibleTrackIds.has(row.id) ? 0.9 : 0).toDestination();
        const sampler = makeSampler(Tone, row.roster).connect(gain);
        samplersRef.current.set(row.id, sampler);
        gainsRef.current.set(row.id, gain);
        created.push((sampler.loaded as unknown as Promise<unknown>) ?? Tone.loaded());
      }
      await Promise.all(created);
      await Tone.loaded();
    } finally {
      setLoadingSamples(false);
    }
  }

  async function togglePlayback() {
    if (playing) {
      stopAndCleanup(false);
      return;
    }
    const Tone = await loadTone();
    toneRef.current = Tone;
    await Tone.start();
    await ensureSamplers(Tone);

    // Clear any leftover scheduled events from a previous run. Pin the base
    // tempo so each note's seconds→ticks conversion is stable regardless of the
    // current playback rate; the rate is re-applied via bpm just before start.
    Tone.Transport.cancel(0);
    Tone.Transport.bpm.value = BASE_BPM;
    const start = position >= duration ? 0 : position;
    Tone.Transport.ticks = musicalSecondsToTicks(Tone, start);

    for (const row of rows) {
      const sampler = samplersRef.current.get(row.id);
      if (!sampler) continue;
      const gain = gainsRef.current.get(row.id);
      if (gain) gain.gain.value = audibleTrackIds.has(row.id) ? 0.9 : 0;

      for (const event of eventsByTrack[row.id] ?? []) {
        if (event.startSeconds + event.durationSeconds <= start) continue;
        const note = midiToName(event.pitch);
        const dur = Math.max(0.05, event.durationSeconds);
        const vel = Math.max(0.1, Math.min(1, event.velocity));
        // Schedule against the transport so cancel(0) actually clears it.
        Tone.Transport.schedule((time: number) => {
          try { sampler.triggerAttackRelease(note, dur, time, vel); } catch { /* skip */ }
        }, event.startSeconds);
      }
    }

    // Apply the selected speed just before playing (tick positions are already
    // fixed, so this only scales wall-clock rate, not the note timeline).
    Tone.Transport.bpm.value = BASE_BPM * rateRef.current;
    Tone.Transport.start();
    setPlaying(true);
    timerRef.current = window.setInterval(() => {
      const elapsed = musicalSeconds(Tone);
      if (elapsed >= duration) {
        stopAndCleanup(true);
        return;
      }
      setPosition(elapsed);
    }, 60);
  }

  function seek(value: number) {
    const next = Math.min(duration, Math.max(0, value));
    const wasPlaying = playing;
    if (wasPlaying) stopAndCleanup(false);
    setPosition(next);
    const Tone = toneRef.current;
    if (Tone) Tone.Transport.ticks = musicalSecondsToTicks(Tone, next);
  }

  return (
    <div className="track-mixer">
      <div className="mixer-transport">
        <button
          type="button"
          className="transport-button"
          onClick={togglePlayback}
          disabled={duration === 0 || loadingSamples}
        >
          {loadingSamples ? "Loading…" : playing ? "Stop" : "Play"}
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

function samplerKey(r: RosterItem): string {
  if (resolveIsDrum(r)) return "drums";
  return `prog_${resolveProgram(r)}`;
}

function makeSampler(Tone: typeof ToneType, r: RosterItem): ToneType.Sampler {
  if (resolveIsDrum(r)) {
    return new Tone.Sampler({
      urls: drumUrls(),
      baseUrl: `${FLUIDR3_BASE}percussion-mp3/`,
    });
  }
  const folder = folderForProgram(resolveProgram(r));
  return new Tone.Sampler({
    urls: melodicUrls(),
    baseUrl: `${FLUIDR3_BASE}${folder}-mp3/`,
  });
}

function buildRows(song: SongState): TrackRow[] {
  const rosterById = new Map(song.roster.map((item) => [item.id, item]));
  const events = buildTrackEvents(song);
  return Object.entries(song.parts).map(([partId]) => {
    const roster = rosterById.get(partId) ?? {
      id: partId, instrument: partId, is_drum: false,
      midi_program: 0, midi_range: [0, 127] as [number, number], role: "",
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
  const m = Math.floor(safe / 60);
  const s = Math.floor(safe % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
