import type { TabExcerpt, TabExcerptEvent } from "@/lib/types";

function eventLabel(event: TabExcerptEvent, instrument: string): string {
  const beat = `beat ${event.beat_index}`;
  if (event.rest) return `${beat} · rest`;
  if (instrument === "drums") return `${beat} · GM ${event.fret ?? "hit"}`;
  if (instrument === "piano") {
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

function midiNoteName(pitch: number): string {
  const names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  return `${names[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}

export default function TabExcerptBlock({ excerpt }: { excerpt: TabExcerpt }) {
  return (
    <section className="tab-excerpt" aria-label={`${excerpt.instrument} tab excerpt`}>
      <header className="tab-excerpt-header">
        <div>
          <p className="tab-excerpt-eyebrow">Songsterr excerpt</p>
          <h2 className="tab-excerpt-title">{excerpt.instrument} tab</h2>
        </div>
        {excerpt.track_name ? <span className="tab-excerpt-track">{excerpt.track_name}</span> : null}
      </header>
      {excerpt.tuning.length > 0 ? (
        <p className="tab-excerpt-tuning">Tuning · {excerpt.tuning.join(" · ")}</p>
      ) : null}
      <div className="tab-measures">
        {excerpt.measures.map((measure) => (
          <article className="tab-measure" key={measure.index}>
            <header>
              <strong>m. {measure.index + 1}</strong>
              {measure.marker ? <span>{measure.marker}</span> : null}
            </header>
            {measure.events.length > 0 ? (
              <ol>
                {measure.events.map((event, index) => (
                  <li key={`${event.beat_index}-${index}`}>{eventLabel(event, excerpt.instrument)}</li>
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
