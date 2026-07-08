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
import { makeSynth, resolveSynthPreset } from "@/lib/synthPresets";

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

// Dense anchor set — three natural notes per octave (C, F, A) across the
// playable range. FluidR3 ships all of these for every melodic patch, so
// Tone.Sampler never has to pitch-shift more than ~2 semitones from an
// anchor. With the old one-per-octave set (C2..C6) the sampler was
// stretching up to ~6 semitones on notes in the middle of each octave; on
// long-sustain patches (electric guitar jazz, pads) that produced the
// bell-like "8-bit" timbre the user reported.
const MELODIC_ANCHORS = [
  "A0",
  "C2", "F2", "A2",
  "C3", "F3", "A3",
  "C4", "F4", "A4",
  "C5", "F5", "A5",
  "C6", "F6", "A6",
];
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
  // FluidR3's `percussion-mp3/` folder was removed from the gleitz CDN, so
  // every load 404'd and crashed Tone.Sampler at construction time. Instead
  // point the drum sampler at `synth_drum-mp3/`, which ships a single B1.mp3
  // Tone.Sampler will pitch-shift to every drum key. Result: no external
  // assets, no 404s, one shared synth-drum timbre for the whole kit.
  return { B1: "B1.mp3" };
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
  const toneRef = useRef<typeof ToneType | null>(null);
  // One instrument + gain per ROW (not per samplerKey) so two channels with
  // the same MIDI program still get independent mute/solo control. Values can
  // be a Tone.Sampler (FluidR3 patch) OR a Tone.Synth preset — both expose
  // triggerAttackRelease with the same signature, so scheduling stays uniform.
  const samplersRef = useRef<Map<string, ToneType.Sampler | ToneType.PolySynth | ToneType.MonoSynth>>(new Map());
  const gainsRef = useRef<Map<string, ToneType.Gain>>(new Map());
  const timerRef = useRef<number | null>(null);

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
        // Sampler and PolySynth expose releaseAll; MonoSynth doesn't (single
        // voice), and triggerRelease with no args cuts its held note.
        try {
          if ("releaseAll" in s) (s as { releaseAll: () => void }).releaseAll();
          else (s as ToneType.MonoSynth).triggerRelease();
        } catch { /* noop */ }
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
        // Sampler exposes a `.loaded` Promise for async sample-buffer fetch;
        // Tone.Synth is ready synchronously, so fall through to Tone.loaded().
        const loadedProm = ("loaded" in sampler ? (sampler as ToneType.Sampler).loaded : undefined) as
          | Promise<unknown>
          | undefined;
        created.push(loadedProm ?? Tone.loaded());
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

    // Clear any leftover scheduled events from a previous run.
    Tone.Transport.cancel(0);
    const start = position >= duration ? 0 : position;
    Tone.Transport.seconds = start;

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

    Tone.Transport.start();
    setPlaying(true);
    timerRef.current = window.setInterval(() => {
      const elapsed = Tone.Transport.seconds;
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
    if (Tone) Tone.Transport.seconds = next;
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

function makeSampler(
  Tone: typeof ToneType,
  r: RosterItem,
): ToneType.Sampler | ToneType.PolySynth | ToneType.MonoSynth {
  // First: does the roster item describe a modern-EDM timbre the FluidR3 GM
  // patches can't render (supersaw lead, sub bass, pluck, warm pad)? If yes,
  // route through a Tone.Synth preset. Drums always stay on the drum sampler.
  if (!resolveIsDrum(r)) {
    const preset = resolveSynthPreset(r);
    if (preset) return makeSynth(Tone, preset);
  }
  // onerror keeps a missing sample from throwing at Sampler construction, so
  // one 404 (e.g. if a folder gets moved on the CDN again) doesn't take the
  // whole player down. The Sampler stays usable with whatever samples did load.
  const onerror = (err: Error) => {
    // eslint-disable-next-line no-console
    console.warn("Sampler load error (continuing without it):", err);
  };
  if (resolveIsDrum(r)) {
    return new Tone.Sampler({
      urls: drumUrls(),
      baseUrl: `${FLUIDR3_BASE}synth_drum-mp3/`,
      onerror,
    });
  }
  const folder = folderForProgram(resolveProgram(r));
  return new Tone.Sampler({
    urls: melodicUrls(),
    baseUrl: `${FLUIDR3_BASE}${folder}-mp3/`,
    onerror,
  });
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
