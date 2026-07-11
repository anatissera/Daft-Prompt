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
      const xml = await fetch(musicXmlUrl).then((r) => r.text());
      if (cancelled) return;
      await osmd.load(xml);
      osmd.render();
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
