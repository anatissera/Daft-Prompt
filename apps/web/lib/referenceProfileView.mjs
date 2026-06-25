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
  const tempo = audio.tempo?.primary_bpm ?? audio.tempo_bpm;
  const tempoConfidence = audio.tempo?.confidence ?? audio.tempo_confidence;
  if (tempo !== null && tempo !== undefined) {
    rows.push(
      `Likely tempo ${Math.round(tempo)} BPM · ${confidenceLabel(tempoConfidence)} · ${formatPercent(
        tempoConfidence,
      )}`,
    );
  }
  const key = audio.harmony?.key?.primary?.key ?? audio.key;
  const keyConfidence = audio.harmony?.key?.confidence ?? audio.key_confidence;
  if (key) {
    rows.push(
      `Likely key ${key} · ${confidenceLabel(keyConfidence)} · ${formatPercent(keyConfidence)}`,
    );
  }
  rows.push(`Overall confidence ${formatPercent(audio.overall_confidence || audio.confidence || 0)}`);
  return rows;
}

export function getTopChordEstimates(profile, limit = 4) {
  const audio = profile.audio;
  if (!audio) return [];
  const harmonicSpans = audio.harmony?.chord_spans ?? [];
  if (harmonicSpans.length > 0) {
    return harmonicSpans
      .filter((span) => span.chosen)
      .slice(0, limit)
      .map((span) => ({
        label: `Probably ${span.chosen.label}`,
        timeRange: `bars ${span.start_bar}-${span.end_bar}`,
        confidence: formatConfidence(confidenceLabel(span.chosen.confidence), span.chosen.confidence),
      }));
  }
  return audio.chord_estimates.slice(0, limit).map((estimate) => ({
    label: estimate.label,
    timeRange: `${formatDuration(estimate.start_seconds)}-${formatDuration(estimate.end_seconds)}`,
    confidence: formatConfidence(estimate.confidence_label, estimate.confidence),
  }));
}

export function getKeyCandidateSummary(profile, limit = 4) {
  const candidates = profile.audio?.harmony?.key?.candidates ?? [];
  return candidates.slice(0, limit).map((candidate) => ({
    label: candidate.key,
    confidence: formatConfidence(confidenceLabel(candidate.confidence), candidate.confidence),
  }));
}

export function getMainProgression(profile) {
  const progressions = profile.audio?.harmony?.progressions ?? [];
  const main = progressions.find((progression) => progression.chords.length > 0);
  if (!main) return null;
  return {
    label: `Probably ${main.chords.join(" - ")}`,
    bars: `bars ${main.start_bar}-${main.end_bar}`,
    repetitions: main.repetitions,
    confidence: formatConfidence(confidenceLabel(main.confidence), main.confidence),
  };
}

export function getStructureTimeline(profile) {
  const sections = profile.audio?.structure?.sections ?? [];
  return sections.map((section) => ({
    label: section.label,
    bars: `${section.start_bar}-${section.end_bar}`,
    timeRange: `${formatDuration(section.start_seconds)}-${formatDuration(section.end_seconds)}`,
    progression: section.main_progression.join(" - "),
    confidence: formatConfidence(confidenceLabel(section.confidence), section.confidence),
  }));
}

export function getAnalysisNotes(profile) {
  return (profile.audio?.analysis_notes ?? []).map((note) => ({
    label: note.severity,
    message: note.message,
  }));
}

export function isReferenceQuestion(prompt) {
  const normalized = prompt.toLowerCase();
  if (/\b(compose|generate|make|write|create)\b/.test(normalized)) return false;
  return /\b(chord|chords|tempo|bpm|key|energy|section|sections|form|structure|chorus|verse|analysis|analyze|profile)\b/.test(
    normalized,
  );
}

export function answerReferenceQuestion(prompt, profile) {
  const normalized = prompt.toLowerCase();
  const audio = profile.audio;
  if (!audio) return "I do not have an audio profile for this reference yet.";

  if (/\b(chord|chords|chorus|harmony|harmonic)\b/.test(normalized)) {
    const main = getMainProgression(profile);
    const estimates = getTopChordEstimates(profile, 4);
    if (!main && estimates.length === 0) {
      return "I do not have probable chord estimates for this reference yet.";
    }
    if (main) {
      return `The main progression is estimated as ${main.label} across ${main.bars}, with ${main.confidence} confidence.`;
    }
    const summary = estimates
      .map((estimate) => `${estimate.label} from ${estimate.timeRange} with ${estimate.confidence} confidence`)
      .join("; ");
    return `The chords are estimated. The strongest matches are: ${summary}.`;
  }

  if (/\b(tempo|bpm|speed|fast|slow)\b/.test(normalized)) {
    const tempo = audio.tempo?.primary_bpm ?? audio.tempo_bpm;
    const tempoConfidence = audio.tempo?.confidence ?? audio.tempo_confidence;
    if (tempo === null || tempo === undefined) {
      return "I do not have a reliable tempo estimate for this reference yet.";
    }
    return `The tempo is likely ${Math.round(tempo)} BPM with ${formatConfidence(
      confidenceLabel(tempoConfidence),
      tempoConfidence,
    )} confidence.`;
  }

  if (/\b(key|tonality|tonal)\b/.test(normalized)) {
    const key = audio.harmony?.key?.primary?.key ?? audio.key;
    const keyConfidence = audio.harmony?.key?.confidence ?? audio.key_confidence;
    if (!key) {
      return "I do not have a reliable key estimate for this reference yet.";
    }
    return `The key is probably ${key} with ${formatConfidence(confidenceLabel(keyConfidence), keyConfidence)} confidence.`;
  }

  if (/\b(section|sections|form|structure|verse|chorus)\b/.test(normalized)) {
    const timeline = getStructureTimeline(profile);
    if (timeline.length > 0) {
      const sections = timeline
        .slice(0, 5)
        .map((section) => `${section.label} bars ${section.bars}`)
        .join(" / ");
      return `The structure appears to repeat as ${sections}.`;
    }
  }

  if (/\b(energy|lift|bigger|contrast)\b/.test(normalized)) {
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

  return "I can answer from the current analysis about likely tempo, key, A/B/C structure, and probable chords.";
}

export function confidenceLabel(value) {
  if (value >= 0.75) return "high";
  if (value >= 0.5) return "medium";
  return "low";
}
