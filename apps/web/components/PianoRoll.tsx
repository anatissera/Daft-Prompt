"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import type { SongState } from "@/lib/types";
import type { PlayerApi } from "@/lib/playerApi";
import { instrumentColor } from "@/lib/colors";
import { buildTrackEvents } from "@/lib/trackMixerLogic.mjs";
import {
  DEFAULT_PX_PER_SEC,
  barLinesInView,
  buildKeyboardKeys,
  clampPitch,
  isNoteActive,
  isNoteVisible,
  keyGeometry,
  noteRectY,
  whiteKeyLetter,
  type KeyboardGeometry,
} from "@/lib/pianoRollLayout.mjs";

interface RollNote {
  trackId: string;
  color: string;
  pitch: number;
  startSeconds: number;
  durationSeconds: number;
  velocity: number;
}

interface PianoRollProps {
  song: SongState;
  audibleTrackIds: Set<string>;
  playerApiRef: MutableRefObject<PlayerApi | null>;
}

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5];
const MIN_KEYBOARD_H = 54;
const MAX_KEYBOARD_H = 104;

export default function PianoRoll({ song, audibleTrackIds, playerApiRef }: PianoRollProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);

  const [rate, setRate] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);

  // Flat, pre-coloured note list — rebuilt only when the song changes.
  const notes = useMemo<RollNote[]>(() => {
    const byTrack = buildTrackEvents(song);
    const flat: RollNote[] = [];
    for (const [trackId, events] of Object.entries(byTrack)) {
      const color = instrumentColor(trackId);
      for (const e of events) {
        flat.push({
          trackId,
          color,
          pitch: e.pitch,
          startSeconds: e.startSeconds,
          durationSeconds: e.durationSeconds,
          velocity: e.velocity,
        });
      }
    }
    return flat;
  }, [song]);

  const keyboard = useMemo(() => buildKeyboardKeys(), []);

  // Audible set and header read live inside the animation loop via refs so the
  // loop never has to restart when mute/solo toggles.
  const audibleRef = useRef(audibleTrackIds);
  audibleRef.current = audibleTrackIds;
  const notesRef = useRef(notes);
  notesRef.current = notes;
  const headerRef = useRef(song.header);
  headerRef.current = song.header;

  // Cache keyboard pixel geometry keyed by width (88 keys, cheap but no reason
  // to recompute every frame).
  const geomCache = useRef<{ width: number; geo: KeyboardGeometry } | null>(null);
  const geometryFor = useCallback(
    (width: number) => {
      const cached = geomCache.current;
      if (cached && Math.abs(cached.width - width) < 0.5) return cached.geo;
      const geo = keyGeometry(keyboard, width);
      geomCache.current = { width, geo };
      return geo;
    },
    [keyboard],
  );

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth;
    const cssH = canvas.clientHeight;
    if (cssW === 0 || cssH === 0) return;
    if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const keyboardH = Math.min(MAX_KEYBOARD_H, Math.max(MIN_KEYBOARD_H, cssH * 0.16));
    const hitLineY = cssH - keyboardH;
    const rollH = hitLineY;
    // Show roughly 3.2 seconds of lookahead, scaling with the roll height.
    const pxPerSec = Math.max(70, Math.min(DEFAULT_PX_PER_SEC, rollH / 3.2));
    const geo = geometryFor(cssW);

    const api = playerApiRef.current;
    const t = api ? api.getTime() : 0;
    const audible = audibleRef.current;
    const allNotes = notesRef.current;
    const header = headerRef.current;

    // --- roll background ---
    ctx.clearRect(0, 0, cssW, cssH);
    const bg = ctx.createLinearGradient(0, 0, 0, rollH);
    bg.addColorStop(0, "#05070d");
    bg.addColorStop(1, "#0a1120");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, cssW, rollH);

    // --- bar lines + numbers ---
    const bars = barLinesInView(header, t, hitLineY, pxPerSec, header.num_bars);
    ctx.font = "10px 'Space Mono', ui-monospace, monospace";
    ctx.textBaseline = "alphabetic";
    for (const line of bars) {
      if (line.y < 0 || line.y > rollH) continue;
      ctx.strokeStyle = "rgba(130,134,154,0.16)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, line.y);
      ctx.lineTo(cssW, line.y);
      ctx.stroke();
      ctx.fillStyle = "rgba(169,170,184,0.5)";
      ctx.fillText(String(line.bar + 1), 6, line.y - 4);
    }

    // --- octave guide lines (faint verticals at every C) ---
    ctx.strokeStyle = "rgba(130,134,154,0.08)";
    ctx.lineWidth = 1;
    for (const key of geo.keys) {
      if (key.black || key.midi % 12 !== 0) continue;
      ctx.beginPath();
      ctx.moveTo(key.x, 0);
      ctx.lineTo(key.x, hitLineY);
      ctx.stroke();
    }

    // --- falling notes ---
    const activeKeys = new Map<number, string>();
    for (const note of allNotes) {
      if (!audible.has(note.trackId)) continue;
      if (isNoteActive(note.startSeconds, note.durationSeconds, t)) {
        activeKeys.set(clampPitch(note.pitch), note.color);
      }
      if (!isNoteVisible(note.startSeconds, note.durationSeconds, t, hitLineY, pxPerSec)) continue;
      const col = geo.byMidi.get(clampPitch(note.pitch));
      if (!col) continue;
      const rect = noteRectY(note.startSeconds, note.durationSeconds, t, hitLineY, pxPerSec);
      const top = Math.max(0, rect.top);
      const bottom = Math.min(hitLineY, rect.bottom);
      const h = Math.max(2, bottom - top);
      const active = rect.bottom >= hitLineY - 1 && rect.top <= hitLineY;
      const pad = col.black ? 1 : 1.5;
      // Louder notes read brighter; the one crossing the hit line glows.
      const baseAlpha = 0.5 + 0.45 * Math.max(0, Math.min(1, note.velocity));
      ctx.save();
      if (active) {
        ctx.shadowColor = note.color;
        ctx.shadowBlur = 14;
      }
      drawRoundedRect(ctx, col.x + pad, top, Math.max(2, col.width - pad * 2), h, 3);
      ctx.fillStyle = note.color;
      ctx.globalAlpha = active ? Math.min(1, baseAlpha + 0.25) : baseAlpha;
      ctx.fill();
      ctx.restore();
      if (active) {
        drawRoundedRect(ctx, col.x + pad, top, Math.max(2, col.width - pad * 2), h, 3);
        ctx.strokeStyle = "rgba(255,255,255,0.85)";
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    // --- hit line (gold LED) ---
    ctx.save();
    ctx.shadowColor = "rgba(243,196,90,0.7)";
    ctx.shadowBlur = 10;
    ctx.strokeStyle = "#f3c45a";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, hitLineY);
    ctx.lineTo(cssW, hitLineY);
    ctx.stroke();
    ctx.restore();

    // --- keyboard ---
    drawKeyboard(ctx, geo, hitLineY, keyboardH, cssW, activeKeys);

    // --- caption ---
    ctx.fillStyle = "rgba(243,196,90,0.85)";
    ctx.font = "11px 'Space Mono', ui-monospace, monospace";
    ctx.textAlign = "right";
    ctx.fillText(`${header.key} · ${Math.round(header.tempo_bpm * rate)} BPM`, cssW - 8, 16);
    ctx.textAlign = "left";
  }, [geometryFor, playerApiRef, rate]);

  // Continuous animation loop — cheap for a few thousand notes and keeps play,
  // pause, seek and mute/solo all reflected without restart plumbing.
  useEffect(() => {
    const loop = () => {
      draw();
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [draw]);

  // Track fullscreen changes (including Esc) to keep the toggle label honest.
  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === stageRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const handleSpeed = useCallback(
    (value: number) => {
      setRate(value);
      playerApiRef.current?.setRate(value);
    },
    [playerApiRef],
  );

  const toggleFullscreen = useCallback(() => {
    const el = stageRef.current;
    if (!el) return;
    if (document.fullscreenElement === el) void document.exitFullscreen();
    else void el.requestFullscreen?.();
  }, []);

  // Click in the roll area scrubs to the time under the cursor.
  const handleCanvasClick = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      const api = playerApiRef.current;
      if (!canvas || !api) return;
      const rect = canvas.getBoundingClientRect();
      const y = event.clientY - rect.top;
      const cssH = canvas.clientHeight;
      const keyboardH = Math.min(MAX_KEYBOARD_H, Math.max(MIN_KEYBOARD_H, cssH * 0.16));
      const hitLineY = cssH - keyboardH;
      if (y > hitLineY) return; // ignore clicks on the keyboard
      const pxPerSec = Math.max(70, Math.min(DEFAULT_PX_PER_SEC, hitLineY / 3.2));
      const t = api.getTime();
      const target = t + (hitLineY - y) / pxPerSec;
      api.seek(Math.max(0, Math.min(api.getDuration(), target)));
    },
    [playerApiRef],
  );

  const hasNotes = notes.length > 0;

  return (
    <div className="piano-stage" ref={stageRef}>
      <div className="piano-stage-bar">
        <span className="piano-stage-eyebrow">Piano roll</span>
        <div className="piano-stage-controls">
          <div className="piano-speed" role="group" aria-label="Playback speed">
            {SPEEDS.map((value) => (
              <button
                key={value}
                type="button"
                className={`piano-speed-btn ${value === rate ? "is-active" : ""}`}
                onClick={() => handleSpeed(value)}
                aria-pressed={value === rate}
              >
                {value === 1 ? "1×" : `${value}×`}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="piano-fs-btn"
            onClick={toggleFullscreen}
            aria-label={fullscreen ? "Exit fullscreen" : "Enter fullscreen"}
            title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
          >
            {fullscreen ? "⤡ Exit" : "⤢ Full"}
          </button>
        </div>
      </div>
      <div className="piano-stage-canvas-wrap" ref={containerRef}>
        {hasNotes ? (
          <canvas
            ref={canvasRef}
            className="piano-stage-canvas"
            onClick={handleCanvasClick}
            aria-label="Falling-notes piano visualization"
          />
        ) : (
          <p className="piano-stage-empty">No notes to visualize.</p>
        )}
      </div>
    </div>
  );
}

function drawRoundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  if (typeof ctx.roundRect === "function") {
    ctx.roundRect(x, y, w, h, radius);
    return;
  }
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

function drawKeyboard(
  ctx: CanvasRenderingContext2D,
  geo: KeyboardGeometry,
  top: number,
  height: number,
  width: number,
  activeKeys: Map<number, string>,
) {
  const showLetters = geo.whiteWidth > 9;
  // White keys first so black keys overlay them.
  for (const key of geo.keys) {
    if (key.black) continue;
    const lit = activeKeys.get(key.midi);
    ctx.fillStyle = lit ?? "#e9e6da";
    ctx.fillRect(key.x, top, key.width, height);
    ctx.strokeStyle = "rgba(0,0,0,0.35)";
    ctx.lineWidth = 1;
    ctx.strokeRect(key.x + 0.5, top, key.width, height);
    if (showLetters && !lit) {
      ctx.fillStyle = "rgba(10,7,16,0.45)";
      ctx.font = "8px 'Space Mono', ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.fillText(whiteKeyLetter(key.midi), key.centerX, top + height - 5);
      ctx.textAlign = "left";
    }
  }
  const blackH = height * 0.62;
  for (const key of geo.keys) {
    if (!key.black) continue;
    const lit = activeKeys.get(key.midi);
    ctx.fillStyle = lit ?? "#11131c";
    ctx.fillRect(key.x, top, key.width, blackH);
    if (lit) {
      ctx.strokeStyle = "rgba(255,255,255,0.5)";
      ctx.lineWidth = 1;
      ctx.strokeRect(key.x + 0.5, top + 0.5, key.width - 1, blackH - 1);
    }
  }
  // Gold sill under the keys.
  ctx.fillStyle = "rgba(243,196,90,0.25)";
  ctx.fillRect(0, top, width, 2);
}
