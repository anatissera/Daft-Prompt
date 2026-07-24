// Server-only. The backend guards its LLM-backed routes with a shared secret;
// this reads it inside the Next API routes so it never reaches the browser.
// Absent in local development, where the backend leaves those routes open.

export function upstreamHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  const apiKey = process.env.API_KEY;
  if (apiKey) headers["X-API-Key"] = apiKey;
  return headers;
}
