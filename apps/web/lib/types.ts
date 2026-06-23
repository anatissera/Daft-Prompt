// TypeScript mirror of the backend `SongState` (apps/api/llm_band/schema.py).
// Keep in sync; later phases may generate this from the JSON schema in CI.

export interface Section {
  name: string;
  start_bar: number;
  end_bar: number;
}

export interface ChordSpan {
  bar: number;
  chord: string;
}

export interface Header {
  genre: string;
  key: string;
  tempo_bpm: number;
  time_signature: [number, number];
  num_bars: number;
  sections: Section[];
  chord_progression: ChordSpan[];
}

export interface RosterItem {
  id: string;
  instrument: string;
  midi_program: number;
  midi_range: [number, number];
  role: string;
  is_drum: boolean;
}

export interface Note {
  bar: number;
  start_beat: number;
  pitch: number | null; // null = rest
  dur: number;
  velocity: number;
}

export interface Part {
  instrument_id: string;
  version: number;
  notes: Note[];
  notes_summary: string;
  self_notes: string;
}

export interface NegotiationRequest {
  id: string;
  from: string;
  to: string;
  round: number;
  bars: number[];
  request: string;
  rationale: string;
  status: "pending" | "resolved" | "declined";
  resolution: string;
}

export interface SongState {
  request: string;
  header: Header;
  roster: RosterItem[];
  parts: Record<string, Part>;
  negotiation_requests: NegotiationRequest[];
  round: number;
  converged: boolean;
  errors: string[];
}

export interface ComposeResponse {
  job_id: string;
  source: "director" | "canned";
  song: SongState;
  artifacts: {
    midi: string;
    musicxml: string;
  };
}

// SSE events from POST /compose/stream (proxied by app/api/compose), in emission
// order: one "director" event, zero or more "agent_pass" events as instruments
// compose/negotiate, one "convergence" event, then one "done" event.
export type ComposeEvent =
  | { type: "director"; source: "director" | "canned"; header: Header; roster: RosterItem[] }
  | {
      type: "agent_pass";
      round: number;
      instrument_id: string;
      notes_summary: string;
      new_requests: NegotiationRequest[];
      resolved_requests: NegotiationRequest[];
    }
  | {
      type: "convergence";
      round: number;
      converged: boolean;
      resolved_requests: NegotiationRequest[];
    }
  | (ComposeResponse & { type: "done" });
