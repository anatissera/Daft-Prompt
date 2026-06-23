import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Multi-agent Band",
  description: "Describe a style — a band of LLM agents composes a song for it.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          margin: 0,
          background: "#0b0b10",
          color: "#eaeaf0",
        }}
      >
        {children}
      </body>
    </html>
  );
}
