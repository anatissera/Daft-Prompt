// Where the browser should send an audio file for analysis.
//
// Chat and compose go through the Next API routes: small JSON bodies, and the
// proxy keeps the backend URL and the shared secret server-side. Analysis
// cannot. A serverless function caps request bodies at 4.5 MB — which is 25
// seconds of WAV, or about three minutes of a 192 kbps MP3 — and caps its own
// duration well below what stem separation takes on CPU. Both limits disappear
// when the upload goes straight to the backend.
//
// With no public base configured (local development) this falls back to the
// proxy route, so `npm run dev` needs no extra setup and no CORS handling.

export function analyzeEndpoint(publicApiBase) {
  const base = typeof publicApiBase === "string" ? publicApiBase.trim() : "";
  const normalized = base.replace(/\/+$/, "");
  return normalized ? `${normalized}/references/analyze/stream` : "/api/references/analyze";
}
