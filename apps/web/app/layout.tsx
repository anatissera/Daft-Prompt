import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Daft Prompt",
  description: "Chat with a music agent. Attach audio for analysis or ask it to compose a sketch.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Audiowide&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Orbitron:wght@500;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        {/* Hidden SVG: turbulence filter that displaces the flames so their
            edges shimmer organically instead of looking like blurred blobs. */}
        <svg width="0" height="0" aria-hidden="true" style={{ position: "absolute" }}>
          <defs>
            <filter id="fire-distort" x="-20%" y="-20%" width="140%" height="140%">
              <feTurbulence type="fractalNoise" baseFrequency="0.012 0.04" numOctaves="2" seed="7">
                <animate attributeName="baseFrequency" dur="9s" values="0.012 0.04; 0.018 0.06; 0.012 0.04" repeatCount="indefinite" />
              </feTurbulence>
              <feDisplacementMap in="SourceGraphic" scale="36" xChannelSelector="R" yChannelSelector="G" />
            </filter>
          </defs>
        </svg>

        {/* Fire stage: each span is a tongue of flame with its own delay. */}
        <div className="fire-stage" aria-hidden="true">
          <div className="fire-haze" />
          <div className="fire-layer fire-layer-back">
            <span /><span /><span /><span /><span /><span />
          </div>
          <div className="fire-layer fire-layer-front">
            <span /><span /><span /><span /><span /><span /><span />
          </div>
          <div className="fire-embers">
            <span /><span /><span /><span /><span /><span /><span /><span />
          </div>
        </div>

        {children}
      </body>
    </html>
  );
}
