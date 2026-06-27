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

export function isLowUsefulness(profile) {
  const notes = profile.audio?.analysis_notes ?? [];
  return notes.some((note) => note.code === "low_usefulness");
}

export function describeReferenceSummary(profile) {
  const audio = profile.audio;
  if (!audio) return ["No audio profile available yet."];

  const rows = [`Duration ${formatDuration(audio.duration_seconds)}`];
  if (isLowUsefulness(profile)) {
    rows.push("Chord and structure evidence is weak here; treat the read below as a rough sketch.");
  }
  const tempo = audio.tempo?.primary_bpm ?? audio.tempo_bpm;
  const tempoConfidence = audio.tempo?.confidence ?? audio.tempo_confidence;
  if (tempo !== null && tempo !== undefined) {
    rows.push(
      `Likely tempo ${Math.round(tempo)} BPM · ${confidenceLabel(tempoConfidence)} · ${formatPercent(
        tempoConfidence,
      )}`,
    );
    for (const alternative of getTempoAlternatives(audio.tempo)) {
      rows.push(`Also plausible: ${Math.round(alternative.bpm)} BPM ${formatTempoRelation(alternative.relation)}`);
    }
  }
  const key = audio.harmony?.key?.primary?.key ?? audio.key;
  const keyConfidence = audio.harmony?.key?.confidence ?? audio.key_confidence;
  if (key) {
    if (keyConfidence < 0.5 || audio.harmony?.key?.relative_key_ambiguity) {
      const candidates = [key, ...getCloseKeyCandidates(audio.harmony?.key)].slice(0, 3);
      rows.push(`Tonal center is ambiguous; close candidates include ${candidates.join(", ")}.`);
    } else {
      rows.push(
        `Likely key ${key} · ${confidenceLabel(keyConfidence)} · ${formatPercent(keyConfidence)}`,
      );
    }
    const alternatives = getCloseKeyAlternatives(audio.harmony?.key);
    if (alternatives.length > 0) {
      rows.push(`Close alternatives: ${alternatives.join(", ")}`);
    }
  }
  rows.push(`Overall confidence ${formatPercent(audio.overall_confidence || audio.confidence || 0)}`);
  return rows;
}

function getTempoAlternatives(tempoProfile) {
  const primary = tempoProfile?.primary_bpm;
  return (tempoProfile?.candidates ?? [])
    .filter((candidate) => candidate.relation !== "primary")
    .filter((candidate) => candidate.bpm !== primary)
    .filter((candidate) => Number.isFinite(candidate.bpm))
    .filter((candidate) => candidate.confidence >= 0.4)
    .slice(0, 3);
}

function formatTempoRelation(relation) {
  if (relation === "half_time") return "half-time";
  if (relation === "double_time") return "double-time";
  return "alternate";
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
  const keyProfile = profile.audio?.harmony?.key;
  const candidates = keyProfile?.candidates ?? [];
  const globalConfidence = keyProfile?.confidence;
  return candidates.slice(0, limit).map((candidate) => ({
    label: candidate.key,
    confidence: formatConfidence(
      confidenceLabel(Math.min(candidate.confidence, globalConfidence ?? candidate.confidence)),
      Math.min(candidate.confidence, globalConfidence ?? candidate.confidence),
    ),
  }));
}

export function getMainProgression(profile) {
  const progressions = profile.audio?.harmony?.progressions ?? [];
  const main = progressions.find((progression) => progression.chords.length > 0);
  if (!main) return null;
  const progression = main.chords.join(" - ");
  return {
    label: main.confidence < 0.5 ? `Weak chord loop candidate: ${progression}` : `Probably ${progression}`,
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

export function getLegacyEnergySections(profile) {
  const sections = profile.audio?.sections ?? [];
  const usefulSections = sections.filter((section) => {
    const hasEnergy = section.energy !== null && section.energy !== undefined;
    return hasEnergy && section.energy_confidence > 0;
  });
  if (usefulSections.length === 0) return [];
  return usefulSections.map((section) => ({
    name: section.name,
    timeRange: `${formatDuration(section.start_seconds)}-${formatDuration(section.end_seconds)}`,
    energy: Math.round((section.energy ?? 0) * 100),
    confidence: formatConfidence(confidenceLabel(section.energy_confidence), section.energy_confidence),
  }));
}

function getCloseKeyAlternatives(keyProfile) {
  if (!keyProfile?.primary || !keyProfile.relative_key_ambiguity) return [];
  return keyProfile.candidates
    .slice(1, 4)
    .filter((candidate) => keyProfile.confidence - candidate.confidence <= 0.12)
    .map((candidate) => candidate.key);
}

function getCloseKeyCandidates(keyProfile) {
  if (!keyProfile?.primary) return [];
  return keyProfile.candidates.slice(1, 4).map((candidate) => candidate.key);
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

  // "chorus"/"verse" are structural terms, handled by the structure branch below.
  if (/\b(chord|chords|harmony|harmonic)\b/.test(normalized)) {
    const main = getMainProgression(profile);
    const estimates = getTopChordEstimates(profile, 4);
    if (!main && estimates.length === 0) {
      return "I do not have probable chord estimates for this reference yet.";
    }
    if (main) {
      const progression = main.label.replace("Weak chord loop candidate: ", "").replace("Probably ", "");
      if (main.label.startsWith("Weak chord loop candidate:")) {
        return `Weak chord loop candidate: ${progression} across ${main.bars}, with ${main.confidence} confidence.`;
      }
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
    if (keyConfidence < 0.5 || audio.harmony?.key?.relative_key_ambiguity) {
      const candidates = [key, ...getCloseKeyCandidates(audio.harmony?.key)].slice(0, 3);
      return `Tonal center is ambiguous; close candidates include ${candidates.join(", ")}, with ${formatConfidence(confidenceLabel(keyConfidence), keyConfidence)} confidence.`;
    }
    return `The key is probably ${key} with ${formatConfidence(confidenceLabel(keyConfidence), keyConfidence)} confidence.`;
  }

  if (/\b(section|sections|form|structure|verse|chorus)\b/.test(normalized)) {
    const timeline = getStructureTimeline(profile);
    if (timeline.length > 0) {
      const sections = timeline
        .slice(0, 5)
        .map((section) => `${section.label} bars ${section.bars} (${section.confidence})`)
        .join(" / ");
      if ((audio.structure?.confidence ?? 0) < 0.4) {
        return `Structure is approximate/unclear: ${sections}.`;
      }
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
