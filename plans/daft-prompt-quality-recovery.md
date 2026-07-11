# Daft Prompt Quality Recovery Plan

## Goal

Fix the current "Something by The Beatles" failure path end to end: evidence
answers should answer the actual question, playable tabs should look like real
tabs, generated songs should use evidence-guided instruments, sounds, rhythms,
and arrangement balance, edits should actually change the requested material,
and final composition review should catch bad outputs before the user hears
them.

This plan continues the Daft Prompt convergence work. It assumes the LLM tool
router is the primary intent and entity decision-maker, while public evidence
connectors remain the source of truth for known-song facts.

## Product North Star

Daft Prompt should behave like a chat-first music teacher and producer.

Expected behavior for the motivating example:

- User asks "What chords does Something by The Beatles have?"
- The router identifies a named song, a chord question, and the need for online
  evidence.
- The app researches the song and directly answers the chord question in the
  same response.
- If the user asks for intro tabs, the app renders readable ASCII guitar tab for
  the requested section, not note-event cards.
- If the user asks for a similar or exact song, composition uses the song
  evidence: guitar-led arrangement, matching tempo/key/harmony/style, restrained
  piano if evidence supports it, and no generic synth/piano filler.
- If the user says "replace the piano with guitars," the generated song changes
  instrumentation and musical material, not just a patch label.
- Piano roll appears only when explicitly requested or opened, and should show
  the requested section or track rather than an always-on full-song wall.

## Current Failures

- Evidence lookup returns "usable evidence covers chords" but does not answer
  the chord question until the user asks again.
- Chord answers can include raw Markdown markers such as `**Intro:**`.
- `TabExcerptBlock` renders note-event cards instead of monospaced tablature.
- Composition from reference evidence is too generic: decent harmony, weak
  leads, poor timbre, and wrong instrument balance.
- "Exact/similar to this song" does not preserve source instrumentation strongly
  enough.
- Generated-song edits do not understand structural operations like replacing
  piano with guitars.
- The arbiter resolves pending negotiation bookkeeping; it does not review final
  composition quality against the user brief.
- Generated piano roll is always visible and full-song, even when the user did
  not ask for it.

## Branch And Commit Strategy

Continue from the current convergence branch after preserving the LLM-router
fix. Keep commits small:

1. `fix: answer requested evidence after song lookup`
2. `fix: render readable chord and tab answers`
3. `feat: add evidence-guided composition fidelity modes`
4. `feat: add final composition reviewer`
5. `feat: support structural generated-song edits`
6. `fix: gate piano roll and playable views by request`
7. `test: add Something end-to-end quality regressions`

Do not merge `giner` blindly. Compare `product-direction` for instrument
selection behavior and port only parts that improve roster selection without
losing current evidence and router work.

## Phase 1 - Evidence Answers Must Answer The User

Implementation:

- Keep `search_song_evidence.requested_info`, for example `["chords"]`,
  `["intro_tab"]`, or `["key"]`.
- After `MusicTools.research_song()` saves the `SongKnowledgeProfile`,
  immediately run the matching profile query when `requested_info` is present:
  chords -> `ProfileQueryTools.chords`;
  key/tempo -> `ProfileQueryTools.key_bpm`;
  instruments/tone -> `ProfileQueryTools.instrumentation`;
  sections -> `ProfileQueryTools.sections`;
  playable requests -> `get_tab_excerpt`.
- The first response for "What chords does X have?" must include the chord
  answer, not only a research summary.
- Keep research context secondary: source count, source names, confidence, and
  missing evidence.
- Add optional diagnostics such as `answered_request` and `requested_info` only
  where useful for tests.

Acceptance:

- "What chords does Something by The Beatles have?" returns chord content in the
  first assistant answer.
- If chord evidence is thin, the answer says that directly and cites what was
  found.

## Phase 2 - Chord And Tab Readability

Implementation:

- Stop showing raw Markdown in chat bubbles. Deterministic chord answers should
  be structured plain text plus chord chart data where available.
