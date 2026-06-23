// Deterministic per-instrument accent color so the same roster id (e.g. "bass")
// always gets the same hue across RosterView and NegotiationFeed, without
// needing the backend to assign colors.
const HUES = [262, 200, 152, 28, 330, 12, 176, 48];

export function instrumentColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  const hue = HUES[hash % HUES.length];
  return `hsl(${hue}, 80%, 72%)`;
}
