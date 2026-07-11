import { createRequire } from "module";

const require = createRequire(import.meta.url);

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Artifact files (MusicXML for the score viewer) are served by the FastAPI
  // backend. The backend emits RELATIVE /artifacts/… URLs so they resolve
  // against the frontend origin — required for remote access (Tailscale,
  // LAN), where the backend's localhost isn't reachable from the browser.
  // This rewrite proxies them through the Next server.
  async rewrites() {
    return [
      {
        source: "/artifacts/:path*",
        destination: `${API_BASE_URL}/artifacts/:path*`,
      },
    ];
  },
  webpack: (config) => {
    // tone's "module" field (its ESM build) has circular-import binding issues
    // that break under Webpack, surfacing as "Tone.X is not a constructor" in
    // @magenta/music. Force resolution to tone's UMD bundle instead.
    config.resolve.alias.tone = require.resolve("tone/build/Tone.js", {
      paths: [require.resolve("@magenta/music/package.json")],
    });
    return config;
  },
};

export default nextConfig;