- Add source-backed chord chart rows for `SongKnowledgeProfile`, not only local
  audio estimates.
- Replace current guitar/bass tab event-card UI with ASCII tablature:
  use a monospaced `<pre>` block;
  guitar display is high-to-low `E B G D A E`;
  bass display is `G D A E`;
  quantize events into a measure grid using beat positions and durations;
  place fret numbers on the correct string and dashes elsewhere;
  keep multi-digit frets aligned;
  omit rests from guitar/bass ASCII tabs.
- Respect requested section: "intro tabs" selects Intro measures first, "chorus
  tabs" selects Chorus, and unavailable sections explain which sections are
  available.

Acceptance:

```text
E|--2----2------0----------2----------------|
B|--3----2------0----------2----------------|
G|--4----2------0----------3----------------|
D|--4----2------2--------2------------------|
A|--2----2------2------4--------------------|
E|--------------0----2----------------------|
```

No literal `**` appears in chord answers.

## Phase 3 - Evidence-Guided Composition Fidelity

Implementation:

- Introduce explicit composition fidelity modes in `CompositionBrief`:
  `similar`, `very_similar`, and `exact_or_as_close_as_possible`.
- For song-reference composition, feed the director stronger evidence:
  Songsterr track index instrumentation;
  tone profiles;
  chord progressions by section;
  tempo/key/meter;
  requested section or full-song scope;
  instrument salience such as guitar-led or small piano support.
- Director roster constraints:
  if evidence shows guitar/bass/drums and small piano, do not replace that with
  piano/synth-heavy arrangements;
  avoid synths/keyboards unless evidence or user request supports them;
  preserve exact requested instruments for "exactly like" or "as similar as
  possible."
- Instrument agents should use source chord maps, section maps, playable seeds,
  and melodic/rhythmic motifs when available, while avoiding one-bar lead loops
  pasted across the song.
- Compare `product-direction` director/instrument prompts and port better
  instrument-selection wording where it improves behavior without losing current
  patch/evidence support.

Acceptance:

- "Compose a similar song" for `Something` produces guitar-led classic
  rock/baroque pop, not piano/synth-heavy generic output.
- "Exactly like / as similar as possible" produces stronger source-preservation
  warnings and constraints, not a vague style sketch.
- Leads have phrase variation and section-aware contour.

## Phase 4 - Real Final Composition Reviewer

Implementation:

- Add a final `CompositionReviewer` after instrument generation and before
  returning `ChatComposeResult`.
- Reviewer input: `CompositionBrief`, song or artist evidence profile, final
  `SongState`, validation results, and requested source playable preservation.
- Reviewer checks:
  required instruments present;
  forbidden or unsupported instruments absent;
  requested guitar/piano/bass/drum balance respected;
  chord progression and key fit;
  lead repetition/density not obviously broken;
  coherent section form;
  fidelity mode honored;
  source-backed playable parts preserved when requested.
- Reviewer output: `accepted`, `issues`, `targeted_revision_requests`, and
  `user_warnings`.
- Allow one bounded targeted revision pass for high-severity reviewer failures.
- Keep this separate from the arbiter, which resolves negotiation bookkeeping.

Acceptance:

- A piano-heavy output for a guitar-led reference fails review and triggers
  revision.
- Missing requested guitar or unchanged piano replacement fails review.
- The user sees useful warnings, not raw internal reviewer text.

## Phase 5 - Structural Edits Over Generated Songs

Implementation:

- Replace edit heuristics with a typed edit intent:
  `tone_change`, `chord_change`, `replace_instrument`, `add_instrument`,
  `remove_instrument`, `rebalance`, `regenerate_part`, and
  `make_more_like_reference`.
- For "replace all that piano with one or more guitars like the one from the
  song": target piano/keys parts, remove or deactivate piano, add one or more
  guitar roster items, generate new guitar material from reference evidence, and
  preserve unaffected drums/bass.
- Use LLM classification for edit intent when configured, then deterministic
  validation.
- Ask clarification only when targets are truly ambiguous.

Acceptance:

