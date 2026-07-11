// Minimal imperative handle a transport exposes so a visualizer can read the
// playback clock and drive scrubbing without knowing which audio engine is
// underneath. TrackMixer (Tone.js) populates this today; after the SpessaSynth
// branch merges, the same interface maps 1:1 onto its Sequencer
// (getTime → seq.currentHighResolutionTime, seek → seq.currentTime = s,
// setRate → seq.playbackRate = r). The PianoRoll component depends only on this
// type, never on Tone or spessasynth directly.
//
// All times are in *musical seconds* (the tempo-derived timeline produced by
// buildTrackEvents), independent of the current playback rate.
export interface PlayerApi {
  /** Current playhead position in musical seconds. Called every animation frame. */
  getTime(): number;
  /** Total song length in musical seconds. */
  getDuration(): number;
  /** Whether audio is currently advancing. */
  isPlaying(): boolean;
  /** Jump the playhead to a musical-seconds position. */
  seek(seconds: number): void;
  /** Playback speed multiplier (1 = normal, 0.5 = half, 1.5 = faster). */
  setRate(rate: number): void;
  getRate(): number;
}
