"use client";

import { useEffect, useRef } from "react";

// Renders MusicXML in the browser via OpenSheetMusicDisplay (no server engraver).
export default function ScoreViewer({ musicXmlUrl }: { musicXmlUrl: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    const host = ref.current;
    (async () => {
      const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");
      if (!host || cancelled) return;
      const osmd = new OpenSheetMusicDisplay(host, {
        autoResize: true,
        drawTitle: false,
      });
      try {
        const res = await fetch(musicXmlUrl);
        if (!res.ok) throw new Error(`score fetch failed: ${res.status}`);
        const xml = await res.text();
        if (cancelled) return;
        await osmd.load(xml);
        osmd.render();
      } catch {
        // Transient network hiccups (dev-server restart, flaky mobile link)
        // shouldn't crash the page with a runtime overlay.
        if (!cancelled && host) {
          host.textContent = "No se pudo cargar la partitura — recargá la página.";
        }
      }
    })();
    return () => {
      cancelled = true;
      if (host) host.innerHTML = "";
    };
  }, [musicXmlUrl]);

  return (
    <div className="score-paper">
      <span className="score-paper-corner score-paper-corner-tl" aria-hidden="true" />
      <span className="score-paper-corner score-paper-corner-tr" aria-hidden="true" />
      <span className="score-paper-corner score-paper-corner-bl" aria-hidden="true" />
      <span className="score-paper-corner score-paper-corner-br" aria-hidden="true" />
      <div ref={ref} className="score-paper-canvas" />
    </div>
  );
}
