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
  /** Per-instrument + "_overall" fraction (0-1) of sounding notes that are tones of
   *  the active chord. Absent on older responses. */
  harmonic_fit?: Record<string, number>;
}

export interface ChatErrorDetail {
  type?: "error";
  code: string;
  message: string;
  provider?: string | null;
  model?: string | null;
  partial?: boolean;
}

export interface ChatComposeResult {
  song: SongState;
  source: string;
  artifacts?: {
    midi: string;
    musicxml: string;
  } | null;
  reference_transfer_intent?: Record<string, unknown> | null;
  instrument_requests_summary?: Record<string, unknown>[];
  literal_applications?: Record<string, unknown>[];
  uncertainty_notes?: string[];
  warnings?: string[];
}

export interface TabExcerptEvent {
  beat_index: number;
  duration: string;
  string?: number | null;
  fret?: number | null;
  pitch?: number | null;
  rest: boolean;
  tie: boolean;
  ghost: boolean;
}

export interface TabExcerptMeasure {
  index: number;
  marker?: string | null;
  note_events: number;
  durations: string[];
  events: TabExcerptEvent[];
}

export interface TabExcerpt {
  reference_id?: string | null;
  answer: string;
  summary: string;
  instrument: string;
  track_name: string;
  tuning: string[];
  measures: TabExcerptMeasure[];
  evidence?: string[];
}

export interface ChordChartRow { label: string; chords: string[]; confidence: number; }

export interface ChatResponse {
  intent: "answer_reference" | "compose" | "compose_from_reference" | "clarify" | "off_topic";
  reply: string;
  reference_id?: string | null;
  reference_label?: string | null;
  answer?: { answer: string; confidence?: string } | null;
  tab_excerpt?: TabExcerpt | null;
  chord_chart?: ChordChartRow[];
  melody_preview?: MelodyProfile | null;
  compose?: ChatComposeResult | null;
  clarification?: string | null;
  usage?: Record<string, number> | null;
  error?: ChatErrorDetail | null;
}

export interface ChatRequestPayload {
  message: string;
  reference_id?: string | null;
  current_song?: SongState | null;
  conversation_context?: string | null;
}

export type ReferenceSourceKind = "upload" | "direct_url" | "youtube" | "metadata" | "local";
export type ConfidenceLabel = "low" | "medium" | "high";
export type AnalysisNoteSeverity = "info" | "warning" | "error";
export type TempoCandidateRelation = "primary" | "half_time" | "double_time" | "alternate";
export type MeterSource = "assumed" | "estimated";
export type KeyMode = "major" | "minor" | "unknown";
export type ChordQuality = "major" | "minor" | "diminished" | "unknown";
export type StemRole = "percussion" | "bass" | "vocal" | "harmony" | "mix" | "other";
export type InstrumentFamily = "drums" | "bass" | "guitar" | "piano";
export type TransferMode =
  | "similar"
  | "literal"
  | "timbre_only"
  | "pattern_only"
  | "energy_only"
  | "avoid_copying"
  | "clarify";
export type EvidenceClaimType =
  | "tempo"
  | "key"
  | "meter"
  | "chord_progression"
  | "section"
  | "lyrics"
  | "tab"
  | "credit"
  | "metadata"
  | "instrumentation"
  | "groove"
  | "timbre"
  | "trait"
  | "audio_estimate"
  | "other";
export type ExtractionMethod =
  | "site_parser"
  | "browser_rendered_page"
  | "api"
  | "audio_analyzer"
  | "manual_fixture"
  | "inference";

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

export interface TimbreProfile {
  brightness: "dark" | "warm" | "bright";
  noisiness: "tonal" | "mixed" | "noisy";
  band_balance: "low-heavy" | "mid-heavy" | "high-heavy" | "balanced";
  centroid_hz: number | null;
  flatness: number | null;
  band_split: number[];
  interpretation: string;
  confidence: number;
}

export interface RhythmProfile {
  feel: "straight" | "swung";
  swing_ratio: number | null;
  syncopation: number;
  density: "sparse" | "moderate" | "busy";
  onsets_per_bar: number | null;
  interpretation: string;
  confidence: number;
}

export interface DynamicsPoint {
  bar: number;
  level: number;
}

export interface DynamicsEvent {
  kind: "build" | "drop";
  start_bar: number;
  end_bar: number;
}

