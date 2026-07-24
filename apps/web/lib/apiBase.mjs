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

// Going direct raises the ceiling but does not remove it: Cloud Run rejects
// HTTP/1 requests over 32 MiB at its frontend, before the container sees them,
// and answers with an opaque HTML error page rather than our JSON. Checking
// here turns that into a sentence the user can act on.
//
// In practice this only bites lossless files — 32 MiB is about 3 minutes of
// stereo WAV, 6 of FLAC, but 13 minutes of a 320 kbps MP3.
export const MAX_UPLOAD_BYTES = 32 * 1024 * 1024;

export function uploadTooLargeMessage(bytes) {
  if (typeof bytes !== "number" || bytes <= MAX_UPLOAD_BYTES) return null;
  const mb = (bytes / 1024 / 1024).toFixed(1);
  return `That file is ${mb} MB and the limit is 32 MB. Converting it to MP3 will fit almost any track.`;
}
