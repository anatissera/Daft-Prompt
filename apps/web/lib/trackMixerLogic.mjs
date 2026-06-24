export function getAudibleTrackIds(trackIds, mutedTrackIds, soloTrackIds) {
  const soloActive = soloTrackIds.size > 0;
  const audible = new Set();

  for (const trackId of trackIds) {
    if (mutedTrackIds.has(trackId)) continue;
    if (soloActive && !soloTrackIds.has(trackId)) continue;
    audible.add(trackId);
  }

  return audible;
}

export function midiToFrequency(pitch) {
  return Math.round(440 * 2 ** ((pitch - 69) / 12) * 1000) / 1000;
}

export function buildTrackEvents(song) {
  const secondsPerBeat = 60 / song.header.tempo_bpm;
  const beatsPerBar = beatsPerMeasure(song.header.time_signature);
  const eventsByTrack = {};

  for (const [trackId, part] of Object.entries(song.parts)) {
    eventsByTrack[trackId] = [];
    for (const note of part.notes) {
      if (note.pitch === null || note.pitch === undefined) continue;
      const startBeat = note.bar * beatsPerBar + note.start_beat;
      eventsByTrack[trackId].push({
        durationSeconds: note.dur * secondsPerBeat,
        frequency: midiToFrequency(note.pitch),
        pitch: note.pitch,
        startSeconds: startBeat * secondsPerBeat,
        velocity: note.velocity / 127,
      });
    }
  }

  return eventsByTrack;
}

export function getSongDurationSeconds(song) {
  let duration = 0;

  for (const events of Object.values(buildTrackEvents(song))) {
    for (const event of events) {
      duration = Math.max(duration, event.startSeconds + event.durationSeconds);
    }
  }

  return duration;
}

function beatsPerMeasure(timeSignature) {
  const [numerator, denominator] = timeSignature;
  return numerator * (4 / denominator);
}
