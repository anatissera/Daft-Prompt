import assert from "node:assert/strict";
import test from "node:test";

import {
  answerReferenceQuestion,
  describeReferenceSummary,
  formatConfidence,
  formatDuration,
  getAnalysisNotes,
  getAnalysisReadyMessage,
  getKeyCandidateSummary,
  getLegacyEnergySections,
  getMainProgression,
  getStemListening,
  getStructureTimeline,
  getTopChordEstimates,
  isLowUsefulness,
  isReferenceQuestion,
} from "./referenceProfileView.mjs";

const profile = {
  reference_id: "ref_demo",
  source: {
    reference_id: "ref_demo",
    kind: "upload",
    label: "Under pressure.mp3",
    uri: "/tmp/Under pressure.mp3",
    authorized: true,
    permission_error: null,
  },
  summary: "Analyzed about 241.2s of local audio.",
  audio: {
    duration_seconds: 241.2,
    tempo_bpm: 113.6,
    tempo_confidence: 0.82,
    key: "D major",
    key_confidence: 0.64,
    confidence: 0.71,
    overall_confidence: 0.71,
    energy_curve: [],
    chord_estimates: [
      {
        start_seconds: 0,
        end_seconds: 16,
        chords: ["D", "A", "Bm", "G"],
        confidence: 0.63,
        confidence_label: "medium",
        is_probable: true,
        label: "Probably D - A - Bm - G",
      },
      {
        start_seconds: 16,
        end_seconds: 32,
        chords: ["G", "A"],
        confidence: 0.41,
        confidence_label: "low",
        is_probable: true,
        label: "Probably G - A",
      },
    ],
    sections: [],
    stems: [],
  },
};

const harmonicProfile = {
  ...profile,
  audio: {
    ...profile.audio,
    tempo: {
      primary_bpm: 113.6,
      confidence: 0.82,
      candidates: [],
      beat_grid_confidence: 0.8,
      bar_grid_confidence: 0.78,
    },
    meter: {
      time_signature: [4, 4],
      source: "assumed",
      confidence: 0.5,
    },
    harmony: {
      key: {
        primary: { key: "D major", mode: "major", confidence: 0.64 },
        candidates: [
          { key: "D major", mode: "major", confidence: 0.64 },
          { key: "B minor", mode: "minor", confidence: 0.58 },
        ],
        relative_key_ambiguity: true,
        confidence: 0.64,
      },
      chord_spans: [
        {
          start_bar: 1,
          end_bar: 1,
          start_beat: 1,
          end_beat: 1,
          start_seconds: 0,
          end_seconds: 2,
          candidates: [],
          chosen: { root: "D", quality: "major", label: "D", confidence: 0.72 },
          confidence: 0.72,
        },
        {
          start_bar: 2,
          end_bar: 2,
          start_beat: 1,
          end_beat: 1,
          start_seconds: 2,
          end_seconds: 4,
          candidates: [],
          chosen: { root: "A", quality: "major", label: "A", confidence: 0.7 },
          confidence: 0.7,
        },
      ],
      progressions: [
        {
          start_bar: 1,
          end_bar: 4,
          chords: ["D", "A", "Bm", "G"],
          confidence: 0.63,
          repetitions: 2,
        },
      ],
      harmonic_rhythm_label: "moderate",
      confidence: 0.71,
    },
    structure: {
      sections: [
        {
          label: "A",
          start_bar: 1,
          end_bar: 4,
          start_seconds: 0,
          end_seconds: 16,
          confidence: 0.78,
          main_progression: ["D", "A", "Bm", "G"],
        },
        {
          label: "B",
          start_bar: 5,
          end_bar: 8,
          start_seconds: 16,
          end_seconds: 32,
          confidence: 0.74,
          main_progression: ["G", "A", "D", "D"],
        },
      ],
      confidence: 0.76,
    },
    analysis_notes: [
      {
        code: "weak_bar_grid",
        message: "The bar grid was unstable; chord and structure estimates are less reliable.",
        severity: "info",
      },
    ],
  },
};

test("formatDuration renders minutes and seconds", () => {
  assert.equal(formatDuration(241.2), "4:01");
  assert.equal(formatDuration(59.6), "1:00");
});

