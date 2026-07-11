"use client";

import { useEffect, useRef } from "react";

/** Rotary volume knob controlled with the mouse wheel. 0..1 gain, default 1.
 *  The wheel listener is attached natively with `passive: false` because
 *  React's synthetic onWheel is passive and can't preventDefault — without
 *  it every volume tick would also scroll the chat. */
export default function VolumeKnob({
  gain,
  onChange,
  label,
}: {
  gain: number;
  onChange: (gain: number) => void;
  label?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const gainRef = useRef(gain);
  gainRef.current = gain;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const step = 0.05;
      const next = Math.max(0, Math.min(1, gainRef.current + (e.deltaY < 0 ? step : -step)));
      onChangeRef.current(Math.round(next * 100) / 100);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const pct = Math.round(gain * 100);
  // Pointer sweeps -135° (0%) → +135° (100%), like a hardware pot.
  const angle = -135 + 270 * gain;
  return (
    <span
      ref={ref}
      className="volume-knob"
      role="slider"
      aria-label={label ? `${label} volume` : "volume"}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      title={`Vol ${pct}% (rueda del mouse)`}
      data-dimmed={gain < 1 ? "true" : undefined}
    >
      <span className="volume-knob-pointer" style={{ transform: `rotate(${angle}deg)` }} />
    </span>
  );
}
