"use client";

import { useMemo } from "react";
import type { SongState } from "@/lib/types";
import { instrumentColor } from "@/lib/colors";
import { buildTrackEvents, getSongDurationSeconds } from "@/lib/trackMixerLogic.mjs";
import { clampPitch, isBlackKey, secondsPerBar } from "@/lib/pianoRollLayout.mjs";

interface PianoRollProps {
  song: SongState;
  audibleTrackIds: Set<string>;
}

interface RollNote {
  trackId: string;
  pitch: number;
  startSeconds: number;
  durationSeconds: number;
  velocity: number;
}

const WIDTH = 960;
const HEIGHT = 238;
const LABEL_WIDTH = 42;
const ROLL_HEIGHT = 204;
const KEYBOARD_LOW = 21;
const KEYBOARD_HIGH = 108;

export default function PianoRoll({ song, audibleTrackIds }: PianoRollProps) {
  const notes = useMemo<RollNote[]>(() => {
    const eventsByTrack = buildTrackEvents(song);
    return Object.entries(eventsByTrack).flatMap(([trackId, events]) => (
      events.map((event) => ({ trackId, ...event }))
    ));
  }, [song]);

  const duration = Math.max(
    getSongDurationSeconds(song),
    secondsPerBar(song.header) * song.header.num_bars,
    0.01,
  );
  const pitchRange = useMemo(() => {
    if (notes.length === 0) return { low: 48, high: 84 };
    const pitches = notes.map((note) => clampPitch(note.pitch));
    return {
      low: Math.max(KEYBOARD_LOW, Math.min(...pitches) - 2),
      high: Math.min(KEYBOARD_HIGH, Math.max(...pitches) + 2),
    };
  }, [notes]);
  const pitchCount = pitchRange.high - pitchRange.low + 1;
  const pitchHeight = ROLL_HEIGHT / pitchCount;
  const plotWidth = WIDTH - LABEL_WIDTH;
  const bars = Math.max(1, song.header.num_bars);
  const spBar = secondsPerBar(song.header);

  function xForTime(seconds: number) {
    return LABEL_WIDTH + (seconds / duration) * plotWidth;
  }

  function yForPitch(pitch: number) {
    const clamped = clampPitch(pitch, pitchRange.low, pitchRange.high);
    return (pitchRange.high - clamped) * pitchHeight;
  }

  return (
    <section className="piano-roll" aria-label="Piano roll">
      <header className="piano-roll-header">
        <div>
          <p className="piano-roll-eyebrow">Piano roll</p>
          <h3>Generated MIDI</h3>
        </div>
        <span>{notes.length} notes · {formatDuration(duration)}</span>
      </header>
      {notes.length === 0 ? (
        <p className="piano-roll-empty">No notes to visualize.</p>
      ) : (
        <div className="piano-roll-scroll">
          <svg className="piano-roll-svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Static piano roll of generated notes">
            <rect x={0} y={0} width={WIDTH} height={ROLL_HEIGHT} className="piano-roll-bg" />
            {Array.from({ length: pitchCount }, (_, index) => {
              const pitch = pitchRange.high - index;
              const y = index * pitchHeight;
              return (
                <g key={pitch}>
                  <rect
                    x={LABEL_WIDTH}
                    y={y}
                    width={plotWidth}
                    height={pitchHeight}
                    className={isBlackKey(pitch) ? "piano-roll-row-black" : "piano-roll-row-white"}
                  />
                  {pitch % 12 === 0 ? (
                    <text x={8} y={y + pitchHeight * 0.72} className="piano-roll-label">
                      {noteName(pitch)}
                    </text>
                  ) : null}
                </g>
              );
            })}
            {Array.from({ length: bars + 1 }, (_, bar) => {
              const x = xForTime(Math.min(duration, bar * spBar));
              return (
                <g key={bar}>
                  <line x1={x} x2={x} y1={0} y2={ROLL_HEIGHT} className={bar % 4 === 0 ? "piano-roll-bar-strong" : "piano-roll-bar"} />
                  {bar < bars ? (
                    <text x={x + 4} y={ROLL_HEIGHT + 18} className="piano-roll-bar-label">
                      {bar + 1}
                    </text>
                  ) : null}
                </g>
              );
            })}
            {notes.map((note, index) => {
              const audible = audibleTrackIds.has(note.trackId);
              const y = yForPitch(note.pitch) + 1;
              const x = xForTime(note.startSeconds);
              const width = Math.max(4, (note.durationSeconds / duration) * plotWidth);
              return (
                <rect
                  key={`${note.trackId}-${note.startSeconds}-${note.pitch}-${index}`}
                  x={x}
                  y={y}
                  width={width}
                  height={Math.max(3, pitchHeight - 2)}
                  rx={3}
                  className={audible ? "piano-roll-note" : "piano-roll-note piano-roll-note-muted"}
                  style={{ fill: instrumentColor(note.trackId), opacity: audible ? 0.55 + note.velocity * 0.4 : 0.16 }}
                />
              );
            })}
            <rect x={LABEL_WIDTH} y={ROLL_HEIGHT + 26} width={plotWidth} height={10} className="piano-roll-timeline" />
          </svg>
        </div>
      )}
    </section>
  );
}

function noteName(pitch: number): string {
  const names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  return `${names[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}

function formatDuration(value: number): string {
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
