import test from "node:test";
import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";

const mixerSource = await readFile(new URL("../components/TrackMixer.tsx", import.meta.url), "utf8");
const playerSource = await readFile(new URL("./spessasynthPlayer.ts", import.meta.url), "utf8");
const mp3Source = await readFile(new URL("./mp3Export.ts", import.meta.url), "utf8");
const songBlockSource = await readFile(new URL("../components/GeneratedSongBlock.tsx", import.meta.url), "utf8");

test("generated-song playback uses the self-hosted SF3 engine", () => {
  assert.doesNotMatch(mixerSource + playerSource, /gleitz\.github\.io|storage\.googleapis\.com|FLUIDR3_BASE/);
  assert.match(mixerSource, /spessasynth_lib/);
  assert.match(mixerSource, /loadSoundBank/);
  assert.match(mixerSource, /workletUrl/);
  assert.match(playerSource, /MuseScore_General\.sf3/);
  assert.match(playerSource, /spessasynth_processor\.min\.js/);
});

test("MP3 export renders through the same SF3 path and honors audible tracks", () => {
  assert.match(mp3Source, /renderSongToMp3Blob/);
  assert.match(mp3Source, /buildMidiWithChannels/);
  assert.match(mp3Source, /loadSoundBank/);
  assert.match(mp3Source, /@breezystack\/lamejs/);
  assert.match(mp3Source, /audible\?: Set<string>/);
  assert.match(songBlockSource, /triggerMp3Download\(song, undefined, audibleTrackIds\)/);
});

test("self-hosted SF3 assets are present", async () => {
  const sf3 = await stat(new URL("../public/soundfonts/MuseScore_General.sf3", import.meta.url));
  const worklet = await stat(new URL("../public/spessasynth/spessasynth_processor.min.js", import.meta.url));

  assert.ok(sf3.size > 1_000_000);
  assert.ok(worklet.size > 10_000);
});
