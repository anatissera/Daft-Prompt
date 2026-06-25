export function formatDuration(seconds) {
  const safeSeconds = Number.isFinite(seconds) ? Math.max(0, Math.round(seconds)) : 0;
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

export function formatPercent(value) {
  if (!Number.isFinite(value)) return "0%";
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

export function formatConfidence(label, value) {
  return `${label} · ${formatPercent(value)}`;
}

export function describeReferenceSummary(profile) {
  const audio = profile.audio;
  if (!audio) return ["No audio profile available yet."];

  const rows = [`Duration ${formatDuration(audio.duration_seconds)}`];
  if (audio.tempo_bpm !== null && audio.tempo_bpm !== undefined) {
    rows.push(
      `Likely tempo ${Math.round(audio.tempo_bpm)} BPM · ${confidenceLabel(audio.tempo_confidence)} · ${formatPercent(
        audio.tempo_confidence,
      )}`,
    );
  }
  if (audio.key) {
    rows.push(
      `Likely key ${audio.key} · ${confidenceLabel(audio.key_confidence)} · ${formatPercent(audio.key_confidence)}`,
    );
  }
  rows.push(`Overall confidence ${formatPercent(audio.overall_confidence || audio.confidence || 0)}`);
  return rows;
}

export function getTopChordEstimates(profile, limit = 4) {
  const audio = profile.audio;
  if (!audio) return [];
  return audio.chord_estimates.slice(0, limit).map((estimate) => ({
    label: estimate.label,
    timeRange: `${formatDuration(estimate.start_seconds)}-${formatDuration(estimate.end_seconds)}`,
    confidence: formatConfidence(estimate.confidence_label, estimate.confidence),
  }));
}

export function isReferenceQuestion(prompt) {
  const normalized = prompt.toLowerCase();
  if (/\b(compose|generate|make|write|create)\b/.test(normalized)) return false;
  return /\b(chord|chords|tempo|bpm|key|energy|section|sections|chorus|verse|analysis|analyze|profile)\b/.test(
    normalized,
  );
}

export function answerReferenceQuestion(prompt, profile) {
  const normalized = prompt.toLowerCase();
  const audio = profile.audio;
  if (!audio) return "I do not have an audio profile for this reference yet.";

  if (/\b(chord|chords|chorus|harmony|harmonic)\b/.test(normalized)) {
    const estimates = getTopChordEstimates(profile, 4);
    if (estimates.length === 0) {
      return "I do not have probable chord estimates for this reference yet.";
    }
    const summary = estimates
      .map((estimate) => `${estimate.label} from ${estimate.timeRange} with ${estimate.confidence} confidence`)
      .join("; ");
    return `The chords are estimated. The strongest matches are: ${summary}.`;
  }

  if (/\b(tempo|bpm|speed|fast|slow)\b/.test(normalized)) {
    if (audio.tempo_bpm === null || audio.tempo_bpm === undefined) {
      return "I do not have a reliable tempo estimate for this reference yet.";
    }
    return `The tempo is likely ${Math.round(audio.tempo_bpm)} BPM with ${formatConfidence(
      confidenceLabel(audio.tempo_confidence),
      audio.tempo_confidence,
    )} confidence.`;
  }

  if (/\b(key|tonality|tonal)\b/.test(normalized)) {
    if (!audio.key) {
      return "I do not have a reliable key estimate for this reference yet.";
    }
    return `The key is probably ${audio.key} with ${formatConfidence(confidenceLabel(audio.key_confidence), audio.key_confidence)} confidence.`;
  }

  if (/\b(energy|section|sections|lift|bigger|contrast|verse|chorus)\b/.test(normalized)) {
    if (audio.sections.length === 0) {
      return "I do not have section-level energy estimates for this reference yet.";
    }
    const sections = audio.sections
      .slice(0, 3)
      .map((section) => {
        const energy = section.energy === null || section.energy === undefined ? "unknown energy" : `${Math.round(section.energy * 100)}%`;
        return `${section.name} ${energy} from ${formatDuration(section.start_seconds)}-${formatDuration(section.end_seconds)}`;
      })
      .join(", then ");
    return `The section energy estimate is ${sections}.`;
  }

  return "I can answer from the current analysis about likely tempo, key, energy or sections, and probable chords.";
}

export function confidenceLabel(value) {
  if (value >= 0.75) return "high";
  if (value >= 0.5) return "medium";
  return "low";
}