export interface StemDynamics {
  points: DynamicsPoint[];
  events: DynamicsEvent[];
  interpretation: string;
  confidence: number;
}

export interface MelodyEvent {
  bar: number;
  start_beat: number;
  duration_beats: number;
  pitch: number;
}

export interface MelodyProfile {
  note_count: number;
  pitch_low: number | null;
  pitch_high: number | null;
  contour: "rising" | "falling" | "static" | "mixed" | "unknown";
  representative_events: MelodyEvent[];
  confidence: number;
}

export interface StemProfile {
  name: string;
  artifact_uri: string | null;
  role: StemRole;
  available: boolean;
  confidence: number;
  timbre?: TimbreProfile | null;
  rhythm?: RhythmProfile | null;
  dynamics?: StemDynamics | null;
}

export interface TimeRange {
  start_seconds: number | null;
  end_seconds: number | null;
  confidence: number | null;
  source: string | null;
}

export interface EvidenceClaim {
  claim_id: string;
  claim_type: EvidenceClaimType;
  value: string;
  normalized_value: string | null;
  section_name: string | null;
  time_range: TimeRange | null;
  source_name: string;
  source_url: string;
  extraction_method: ExtractionMethod;
  confidence: number;
  snippet: string;
  notes: string[];
  confidence_label: ConfidenceLabel;
}

export interface EvidenceConflict {
  conflict_id: string;
  claim_type: EvidenceClaimType;
  description: string;
  claims: EvidenceClaim[];
  resolution: string | null;
}

export interface MissingData {
  field: string;
  reason: string;
  needed_evidence: string;
}

export interface SongIdentity {
  title: string;
  artist: string | null;
  album: string | null;
  year: number | null;
  version: string | null;
  candidate_matches: string[];
}

export interface SongSectionProfile {
  name: string;
  order: number;
  start_seconds: number | null;
  end_seconds: number | null;
  timestamp_confidence: number | null;
  timestamp_source: string | null;
  lyric_claims: EvidenceClaim[];
  chord_claims: EvidenceClaim[];
  key_claims: EvidenceClaim[];
  instrument_claims: EvidenceClaim[];
  energy: number | null;
  density: number | null;
  notable_instruments: string[];
  evidence_ids: string[];
}

export interface InstrumentTrait {
  instrument: string;
  role: string;
  traits: Record<string, string>;
  source_claim_ids: string[];
  confidence: number;
  confidence_label: ConfidenceLabel;
}

export interface InstrumentTimbreProfile {
  instrument_name: string;
  source_label: string;
  midi_program: number;
  midi_range: [number, number];
  technique: string | null;
  is_drum: boolean;
  playback_note: string;
}

export interface InstrumentPatternProfile {
  density: "low" | "medium" | "high";
  subdivision: string;
  accent_beats: number[];
  contour: string;
  fill_frequency: string;
  section_variations: Record<string, string>;
}

export interface ReferenceNoteSeed {
  bar: number;
  start_beat: number;
  duration_beats: number;
  pitch: number | null;
  velocity: number;
  source_mode: "songsterr" | "audio" | "inferred";
  section_name: string | null;
}

export interface ReferenceNotePack {
  pack_id: string;
  instrument_family: InstrumentFamily;
  section_name: string;
  start_bar: number;
  bar_count: number;
  notes: ReferenceNoteSeed[];
}

export interface ReferenceRhythmPattern {
  pattern_id: string;
  section_name: string;
  density: "low" | "medium" | "high";
  accent_beats: number[];
  durations: number[];
  subdivision: string;
}

export interface ReferencePitchPattern {
  pattern_id: string;
  section_name: string;
  register: number[];
  pitch_classes: number[];
  intervals: number[];
  contour: string;
}

export interface ReferenceMotif {
  motif_id: string;
  section_name: string;
  start_bar: number;
  bar_count: number;
  repetitions: number;
  rhythm_signature: string;
  interval_signature: string;
}

export interface ReferenceHarmonicContext {
  key: string | null;
  chord_progression: string[];
  roman_progression: string[];
  harmonic_rhythm: string;
}

export interface MusicalMemoryProfile {
  summary: string;
  note_packs: ReferenceNotePack[];
  rhythm_patterns: ReferenceRhythmPattern[];
  pitch_patterns: ReferencePitchPattern[];
  harmonic_context: ReferenceHarmonicContext;
  motifs: ReferenceMotif[];
}

