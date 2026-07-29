// Cloud Run itself (not our app) rejects a request when no instance is ready
// to take it — either a cold start losing the race against its own boot time
// (~13-17s measured) or --max-instances already saturated. Both surface as
// the same infra text ("...no available instance" / "Rate exceeded."), as
// plain text, at 429 or 500. Our app's own errors are always JSON (FastAPI's
// HTTPException). That distinction is what tells a transient capacity hiccup
// apart from a real application failure worth surfacing immediately instead
// of retrying.

export const INSTANCE_UNAVAILABLE_RETRY_DELAYS_MS = [3_000, 8_000, 15_000];

export function isRetryableInstanceUnavailable(status, text, contentType) {
  if (status !== 429 && status < 500) return false;
  if (contentType?.includes("application/json")) {
    try {
      JSON.parse(text);
      return false; // valid JSON from our own app — a real error, don't retry
    } catch {
      // falls through: JSON content-type but unparsable body isn't ours either
    }
  }
  return true;
}