test("isReferenceQuestion classifies profile questions but not composition prompts", () => {
  assert.equal(isReferenceQuestion("What chords are probably in the chorus?"), true);
  assert.equal(isReferenceQuestion("What is the tempo?"), true);
  assert.equal(isReferenceQuestion("Why does the energy lift?"), true);
  assert.equal(isReferenceQuestion("Compose a slow blues"), false);
});

test("answerReferenceQuestion answers chord questions from probable estimates", () => {
  assert.equal(
    answerReferenceQuestion("What chords are probably in the chorus?", profile),
    "The chords are estimated. The strongest matches are: Probably D - A - Bm - G from 0:00-0:16 with medium · 63% confidence; Probably G - A from 0:16-0:32 with low · 41% confidence.",
  );
});

test("harmonic helpers prefer key candidates, progressions, structure, and notes", () => {
  assert.deepEqual(getKeyCandidateSummary(harmonicProfile), [
    { kind: "tonal_candidate", label: "D major", description: "Tonal center candidate", confidence: "medium · 64%" },
    { kind: "tonal_candidate", label: "B minor", description: "Tonal center candidate", confidence: "medium · 58%" },
  ]);
  assert.deepEqual(getMainProgression(harmonicProfile), {
    kind: "chord_progression",
    label: "Probable chord progression: D - A - Bm - G",
    bars: "bars 1-4",
    repetitions: 2,
    confidence: "medium · 63%",
  });
  assert.deepEqual(getStructureTimeline(harmonicProfile), [
    {
      label: "A",
      bars: "1-4",
      timeRange: "0:00-0:16",
      progression: "D - A - Bm - G",
      confidence: "high · 78%",
    },
    {
      label: "B",
      bars: "5-8",
      timeRange: "0:16-0:32",
      progression: "G - A - D - D",
      confidence: "medium · 74%",
    },
  ]);
  assert.deepEqual(getAnalysisNotes(harmonicProfile), [
    {
      label: "info",
      message: "The bar grid was unstable; chord and structure estimates are less reliable.",
    },
  ]);
});

test("answerReferenceQuestion answers structure and harmonic progression questions from rich profile", () => {
  assert.equal(
    answerReferenceQuestion("What chords repeat?", harmonicProfile),
    "The main progression is estimated as probably D - A - Bm - G across bars 1-4, with medium · 63% confidence.",
  );
  assert.equal(
    answerReferenceQuestion("What is the A/B/C structure?", harmonicProfile),
    "The structure appears to repeat as A bars 1-4 (high · 78%) / B bars 5-8 (medium · 74%).",
  );
  // "chorus" is structural: it must route to structure, not chord estimates.
  assert.equal(
    answerReferenceQuestion("Where is the chorus?", harmonicProfile),
    "The structure appears to repeat as A bars 1-4 (high · 78%) / B bars 5-8 (medium · 74%).",
  );
});

test("answerReferenceQuestion answers tempo and key questions with confidence", () => {
  assert.equal(
    answerReferenceQuestion("What is the tempo?", profile),
    "The tempo is likely 114 BPM with high · 82% confidence.",
  );
  assert.equal(
    answerReferenceQuestion("What key is this in?", profile),
    "The key is probably D major with medium · 64% confidence.",
  );
});

test("answerReferenceQuestion answers section energy questions with evidence", () => {
  const sectionProfile = {
    ...profile,
    audio: {
      ...profile.audio,
      sections: [
        {
          name: "verse",
          start_seconds: 0,
          end_seconds: 16,
          confidence: 0.9,
          energy: 0.32,
          energy_confidence: 0.7,
          chord_estimates: [],
        },
        {
          name: "chorus",
          start_seconds: 16,
          end_seconds: 32,
          confidence: 0.86,
          energy: 0.81,
          energy_confidence: 0.76,
          chord_estimates: [],
        },
      ],
    },
  };

  assert.equal(
    answerReferenceQuestion("How does the energy change?", sectionProfile),
    "The section energy estimate is verse 32% from 0:00-0:16, then chorus 81% from 0:16-0:32.",
  );
});

test("answerReferenceQuestion gives a compact fallback for unknown profile questions", () => {
  assert.equal(
    answerReferenceQuestion("What should I listen for?", profile),
    "I can answer from the current analysis about likely tempo, key, A/B/C structure, and probable chords.",
  );
});

test("formatConfidence combines label and score", () => {
  assert.equal(formatConfidence("medium", 0.64), "medium · 64%");
});