export interface ReferenceInstrumentProfile {
  source_reference_id: string;
  source_profile_id: string;
  instrument_family: InstrumentFamily;
  track_name: string;
  confidence: number;
  timbre: InstrumentTimbreProfile;
  pattern: InstrumentPatternProfile;
  symbolic_seed: ReferenceNoteSeed[];
  musical_memory: MusicalMemoryProfile;
  evidence: string[];
  uncertainty_notes: string[];
}

export interface ReferenceTransferItem {
  instrument_family: InstrumentFamily;
  reference_id: string;
  transfer_mode: TransferMode;
  section_name: string | null;
  fidelity: number;
  constraints: string[];
}

export interface ReferenceTransferIntent {
  items: ReferenceTransferItem[];
  clarification: string | null;
}

export interface SongKnowledgeProfile {
  profile_id: string;
  identity: SongIdentity;
  credits: Record<string, EvidenceClaim[]>;
  metadata: Record<string, unknown>;
  evidence_claims: EvidenceClaim[];
  sections: SongSectionProfile[];
  traits: InstrumentTrait[];
  conflicts: EvidenceConflict[];
  missing_data: MissingData[];
  confidence_summary: Record<string, string>;
  audio: AudioProfile | null;
}

export interface CompositionBrief {
  brief_id: string;
  user_request: string;
  global_constraints: Record<string, unknown>;
  references_used: string[];
  transfer_policy: Record<string, string[]>;
  harmonic_guidance: Record<string, unknown>;
  rhythmic_guidance: Record<string, unknown>;
  melodic_guidance: Record<string, unknown>;
  form_guidance: Record<string, unknown>;
  instrumentation: Record<string, unknown>;
  instrument_requests: Record<string, Record<string, unknown>>;
  timbre_traits: Record<string, unknown>;
  forbidden_traits: string[];
  uncertainty_notes: string[];
}

export interface ArrangementCell {
  stem: string;
  activity: number;
  level: "silent" | "low" | "medium" | "high";
}

export interface ArrangementColumn {
  section: string;
  start_bar: number;
  end_bar: number;
  cells: ArrangementCell[];
}

export interface EnsembleProfile {
  columns: ArrangementColumn[];
  callouts: string[];
  interpretation: string;
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
  mix_timbre?: TimbreProfile | null;
  ensemble?: EnsembleProfile | null;
  melody?: MelodyProfile | null;
  analysis_notes: AnalysisNote[];
}

export interface ReferenceProfile {
  reference_id: string;
  source: ReferenceSource;
  audio: AudioProfile | null;
  summary: string;
  research_evidence: ResearchEvidence[];
  knowledge: SongKnowledgeProfile | null;
}

export interface ResearchEvidence {
  url: string;
  site: string;
  claim_type: string;
  value: string;
  confidence: number;
  snippet: string;
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
  | "extracting_stem_features"
  | "detecting_structure"
  | "analysis_keepalive";

export interface AnalysisProgressEvent {
  type: AnalysisProgressType;
  message: string;
  status: "started" | "completed";
  elapsed_seconds: number | null;
  cache_hit: boolean | null;
}

export type AnalysisEvent =
  | AnalysisProgressEvent
  | { type: "done"; message: string; profile: ReferenceProfile }
  | { type: "error"; message: string };

// SSE events from POST /compose/stream (proxied by app/api/compose), in emission
// order: one "director" event, zero or more "agent_pass" events as instruments
// compose/negotiate, optional "error", one "convergence" or "done" event.
export type ComposeTiming = {
  elapsed_seconds?: number | null;
  stage_elapsed_seconds?: number | null;
};

export type ComposeEvent =
  | ({ type: "director"; source: "director" | "canned"; header: Header; roster: RosterItem[] } & ComposeTiming)
  | ({
      type: "agent_pass";
      round: number;
      instrument_id: string;
      composition_group?: string | null;
      notes_summary: string;
      new_requests: NegotiationRequest[];
      resolved_requests: NegotiationRequest[];
    } & ComposeTiming)
  | ({
      type: "convergence";
      round: number;
      converged: boolean;
      resolved_requests: NegotiationRequest[];
    } & ComposeTiming)
  | {
      type: "error";
      code: string;
      message: string;
      provider: string | null;
      model: string | null;
      partial: boolean;
    }
  | (ComposeResponse & { type: "done" } & ComposeTiming);
