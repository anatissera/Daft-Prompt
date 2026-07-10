"use client";

import { useEffect, useRef, useState } from "react";

// Renders MusicXML in the browser via OpenSheetMusicDisplay (no server engraver).
export default function ScoreViewer({ musicXmlUrl }: { musicXmlUrl: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");

  useEffect(() => {
    let cancelled = false;
    const host = ref.current;
    setStatus("loading");
    (async () => {
      const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");
      if (!host || cancelled) return;
      const osmd = new OpenSheetMusicDisplay(host, {
        autoResize: true,
        drawTitle: false,
      });
      const response = await fetch(musicXmlUrl);
      if (!response.ok) throw new Error(`score request failed (${response.status})`);
      const xml = await response.text();
      if (cancelled) return;
      await osmd.load(xml);
      osmd.render();
      if (!cancelled) setStatus("ready");
    })().catch(() => {
      if (!cancelled) setStatus("unavailable");
    });
    return () => {
      cancelled = true;
      if (host) host.innerHTML = "";
    };
  }, [musicXmlUrl, attempt]);

  return (
    <div className="score-paper">
      <span className="score-paper-corner score-paper-corner-tl" aria-hidden="true" />
      <span className="score-paper-corner score-paper-corner-tr" aria-hidden="true" />
      <span className="score-paper-corner score-paper-corner-bl" aria-hidden="true" />
      <span className="score-paper-corner score-paper-corner-br" aria-hidden="true" />
      {status === "loading" ? <p className="empty-note">Preparing score…</p> : null}
      {status === "unavailable" ? (
        <div className="empty-note" role="status">
          <p>Notation is unavailable. Playback and MIDI remain available.</p>
          <button type="button" className="artifact-link" onClick={() => setAttempt((value) => value + 1)}>
            Retry score
          </button>
        </div>
      ) : null}
      <div ref={ref} className="score-paper-canvas" hidden={status !== "ready"} />
    </div>
  );
}
