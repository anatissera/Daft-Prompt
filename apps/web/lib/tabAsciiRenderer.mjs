const DEFAULT_TUNINGS = {
  guitar: ["E", "B", "G", "D", "A", "E"],
  bass: ["G", "D", "A", "E"],
};

function normalizeKind(instrument) {
  const normalized = String(instrument ?? "").toLowerCase();
  return normalized.includes("bass") ? "bass" : "guitar";
}

function durationInBeats(duration) {
  const value = String(duration ?? "").trim();
  const fraction = value.match(/(\d+(?:\.\d+)?)\s*\/\s*(\d+)/);
  if (fraction) return (4 * Number(fraction[1])) / Number(fraction[2]);
  const number = value.match(/\d+(?:\.\d+)?/);
  return number ? Number(number[0]) : 0.25;
}

function lineLabels(excerpt, kind) {
  const fallback = DEFAULT_TUNINGS[kind];
  const tuning = Array.isArray(excerpt?.tuning) && excerpt.tuning.length === fallback.length
    ? excerpt.tuning
    : fallback;
  return tuning.map((value, index) => String(value || fallback[index]).replace(/\d+$/, ""));
}

function measureGrid(measure, stringCount) {
  const playable = (measure?.events ?? []).filter(
    (event) => !event?.rest && Number.isInteger(event?.string) && Number.isInteger(event?.fret),
  );
  if (!playable.length) return null;

  const span = Math.max(
    4,
    ...playable.map((event) => Number(event.beat_index ?? 0) + durationInBeats(event.duration)),
  );
  const cellCount = Math.max(16, Math.ceil(span * 4));
  const grid = Array.from({ length: stringCount }, () => Array(cellCount).fill(null));
  let maxDigits = 1;
  for (const event of playable) {
    const stringIndex = event.string - 1;
    if (stringIndex < 0 || stringIndex >= stringCount) continue;
    const cell = Math.max(0, Math.min(cellCount - 1, Math.round(Number(event.beat_index ?? 0) * 4)));
    const fret = String(event.fret);
    maxDigits = Math.max(maxDigits, fret.length);
    if (grid[stringIndex][cell] == null) grid[stringIndex][cell] = fret;
  }
  const cellWidth = Math.max(2, maxDigits + 1);
  return grid.map((line) => line.map((value) => (value == null ? "-".repeat(cellWidth) : value.padEnd(cellWidth, "-"))).join(""));
}

export function renderTabAscii(excerpt) {
  const kind = normalizeKind(excerpt?.instrument);
  const labels = lineLabels(excerpt, kind);
  const blocks = [];
  for (const measure of excerpt?.measures ?? []) {
    const lines = measureGrid(measure, labels.length);
    if (!lines) continue;
    const marker = measure.marker ? ` · ${measure.marker}` : "";
    blocks.push([
      `m. ${Number(measure.index ?? 0) + 1}${marker}`,
      ...lines.map((line, index) => `${labels[index]}|${line}|`),
    ].join("\n"));
  }
  return blocks.join("\n\n");
}

