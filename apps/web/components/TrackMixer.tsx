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
}

// Lazy import keeps Tone.js out of the initial bundle.
async function loadTone(): Promise<typeof ToneType> {
  return (await import("tone")) as unknown as typeof ToneType;
}

type LocalVoice = ToneType.PolySynth<ToneType.Synth>;

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

  const [preparingPlayback, setPreparingPlayback] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const toneRef = useRef<typeof ToneType | null>(null);
  // One sampler + gain per ROW (not per samplerKey) so two channels with the
  // same MIDI program still get independent mute/solo control.
  const voicesRef = useRef<Map<string, LocalVoice>>(new Map());
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
      for (const voice of voicesRef.current.values()) {
        try { voice.releaseAll(); } catch { /* noop */ }
      }
    }
    if (resetPosition && Tone) Tone.Transport.seconds = 0;
    if (resetPosition) setPosition(0);
    setPlaying(false);
  }

  function ensureVoices(Tone: typeof ToneType) {
    setPreparingPlayback(true);
    try {
      // Per-row local voices; drop any whose row id no longer exists.
      const wanted = new Set(rows.map((r) => r.id));
      for (const [id, voice] of voicesRef.current) {
        if (!wanted.has(id)) {
          voice.dispose();
          voicesRef.current.delete(id);
          gainsRef.current.get(id)?.disconnect();
          gainsRef.current.delete(id);
        }
      }
      for (const row of rows) {
        if (voicesRef.current.has(row.id)) continue;
        const gain = new Tone.Gain(audibleTrackIds.has(row.id) ? 0.9 : 0).toDestination();
        const voice = makeLocalVoice(Tone, row.roster).connect(gain);
        voicesRef.current.set(row.id, voice);
        gainsRef.current.set(row.id, gain);
      }
    } finally {
      setPreparingPlayback(false);
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
    ensureVoices(Tone);

    // Clear any leftover scheduled events from a previous run.
    Tone.Transport.cancel(0);
    const start = position >= duration ? 0 : position;
    Tone.Transport.seconds = start;

    for (const row of rows) {
      const voice = voicesRef.current.get(row.id);
      if (!voice) continue;
      const gain = gainsRef.current.get(row.id);
      if (gain) gain.gain.value = audibleTrackIds.has(row.id) ? 0.9 : 0;

      for (const event of eventsByTrack[row.id] ?? []) {
        if (event.startSeconds + event.durationSeconds <= start) continue;
        const note = midiToName(event.pitch);
        const dur = Math.max(0.05, event.durationSeconds);
        const vel = Math.max(0.1, Math.min(1, event.velocity));
        // Schedule against the transport so cancel(0) actually clears it.
        Tone.Transport.schedule((time: number) => {
          try { voice.triggerAttackRelease(note, dur, time, vel); } catch { /* skip */ }
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
          disabled={duration === 0 || preparingPlayback}
        >
          {preparingPlayback ? "Preparing…" : playing ? "Stop" : "Play"}
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

function makeLocalVoice(Tone: typeof ToneType, roster: RosterItem): LocalVoice {
  const isDrum = resolveIsDrum(roster);
  const program = resolveProgram(roster);
  const oscillator = isDrum
    ? "sine"
    : program >= 80 && program <= 87
      ? "square"
      : program >= 29 && program <= 31
        ? "sawtooth"
        : program >= 24 && program <= 28
          ? "triangle"
          : "sine";
  return new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: oscillator },
    envelope: isDrum
      ? { attack: 0.001, decay: 0.08, sustain: 0, release: 0.05 }
      : { attack: 0.01, decay: 0.12, sustain: 0.35, release: 0.25 },
    volume: isDrum ? -5 : -9,
  });
}

function buildRows(song: SongState): TrackRow[] {
  const rosterById = new Map(song.roster.map((item) => [item.id, item]));
  const events = buildTrackEvents(song);
  return Object.entries(song.parts).map(([partId]) => {
    const roster = rosterById.get(partId) ?? {
      id: partId, instrument: partId, is_drum: false,
      midi_program: 0, midi_range: [0, 127] as [number, number], role: "", playing_style: "",
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
