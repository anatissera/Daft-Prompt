"use client";

import type { ChordDiagramChatMessage, PlayableChord } from "@/lib/chatTypes";

const KEY_PCS = [
  { pc: 0, label: "C", black: false },
  { pc: 1, label: "C#", black: true },
  { pc: 2, label: "D", black: false },
  { pc: 3, label: "Eb", black: true },
  { pc: 4, label: "E", black: false },
  { pc: 5, label: "F", black: false },
  { pc: 6, label: "F#", black: true },
  { pc: 7, label: "G", black: false },
  { pc: 8, label: "Ab", black: true },
  { pc: 9, label: "A", black: false },
  { pc: 10, label: "Bb", black: true },
  { pc: 11, label: "B", black: false },
];

export default function ChordDiagramBlock({ message }: { message: ChordDiagramChatMessage }) {
  const playable = message.playableChords;
  return (
    <section className="chord-diagram-block" aria-label={`${playable.instrument} chord diagrams`}>
      <header className="chord-diagram-header">
        <span className="chord-diagram-badge">
          {playable.instrument === "piano" ? "Piano chords" : "Guitar chords"}
        </span>
        <span className="chord-diagram-source">{playable.source_label}</span>
      </header>
      <div className="chord-section-grid">
        {playable.sections.map((section) => (
          <article key={section.name} className="chord-section-card">
            <div className="chord-section-title-row">
              <h3>{section.name}</h3>
              <span>{Math.round(section.confidence * 100)}%</span>
            </div>
            <div className="chord-card-list">
              {section.chords.map((chord) => (
                <div key={`${section.name}-${chord.chord}`} className="chord-card">
                  <div className="chord-card-label">
                    <strong>{chord.chord}</strong>
                    {chord.notes.length > 0 ? <span>{chord.notes.join(" · ")}</span> : null}
                  </div>
                  {playable.instrument === "piano" ? <MiniKeyboard chord={chord} /> : null}
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function MiniKeyboard({ chord }: { chord: PlayableChord }) {
  const activePcs = new Set(chord.midi_notes.map((note) => note % 12));
  return (
    <div className="mini-keyboard" aria-label={`${chord.chord} piano keys`}>
      {KEY_PCS.map((key) => (
        <span
          key={`${chord.chord}-${key.pc}`}
          className={`mini-key mini-key-${key.black ? "black" : "white"}${activePcs.has(key.pc) ? " mini-key-active" : ""}`}
          title={key.label}
        >
          {!key.black ? key.label : ""}
        </span>
      ))}
    </div>
  );
}
