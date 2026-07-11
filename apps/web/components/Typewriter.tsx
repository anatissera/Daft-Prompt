"use client";

import { useEffect, useState } from "react";

interface TypewriterProps {
  text: string;
  charsPerTick?: number;
  tickMs?: number;
}

/** Reveals `text` character by character so each new assistant message
 *  appears as if it's being typed out live. Reset when `text` changes. */
export default function Typewriter({ text, charsPerTick = 3, tickMs = 18 }: TypewriterProps) {
  const [shown, setShown] = useState(0);

  useEffect(() => {
    setShown(0);
  }, [text]);

  useEffect(() => {
    if (shown >= text.length) return;
    const id = setInterval(() => {
      setShown((s) => Math.min(text.length, s + charsPerTick));
    }, tickMs);
    return () => clearInterval(id);
  }, [shown, text, charsPerTick, tickMs]);

  const done = shown >= text.length;
  return (
    <>
      {text.slice(0, shown)}
      <span className={done ? "type-caret type-caret-done" : "type-caret"} aria-hidden="true" />
    </>
  );
}
