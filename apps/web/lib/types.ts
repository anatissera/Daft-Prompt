// TypeScript mirror of the backend `SongState` (apps/api/music_assistant/domain/song_state.py).
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

export type ReferenceSourceKind = "upload" | "direct_url" | "youtube" | "metadata" | "local";
export type ConfidenceLabel = "low" | "medium" | "high";
export type AnalysisNoteSeverity = "info" | "warning" | "error";
export type TempoCandidateRelation = "primary" | "half_time" | "double_time" | "alternate";
export type MeterSource = "assumed" | "estimated";
export type KeyMode = "major" | "minor" | "unknown";
export type ChordQuality = "major" | "minor" | "diminished" | "unknown";
export type StemRole = "percussion" | "bass" | "vocal" | "harmony" | "mix" | "other";

export interface ReferenceSource {
  reference_id: string;
  kind: ReferenceSourceKind;
  label: string;
  uri: string;
  authorized: boolean;
  permission_error: string | null;
}

export interface ChordEstimate {
  start_seconds: number;
  end_seconds: number;
  chords: string[];
  confidence: number;
  is_probable: boolean;
  confidence_label: ConfidenceLabel;
  label: string;
}

export interface EnergyPoint {
  time_seconds: number;
  energy: number;
  confidence: number;
}

export interface SectionProfile {
  name: string;
  start_seconds: number;
  end_seconds: number;
  confidence: number;
  energy: number | null;
  energy_confidence: number;
  chord_estimates: ChordEstimate[];
}

export interface AnalysisNote {
  code: string;
  message: string;
  severity: AnalysisNoteSeverity;
}

export interface TempoCandidate {
  bpm: number;
  confidence: number;
  relation: TempoCandidateRelation;
}

export interface TempoProfile {
  primary_bpm: number | null;
  confidence: number;
  candidates: TempoCandidate[];
  beat_grid_confidence: number;
  bar_grid_confidence: number;
}

export interface MeterProfile {
  time_signature: [number, number];
  source: MeterSource;
  confidence: number;
}

export interface KeyCandidate {
  key: string;
  mode: KeyMode;
  confidence: number;
}

export interface KeyProfile {
  primary: KeyCandidate | null;
  candidates: KeyCandidate[];
  relative_key_ambiguity: boolean;
  confidence: number;
}

export interface ChordCandidate {
  root: string;
  quality: ChordQuality;
  label: string;
  confidence: number;
}

export interface AnalysisChordSpan {
  start_bar: number;
  end_bar: number;
  start_beat: number;
  end_beat: number;
  start_seconds: number;
  end_seconds: number;
  candidates: ChordCandidate[];
  chosen: ChordCandidate | null;
  confidence: number;
}

export interface ProgressionEstimate {
  start_bar: number;
  end_bar: number;
  chords: string[];
  confidence: number;
  repetitions: number;
}

export interface HarmonicProfile {
  key: KeyProfile;
  chord_spans: AnalysisChordSpan[];
  progressions: ProgressionEstimate[];
  harmonic_rhythm_label: string;
  confidence: number;
}

export interface StructuralSection {
  label: string;
  start_bar: number;
  end_bar: number;
  start_seconds: number;
  end_seconds: number;
  confidence: number;
  main_progression: string[];
}

export interface StructureProfile {
  sections: StructuralSection[];
  confidence: number;
}

export interface StemProfile {
  name: string;
  artifact_uri: string | null;
  role: StemRole;
  available: boolean;
  confidence: number;
}

export interface AudioProfile {
  duration_seconds: number;
  tempo_bpm: number | null;
  tempo_confidence: number;
  key: string | null;
  key_confidence: number;
  confidence: number;
  overall_confidence: number;
  energy_curve: EnergyPoint[];
  chord_estimates: ChordEstimate[];
  sections: SectionProfile[];
  stems: StemProfile[];
  tempo: TempoProfile | null;
  meter: MeterProfile;
  harmony: HarmonicProfile | null;
  structure: StructureProfile | null;
  analysis_notes: AnalysisNote[];
}

export interface ReferenceProfile {
  reference_id: string;
  source: ReferenceSource;
  audio: AudioProfile | null;
  summary: string;
}

export interface ExplanationAnswer {
  reference_id: string;
  answer: string;
  evidence: string[];
}

export type AnalysisProgressType =
  | "accepted"
  | "separating_stems"
  | "building_harmonic_source"
  | "estimating_tempo_grid"
  | "estimating_key"
  | "estimating_chords"
  | "detecting_structure"
  | "analysis_keepalive";

export type AnalysisEvent =
  | { type: AnalysisProgressType; message: string }
  | { type: "done"; message: string; profile: ReferenceProfile }
  | { type: "error"; message: string };

// SSE events from POST /compose/stream (proxied by app/api/compose), in emission
// order: one "director" event, zero or more "agent_pass" events as instruments
// compose/negotiate, optional "error", one "convergence" or "done" event.
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
  | {
      type: "error";
      code: string;
      message: string;
      provider: string | null;
      model: string | null;
      partial: boolean;
    }
  | (ComposeResponse & { type: "done" });
