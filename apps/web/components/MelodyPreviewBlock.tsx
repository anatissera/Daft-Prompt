import type { MelodyProfile } from "@/lib/types";

function noteName(pitch: number): string {
  const names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  return `${names[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}

export default function MelodyPreviewBlock({ melody }: { melody: MelodyProfile }) {
  const range = melody.pitch_low != null && melody.pitch_high != null
    ? `${noteName(melody.pitch_low)}–${noteName(melody.pitch_high)}`
    : "register unavailable";
  return (
    <section className="melody-preview" aria-label="Provisional melody transcription">
      <header className="melody-preview-header">
        <div>
          <p className="melody-preview-eyebrow">Local transcription</p>
          <h2>Melody preview</h2>
        </div>
        <span>{Math.round(melody.confidence * 100)}% provisional</span>
      </header>
      <p className="melody-preview-summary">
        {melody.note_count} notes · {range} · {melody.contour} contour
      </p>
      {melody.representative_events.length ? (
        <ol className="melody-events">
          {melody.representative_events.map((event, index) => (
            <li key={`${event.bar}-${event.start_beat}-${event.pitch}-${index}`}>
              <strong>{noteName(event.pitch)}</strong>
              <span>bar {event.bar + 1} · beat {event.start_beat + 1}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