- "More guitar than piano" adjusts arrangement balance.
- "Replace piano with guitars like the song" removes/replaces piano material and
  adds guitar material.
- Unaffected tracks remain unchanged unless reharmonization is required.

## Phase 6 - Requested-Only Playable Views

Implementation:

- Generated song cards should not show full piano roll by default.
- Render piano roll only when the user explicitly asks for piano roll, when the
  user opens a collapsed "Piano roll" details panel, or when a debug/developer
  flag is enabled.
- For requested generated-song tabs or piano roll, show the requested instrument
  and requested section if named, defaulting to a compact excerpt.
- Keep MIDI/MP3 export visible after composition.

Acceptance:

- A generated song response is primarily player, roster, and exports.
- "Show the guitar tab for the chorus" renders only that guitar/section.
- The piano roll no longer appears as a confusing full-song visual unless
  requested or opened.

## Phase 7 - Hybrid Genre And Style Guardrails

Implementation:

- Do not make genre/style deterministic templates. The LLM remains responsible
  for creative arrangement choices.
- Add non-binding genre/style guardrails used by the director and final
  reviewer:
  expected instrument families;
  clearly inappropriate instrument families unless explicitly requested;
  rhythmic priorities;
  tone and production hints;
  source-evidence preservation expectations.
- Guardrails catch obvious mismatches, not force canned outputs:
  guitar-led Beatles-style songs should not become piano/synth-heavy;
  grunge/punk should not add synth pads by default;
  funk should strongly prioritize drums, bass, and syncopated guitar/keys;
  French house/electronic may prioritize synths, samples, filtered chords, and
  dance drums.
- The director may violate a guardrail only when the user explicitly asks for
  it, source evidence supports it, or the prompt is a transformation request.
- The reviewer flags guardrail violations as quality issues and requests a
  targeted revision.
- Deterministic fallback patterns are allowed only as emergency support when LLM
  output is vague or invalid; they should not define normal genre style.

Acceptance:

- Same prompt shape across genres produces recognizably different rhythms,
  instruments, and tones because the LLM reasons from evidence and style.
- Reviewer catches genre/reference-incompatible instrumentation.
- The system remains flexible enough to create unusual user-requested hybrids.

## Test Plan

Backend:

- Named song evidence:
  "What chords does Something by The Beatles have?" researches and answers
  chords in the first response;
  the response contains no raw Markdown markers;
  thin evidence returns uncertainty and sources, not a guessed answer.
- Tabs:
  Songsterr guitar events render as six-line ASCII tab;
  intro/chorus section selection chooses matching markers;
  multi-digit fret alignment is stable.
- Composition:
  `similar` and `exact_or_as_close_as_possible` produce different
  `CompositionBrief` fidelity constraints;
  a guitar-led reference creates a guitar-led roster;
  piano-heavy output for a guitar-led source fails reviewer;
  final reviewer can request one targeted revision.
- Edits:
  "replace piano with guitars" removes/replaces piano and adds guitar;
  "make guitar sound cleaner" remains tone-only;
  "change piano chord to Am" remains chord-only and preserves other tracks.
- UI/type tests:
  chat message with chord chart renders without `**`;
  tab block renders ASCII tab;
  piano roll is hidden by default and appears on request/expand.

Validation:

```bash
cd apps/api && python -m pytest
cd apps/web && npm run typecheck && node --test lib/trackMixerLogic.test.mjs lib/pipelineGraphs.test.mjs
cd apps/web && node --test lib/tabAsciiRenderer.test.mjs lib/chatActionAdapter.test.mjs
```

## Assumptions And Defaults

- Public evidence connectors remain the source of truth for known songs.
- The app may display source-backed tabs for this classroom project.
- "Similar" means inspired and idiomatic; "exact / as similar as possible" means
  preserve source-backed traits and playable parts where evidence exists.
- The reviewer is allowed one targeted revision pass, not infinite retries.
- Piano roll is a contextual teaching/debug view, not a default generated-song
  output.
- Existing LLM-router fixes stay in place.