test("describeReferenceSummary keeps tempo and key probabilistic", () => {
  assert.deepEqual(describeReferenceSummary(profile), [
    "Duration 4:01",
    "Likely tempo 114 BPM · high · 82%",
    "Likely key D major · medium · 64%",
    "Overall confidence 71%",
  ]);
});

test("describeReferenceSummary includes double-time tempo alternative", () => {
  const tempoProfile = {
    ...profile,
    audio: {
      ...profile.audio,
      tempo: {
        primary_bpm: 86,
        confidence: 0.88,
        candidates: [
          { bpm: 86, confidence: 0.88, relation: "primary" },
          { bpm: 172, confidence: 0.56, relation: "double_time" },
        ],
        beat_grid_confidence: 0.88,
        bar_grid_confidence: 0.8,
      },
    },
  };

  const rows = describeReferenceSummary(tempoProfile);

  assert(rows.some((row) => row === "Also plausible: 172 BPM double-time"));
});

test("describeReferenceSummary includes close key alternatives for ambiguous key", () => {
  const ambiguousProfile = {
    ...harmonicProfile,
    audio: {
      ...harmonicProfile.audio,
      harmony: {
        ...harmonicProfile.audio.harmony,
        key: {
          primary: { key: "Ab major", mode: "major", confidence: 0.44 },
          candidates: [
            { key: "Ab major", mode: "major", confidence: 0.44 },
            { key: "F minor", mode: "minor", confidence: 0.42 },
            { key: "C# minor", mode: "minor", confidence: 0.38 },
            { key: "Ab minor", mode: "minor", confidence: 0.36 },
          ],
          relative_key_ambiguity: true,
          confidence: 0.44,
        },
      },
    },
  };

  assert.deepEqual(getKeyCandidateSummary(ambiguousProfile, 2), [
    { kind: "tonal_candidate", label: "Ab major", description: "Tonal center candidate", confidence: "low · 44%" },
    { kind: "tonal_candidate", label: "F minor", description: "Tonal center candidate", confidence: "low · 42%" },
  ]);
  assert(!describeReferenceSummary(ambiguousProfile).some((row) => row.startsWith("Likely key")));
  assert(
    describeReferenceSummary(ambiguousProfile).includes(
      "Tonal center is ambiguous; close candidates include Ab major, F minor, C# minor.",
    ),
  );
  assert(describeReferenceSummary(ambiguousProfile).includes("Close alternatives: F minor, C# minor, Ab minor"));
});


test("harmony helpers label tonal candidates separately from chord progression", () => {
  const keyCandidates = getKeyCandidateSummary(harmonicProfile);
  const mainProgression = getMainProgression(harmonicProfile);

  assert.equal(keyCandidates[0].kind, "tonal_candidate");
  assert.equal(keyCandidates[0].description, "Tonal center candidate");
  assert.equal(mainProgression.kind, "chord_progression");
  assert(mainProgression.label.startsWith("Probable chord progression:"));
});


test("analysis ready message avoids likely key copy for ambiguous key", () => {
  const ambiguousProfile = {
    ...harmonicProfile,
    audio: {
      ...harmonicProfile.audio,
      harmony: {
        ...harmonicProfile.audio.harmony,
        key: {
          primary: { key: "Ab major", mode: "major", confidence: 0.44 },
          candidates: [
            { key: "Ab major", mode: "major", confidence: 0.44 },
            { key: "F minor", mode: "minor", confidence: 0.44 },
          ],
          relative_key_ambiguity: true,
          confidence: 0.44,
        },
      },
    },
  };

  const message = getAnalysisReadyMessage(ambiguousProfile);

  assert(!message.includes("likely key"));
  assert(message.includes("ambiguous tonal center"));
  assert(message.includes("Ab major"));
});

