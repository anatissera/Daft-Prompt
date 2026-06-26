import assert from "node:assert/strict";
import test from "node:test";

import {
  answerReferenceQuestion,
  describeReferenceSummary,
  formatConfidence,
  formatDuration,
  getTopChordEstimates,
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
    "I can answer from the current analysis about likely tempo, key, energy or sections, and probable chords.",
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

test("getTopChordEstimates returns probable chord labels with time ranges", () => {
  assert.deepEqual(getTopChordEstimates(profile, 1), [
    {
      label: "Probably D - A - Bm - G",
      timeRange: "0:00-0:16",
      confidence: "medium · 63%",
    },
  ]);
});
