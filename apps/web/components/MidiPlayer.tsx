"use client";

import { useEffect } from "react";

// `html-midi-player` registers the <midi-player> custom element on import.
// Typed as `any` so we don't need JSX intrinsic-element declarations.
const MidiPlayerEl = "midi-player" as unknown as React.ComponentType<{
  src: string;
  "sound-font"?: string;
  style?: React.CSSProperties;
}>;

const SOUND_FONT =
  "https://storage.googleapis.com/magentadata/js/soundfonts/sgm_plus";

export default function MidiPlayer({ midiUrl }: { midiUrl: string }) {
  useEffect(() => {
    import("html-midi-player");
  }, []);

  return (
    <MidiPlayerEl src={midiUrl} sound-font={SOUND_FONT} style={{ width: "100%" }} />
  );
}
