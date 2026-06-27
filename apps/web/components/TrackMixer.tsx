"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type * as ToneType from "tone";
import type { RosterItem, SongState } from "@/lib/types";
import { instrumentColor } from "@/lib/colors";
import {
  buildTrackEvents,
  getAudibleTrackIds,
  getSongDurationSeconds,
  type TrackEvent,
} from "@/lib/trackMixerLogic.mjs";
import { FLUIDR3_BASE, folderForProgram, inferProgramFromName, isDrumByName, midiToName } from "@/lib/gmInstruments";

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

// Lazy import keeps Tone.js out of the initial bundle.
async function loadTone(): Promise<typeof ToneType> {
  return (await import("tone")) as unknown as typeof ToneType;
}

// 5 sparse base notes give Tone.Sampler enough anchors to pitch-shift smoothly.
const MELODIC_ANCHORS = ["C2", "C3", "C4", "C5", "C6"];
// FluidR3 percussion folder uses letter-note names mapped to drum keys 35-81.
const DRUM_KEYS: number[] = [];
for (let n = 35; n <= 81; n++) DRUM_KEYS.push(n);

function melodicUrls(): Record<string, string> {
  const urls: Record<string, string> = {};
  for (const n of MELODIC_ANCHORS) urls[n] = `${n}.mp3`;
  return urls;
}

function drumUrls(): Record<string, string> {
  const urls: Record<string, string> = {};
  for (const k of DRUM_KEYS) urls[midiToName(k)] = `${midiToName(k)}.mp3`;
  return urls;
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

  const [loadingSamples, setLoadingSamples] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const startedAtRef = useRef(0);
  const offsetRef = useRef(0);
  const samplersRef = useRef<Map<string, ToneType.Sampler>>(new Map());
  const gainsRef = useRef<Map<string, ToneType.Gain>>(new Map());
  const timerRef = useRef<number | null>(null);
  const stopTimeoutRef = useRef<number | null>(null);

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

  useEffect(() => () => stopAndCleanup(), []);

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

  function stopAndCleanup() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (stopTimeoutRef.current !== null) {
      window.clearTimeout(stopTimeoutRef.current);
      stopTimeoutRef.current = null;
    }
    for (const s of samplersRef.current.values()) {
      try { s.releaseAll(); } catch { /* noop */ }
    }
    setPlaying(false);
  }

  async function ensureSamplers(Tone: typeof ToneType) {
    setLoadingSamples(true);
    try {
      const wanted = new Set<string>();
      for (const row of rows) wanted.add(samplerKey(row.roster));

      const created: Array<Promise<unknown>> = [];
      for (const row of rows) {
        const key = samplerKey(row.roster);
        if (samplersRef.current.has(key)) continue;
        const gain = new Tone.Gain(audibleTrackIds.has(row.id) ? 0.9 : 0).toDestination();
        const sampler = makeSampler(Tone, row.roster).connect(gain);
        samplersRef.current.set(key, sampler);
        gainsRef.current.set(row.id, gain);
        created.push((sampler.loaded as unknown as Promise<unknown>) ?? Tone.loaded());
      }
      // Drop samplers no longer in use (kept simple — usually song is stable).
      for (const [key, s] of samplersRef.current) {
        if (!wanted.has(key)) {
          s.disconnect();
          samplersRef.current.delete(key);
        }
      }
      await Promise.all(created);
      await Tone.loaded();
    } finally {
      setLoadingSamples(false);
    }
  }

  async function togglePlayback() {
    if (playing) {
      stopAndCleanup();
      return;
    }
    const Tone = await loadTone();
    await Tone.start();
    await ensureSamplers(Tone);

    const start = position >= duration ? 0 : position;
    offsetRef.current = start;
    startedAtRef.current = Tone.now() - start;

    const baseTime = Tone.now() + 0.05;
    for (const row of rows) {
      const key = samplerKey(row.roster);
      const sampler = samplersRef.current.get(key);
      if (!sampler) continue;
      const gain = gainsRef.current.get(row.id);
      if (gain) gain.gain.value = audibleTrackIds.has(row.id) ? 0.9 : 0;

      for (const event of eventsByTrack[row.id] ?? []) {
        const startOffset = event.startSeconds - start;
        if (event.startSeconds + event.durationSeconds <= start) continue;
        if (startOffset < 0) continue;
        const noteName = midiToName(event.pitch);
        try {
          sampler.triggerAttackRelease(
            noteName,
            Math.max(0.05, event.durationSeconds),
            baseTime + startOffset,
            Math.max(0.1, Math.min(1, event.velocity)),
          );
        } catch {
          // Sampler may reject out-of-range notes; skip silently.
        }
      }
    }

    setPlaying(true);
    timerRef.current = window.setInterval(() => {
      const elapsed = Tone.now() - startedAtRef.current;
      if (elapsed >= duration) {
        setPosition(duration);
        stopAndCleanup();
        setPosition(0);
        return;
      }
      setPosition(elapsed);
    }, 60);
  }

  function seek(value: number) {
    const next = Math.min(duration, Math.max(0, value));
    const wasPlaying = playing;
    if (wasPlaying) stopAndCleanup();
    setPosition(next);
    offsetRef.current = next;
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

// Pick a GM program for an instrument, trusting the director's midi_program
// only when it's non-zero (0 = piano default, which the LLM hands back even
// for "flute" / "viola"). Otherwise infer from the human name.
function resolveProgram(r: RosterItem): number {
  if (r.midi_program && r.midi_program > 0) return r.midi_program;
  const inferred = inferProgramFromName(r.instrument || r.role || r.id);
  return inferred ?? 0;
}

function resolveIsDrum(r: RosterItem): boolean {
  if (r.is_drum) return true;
  return isDrumByName(r.instrument || r.role || r.id);
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