test("weak progression and low-confidence structure use candidate copy", () => {
  const weakProfile = {
    ...harmonicProfile,
    audio: {
      ...harmonicProfile.audio,
      harmony: {
        ...harmonicProfile.audio.harmony,
        progressions: [
          {
            start_bar: 1,
            end_bar: 4,
            chords: ["D", "A", "Bm", "G"],
            confidence: 0.38,
            repetitions: 3,
          },
        ],
      },
      structure: {
        ...harmonicProfile.audio.structure,
        confidence: 0.25,
        sections: harmonicProfile.audio.structure.sections.map((section) => ({
          ...section,
          confidence: 0.25,
        })),
      },
    },
  };

  assert.deepEqual(getMainProgression(weakProfile), {
    kind: "chord_progression",
    label: "Weak chord loop candidate: D - A - Bm - G",
    bars: "bars 1-4",
    repetitions: 3,
    confidence: "low · 38%",
  });
  assert.equal(
    answerReferenceQuestion("What chords repeat?", weakProfile),
    "Weak chord loop candidate: D - A - Bm - G across bars 1-4, with low · 38% confidence.",
  );
  assert.equal(
    answerReferenceQuestion("What is the A/B/C structure?", weakProfile),
    "Structure is approximate/unclear: A bars 1-4 (low · 25%) / B bars 5-8 (low · 25%).",
  );
});

test("legacy energy is hidden when all sections have unknown zero energy", () => {
  const energyProfile = {
    ...profile,
    audio: {
      ...profile.audio,
      sections: [
        {
          name: "A",
          start_seconds: 0,
          end_seconds: 16,
          confidence: 0.2,
          energy: null,
          energy_confidence: 0,
          chord_estimates: [],
        },
        {
          name: "B",
          start_seconds: 16,
          end_seconds: 32,
          confidence: 0.2,
          energy: 0,
          energy_confidence: 0,
          chord_estimates: [],
        },
      ],
    },
  };

  assert.deepEqual(getLegacyEnergySections(energyProfile), []);
});

test("analysis notes stay compact for display", () => {
  assert.deepEqual(getAnalysisNotes(harmonicProfile), [
    {
      label: "info",
      message: "The bar grid was unstable; chord and structure estimates are less reliable.",
    },
  ]);
});

test("low usefulness summary leads with the limitation", () => {
  const weakProfile = {
    ...harmonicProfile,
    audio: {
      ...harmonicProfile.audio,
      analysis_notes: [
        { code: "low_usefulness", message: "Key, chord, and structure evidence are all weak.", severity: "warning" },
      ],
    },
  };

  assert.equal(isLowUsefulness(weakProfile), true);
  assert.equal(isLowUsefulness(harmonicProfile), false);

  const rows = describeReferenceSummary(weakProfile);
  assert.ok(rows.some((row) => row.includes("rough sketch")));
});

test("getTopChordEstimates returns probable chord labels with time ranges", () => {
  assert.deepEqual(getTopChordEstimates(profile, 1), [
    {
      label: "Probably D - A - Bm - G",
      timeRange: "0:00-0:16",
      confidence: "medium · 63%",
    },
  ]);
  assert.deepEqual(getTopChordEstimates(harmonicProfile, 1), [
    {
      label: "Probably D",
      timeRange: "bars 1-1",
      confidence: "medium · 72%",
    },
  ]);
});

test("getStemListening builds chips and callouts from listening profiles", () => {
  const profile = {
    audio: {
      stems: [
        {
          name: "drums",
          role: "percussion",
          timbre: { brightness: "bright", noisiness: "noisy", band_balance: "high-heavy" },
          rhythm: { feel: "swung", density: "busy", syncopation: 0.5 },
          dynamics: {
            events: [
              { kind: "build", start_bar: 8, end_bar: 15 },
              { kind: "drop", start_bar: 15, end_bar: 16 },
            ],
          },
        },
        { name: "bass", role: "bass" },
      ],
    },
  };
  const rows = getStemListening(profile);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].name, "drums");
  assert.deepEqual(rows[0].chips, ["bright", "noisy", "high-heavy", "swung", "busy", "syncopated"]);
  assert.deepEqual(rows[0].callouts, ["builds bars 8–15", "drops at bar 16"]);
});

test("getStemListening hides balanced band and low syncopation chips", () => {
  const profile = {
    audio: {
      stems: [
        {
          name: "other",
          role: "harmony",
          timbre: { brightness: "warm", noisiness: "tonal", band_balance: "balanced" },
          rhythm: { feel: "straight", density: "moderate", syncopation: 0.1 },
        },
      ],
    },
  };
  const rows = getStemListening(profile);
  assert.deepEqual(rows[0].chips, ["warm", "tonal", "straight", "moderate"]);
  assert.deepEqual(rows[0].callouts, []);
});

test("getStemListening is empty without listening data", () => {
  assert.deepEqual(getStemListening({ audio: { stems: [{ name: "bass" }] } }), []);
  assert.deepEqual(getStemListening({}), []);
});
