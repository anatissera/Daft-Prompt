import type { TabExcerpt, TabExcerptEvent } from "@/lib/types";
import { renderTabAscii } from "@/lib/tabAsciiRenderer.mjs";

type TabKind = "guitar" | "bass" | "drums" | "piano" | "tab";

function instrumentKind(instrument: string): TabKind {
  const normalized = instrument.toLowerCase();
  if (normalized.includes("bass")) return "bass";
  if (normalized.includes("drum")) return "drums";
  if (normalized.includes("piano") || normalized.includes("key")) return "piano";
  if (normalized.includes("guitar")) return "guitar";
  return "tab";
}

function eventLabel(event: TabExcerptEvent, instrument: string): string {
  const beat = `beat ${event.beat_index}`;
  if (event.rest) return `${beat} · rest`;
  const kind = instrumentKind(instrument);
  if (kind === "drums") return `${beat} · ${drumLabel(event.pitch ?? event.fret)}`;
  if (kind === "piano") {
    return `${beat} · ${event.pitch == null ? "note unavailable" : midiNoteName(event.pitch)}${event.duration ? ` · ${event.duration}` : ""}`;
  }
  const position = event.string != null && event.fret != null
    ? `string ${event.string} · fret ${event.fret}`
    : event.fret != null
      ? `note ${event.fret}`
      : "hit";
  const suffix = [event.duration, event.tie ? "tie" : "", event.ghost ? "ghost" : ""]
    .filter(Boolean)
    .join(" · ");
  return [beat, position, suffix].filter(Boolean).join(" · ");
}

function eventChipLabel(event: TabExcerptEvent, kind: TabKind): string {
  if (event.rest) return "rest";
  if (kind === "drums") return drumLabel(event.pitch ?? event.fret);
  if (kind === "piano") return event.pitch == null ? "--" : midiNoteName(event.pitch);
  if ((kind === "guitar" || kind === "bass") && event.string != null && event.fret != null) {
    return `S${event.string} F${event.fret}`;
  }
  return event.pitch == null ? "hit" : midiNoteName(event.pitch);
}

function midiNoteName(pitch: number): string {
  const names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  return `${names[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}

function drumLabel(value: number | null | undefined): string {
  const labels: Record<number, string> = {
    35: "Kick",
    36: "Kick",
    38: "Snare",
    40: "Snare",
    42: "Hat",
    44: "Hat",
    46: "Open hat",
    49: "Crash",
    51: "Ride",
  };
  return value == null ? "Hit" : labels[value] ?? `GM ${value}`;
}

export default function TabExcerptBlock({ excerpt }: { excerpt: TabExcerpt }) {
  if (excerpt.error) {
    return (
      <section className="tab-excerpt tab-excerpt-error" role="alert" aria-label="Tab unavailable">
        <p className="tab-excerpt-eyebrow">Tab unavailable</p>
        <p>{excerpt.answer || excerpt.summary || "I could not render this tablature."}</p>
      </section>
    );
  }
  const kind = instrumentKind(excerpt.instrument);
  return (
    <section className={`tab-excerpt tab-excerpt-${kind}`} aria-label={`${excerpt.instrument} tab excerpt`}>
      <header className="tab-excerpt-header">
        <div>
          <p className="tab-excerpt-eyebrow">{kind === "piano" ? "Piano keys" : kind === "drums" ? "Drum tab" : "Playable tab"}</p>
          <h2 className="tab-excerpt-title">{excerpt.instrument} tab</h2>
        </div>
        {excerpt.track_name ? <span className="tab-excerpt-track">{excerpt.track_name}</span> : null}
      </header>
      {excerpt.tuning.length > 0 ? (
        <p className="tab-excerpt-tuning">Tuning · {excerpt.tuning.join(" · ")}</p>
      ) : null}
      <div className="tab-measures">
        {(kind === "guitar" || kind === "bass") ? (
          <pre className="tab-ascii" aria-label={`${excerpt.instrument} ASCII tablature`}>
            {renderTabAscii(excerpt) || "No playable fretted events in this excerpt."}
          </pre>
        ) : excerpt.measures.map((measure) => (
          <article className="tab-measure" key={measure.index}>
            <header>
              <strong>m. {measure.index + 1}</strong>
              {measure.marker ? <span>{measure.marker}</span> : null}
            </header>
            {measure.events.length > 0 ? (
              <ol className="tab-event-list">
                {measure.events.map((event, index) => (
                  <li key={`${event.beat_index}-${index}`}>
                    <span className={`tab-event-chip tab-event-chip-${kind}`}>{eventChipLabel(event, kind)}</span>
                    <span>{eventLabel(event, excerpt.instrument)}</span>
                  </li>
                ))}
              </ol>
            ) : <p>No playable events in this measure.</p>}
          </article>
        ))}
      </div>
      <p className="tab-excerpt-note">{excerpt.summary}</p>
    </section>
  );
}
