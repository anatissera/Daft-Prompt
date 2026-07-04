# Product Direction

This document captures the intended direction for Daft Prompt after the current
scraping-analysis experiment. It does not replace `PRODUCT.md` or `DESIGN.md`
yet. Treat it as a decision record and implementation roadmap to review before
promoting any part of it to the product source of truth.

## Product Idea

Daft Prompt should be a local, research-oriented musical chat workspace.

The main surface is a conversation with an assistant that can answer questions
about known songs, build evidence-backed song profiles, and compose new musical
sketches from scratch or from structured traits taken from one or more
references.

The product is not a DAW, a dashboard, or a form-heavy generator. The user
should mostly type what they want:

- "What chords are in the chorus of this song?"
- "What scale would work over the guitar solo?"
- "Who sings this, and who wrote it?"
- "Use the drums from this song and the harmony from that one."
- "Make a new sketch with this groove but darker synths."

The assistant should not answer from free memory when musical evidence is
needed. It should use tools, cite or summarize evidence, preserve uncertainty,
and say when it does not have enough information.

## Product Decisions

### Chat Is The Orchestrator

The chat layer should become an LLM-based conversational agent with a tight
music-focused prompt and deterministic tools. The current regex-style routing is
useful as an MVP scaffold, but it is not enough for natural follow-ups,
multi-reference requests, Spanish/English phrasing, or nuanced clarification.

The chat LLM should:

- understand the user's musical intent;
- decide which tool to call;
- ask concise clarifying questions when a request is ambiguous;
- answer in bounded, evidence-based language;
- avoid hallucinating song facts, chords, lyrics, performers, or credits;
- translate user requests into structured analysis or composition tasks.

The chat LLM should not:

- scrape pages directly;
- analyze audio directly;
- compose every note directly;
- bypass deterministic profile/query/composition tools;
- present uncertain evidence as fact.

Tools keep the system grounded and prevent the chat context from being filled
with raw pages, full profiles, or large generated songs.

### Song Analysis Should Be Web-First

Extracting exact musical information from commercial audio is difficult. Demucs
stem separation is useful, but separation is not the same as understanding.
Guitar, piano, dense mixes, effects, bends, voicings, and solos are especially
hard to transcribe reliably from audio.

For known songs, web evidence is more likely to produce useful answers quickly:

- chords and progressions;
- key and BPM claims;
- section labels;
- lyrics with section headings when available;
- performer, writer, album, year, and genre metadata;
- tabs or instrument-specific hints;
- conflicting interpretations across sources.

The product should therefore move toward web-first song research. The assistant
should search selected sources, extract compact claims, fuse evidence, and build
a profile that can be queried later.

This is not the same as trusting the web blindly. Different pages may disagree
because of capo, transposition, simplified arrangements, live versions, user
errors, or different theoretical interpretations. The product should keep those
conflicts visible.

### Audio Remains A Complement

Local audio upload should not be the primary path for exact known-song facts,
but it remains valuable as a complementary tool.

Audio can help with:

- tempo and timing estimates;
- energy and density over time;
- approximate structure;
- stem separation;
- rough groove or instrument activity;
- checking whether web claims fit a specific recording;
- estimating missing data when web evidence is weak.

Audio-derived claims should be labeled as estimates. A local analyzer can say
"probably" or "roughly"; it should not claim exact guitar notes, exact drum
parts, or exact synth patches without strong evidence.

### Composition Remains Central

Composition is not a side quest. The long-term product should support both:

1. understanding songs; and
2. using that understanding to compose new sketches.

The current multi-agent composer is a valuable base: director, instrument
agents, shared `SongState`, negotiation requests, arbiter, and renderers. The
problem is not only prompt quality. The composer also needs stronger musical
constraints, more deterministic helpers, and a better representation of what is
being transferred from references.

Reference-guided composition should not depend on a vague string like
"inspired by X". The chat agent should build a structured `CompositionBrief`
from the user's request and one or more song profiles.

Examples:

- "Use the drums from X" should become drum groove traits.
- "Use the harmony from Y" should become harmonic traits.
- "Use the synths from Z" should become texture and timbre traits.
- "Use the form from W" should become section and energy traits.

For local research use, copying exact notes is not the main product concern.
The bigger concern is whether the system has reliable evidence and whether it
labels confidence honestly.

## How This Differs From The Current Repo

The current repo already contains several important pieces:

- a chat-first interface;
- web research endpoints;
- compact reference profiles;
- evidence-backed answering;
- a multi-agent composer;
- generated MIDI/MusicXML artifacts;
- playback and mixer controls;
- clean backend layering.

The repo is still missing the product shape described here:

- chat is still mostly deterministic routing, not an LLM tool-using agent;
- web research is generic and shallow, not source-specific and robust;
- the profile does not yet model a full song knowledge graph;
- lyrics, section-level chords, timestamps, instrument traits, and conflicts are
  not first-class enough;
- composition from reference is still mostly text guidance, not a structured
  `CompositionBrief`;
- instrument agents still have too much freedom and too few musical constraints;
- audio and web evidence are not yet fused into one profile.

## Functional Model

### SongKnowledgeProfile

`SongKnowledgeProfile` should become the main object for known songs. It should
represent what the system knows, where it came from, and how reliable it is.

Suggested fields:

- identity: title, artist, album, year, version, candidate matches;
- credits: performers, writers, producers, source-backed where possible;
- metadata: genre, tags, language, duration;
- tempo: candidates, confidence, sources;
- key: candidates, confidence, relative-key ambiguity, sources;
- meter: stated or estimated meter;
- sections: ordered `SongSectionProfile` entries;
- harmony: global progressions, section progressions, chord claims;
- lyrics: section-scoped text when available and appropriate for local use;
- instruments: guitar, bass, drums, keys, synths, vocals, other;
- traits: groove, energy, density, mood, arrangement, timbre notes;
- web evidence: source claims and snippets;
- audio evidence: optional local analysis claims;
- conflicts: disagreements between sources or between web and audio;
- confidence summary: what is strong, medium, weak, or missing.

The profile should be compact enough to pass summaries to an LLM, but detailed
enough that deterministic tools can answer common questions without asking the
LLM to infer from raw pages.

### SongSectionProfile

Sections are central because users ask about verses, choruses, solos, bridges,
and intros.

Suggested fields:

- name: intro, verse, pre-chorus, chorus, bridge, solo, outro, unknown;
- index/order;
- start and end timestamps when known;
- timestamp confidence and source;
- lyrics for the section when available;
- chords or progression for the section;
- key/mode override if the section modulates;
- energy and density;
- notable instruments or arrangement changes;
- source evidence and confidence.

Timestamps should be optional. Many web sources provide section labels and
lyrics but not timing. Audio can estimate timing, but those estimates should be
marked as such.

### EvidenceClaim

Every extracted fact should be stored as a claim, not as truth.

Suggested fields:

- claim type: tempo, key, chord progression, section, lyric, credit,
  instrumentation, groove, timbre, performer, writer, etc.;
- value;
- normalized value when applicable;
- song section or time range when applicable;
- source name and URL;
- extraction method: site parser, browser-rendered page, API, audio analyzer,
  manual fixture;
- confidence;
- short supporting snippet or locator;
- notes about transposition, capo, version, or ambiguity.

The assistant should answer from fused profiles, but claims should remain
available for traceability and debugging.

### Source Connectors

The generic scraper should be replaced or supplemented by source-specific
connectors. A small number of good connectors is better than broad shallow
scraping.

Each connector should:

- know how to search or resolve a song on that source;
- fetch pages through the appropriate mechanism;
- extract structured claims;
- avoid storing raw pages as product data;
- report blocked, unavailable, or low-quality pages explicitly;
- normalize output into `EvidenceClaim` records.

Some pages render with JavaScript. A basic HTTP fetcher will only see the
initial HTML and may miss the useful content. For selected sources, a
browser-based fetcher such as Playwright can be added behind the same port. It
should be optional because it is slower, heavier in Docker, and more fragile
against bot protection.

### EvidenceFuser

`EvidenceFuser` should combine claims into a profile while preserving conflict.

It should:

- group claims by type and section;
- normalize key names, chord labels, BPM values, and section labels;
- detect likely transposition or capo differences;
- detect version conflicts when possible;
- choose a best candidate only when evidence supports it;
- keep minority/conflicting claims visible;
- produce confidence labels for chat responses.

It should not silently flatten disagreement into a single answer.

### CompositionBrief

`CompositionBrief` should be the structured input to composition.

Suggested fields:

- user request;
- global constraints: genre, tempo, key, meter, length, mood;
- references used;
- transfer policy: which traits to use from which reference;
- harmonic guidance: chords, key, progression, confidence;
- rhythmic guidance: groove family, drum pattern, swing, density;
- form guidance: sections, energy, arrangement arc;
- instrumentation: required/optional instruments;
- instrument-specific requests: drums, bass, guitar, keys, synths, vocals;
- timbre traits: synth type, envelope, filter, effects, register, texture;
- forbidden or ignored traits;
- uncertainty notes.

The chat agent should build this brief before invoking the composer. The
composer should not have to infer all transfer rules from a free-text prompt.

## Composition Direction

### Keep The Multi-Agent Base

The existing composer should remain isolated:

```text
director
  -> instrument agents
  -> shared SongState negotiation
  -> arbiter
  -> render artifacts
```

The `SongState` should remain the canonical generated-song representation. MIDI
and MusicXML are exports.

### Strengthen The Director

The director should decide more than roster, key, BPM, and chord progression.
It should produce a real arrangement plan:

- groove family;
- section energy and density;
- primary motif or hook idea;
- who leads each section;
- what each reference contributes;
- instrument roles and constraints;
- phrase structure;
- where fills, drops, or transitions happen;
- whether the piece should be sparse, dense, repetitive, evolving, etc.

The director output should be structured enough that instrument agents receive
clear jobs instead of broad stylistic wishes.

### Narrow Instrument Agent Freedom

Instrument agents should receive specific constraints:

- drums: pattern, density, fills, swing, kit role;
- bass: roots, approach notes, rhythm relationship to kick, register;
- harmony: voicings, rhythm, register, density, chord tones;
- melody: scale, motif, range, repetition, tension and resolution;
- guitar: strumming/picking pattern, chord shapes or register, articulation;
- synths: role, texture, waveform family, filter/envelope/effects traits.

The goal is not to remove creativity. The goal is to stop each agent from
inventing an incompatible interpretation of the same song.

### Add Deterministic Musical Helpers

Some musical material should not require an LLM call every time.

Useful helpers:

- drum pattern generator;
- bass pattern generator from groove and chords;
- chord voicing generator;
- scale and chord-tone helpers;
- motif transformation helpers;
- density and range validators;
- timing quantization and humanization helpers.

The LLM can choose and adapt these helpers, but deterministic functions should
handle repetitive symbolic work where possible.

### Improve Reference Transfer

The composer should support mixing references by dimension:

- drums from one song;
- harmony from another;
- synth texture from another;
- form from another;
- mood or energy from another.

The chat agent must resolve ambiguity. If the user says "make it like these two
songs" without specifying what to transfer, the system should ask or apply a
documented default.

### Separate Composition Quality From Playback Quality

A symbolic song can be musically reasonable and still sound bad if rendered
with poor General MIDI patches or weak soundfonts. This should be treated as a
separate risk.

Composition work should improve notes, rhythm, arrangement, and structure.
Playback/render work should improve timbre, synth patches, samples, dynamics,
and mix realism.

## Implementation Plan

The work should be implemented as three connected tracks:

- Track A: web-first profiles and research evidence;
- Track B: LLM chat orchestration with deterministic tools;
- Track C: composition from structured traits and briefs.

Tracks are ordered deliberately. Track C depends on the profile and brief
contracts from Track A. Track B can start after the profile query tools exist,
but it should not invent data that the tools cannot provide.

Implementation should happen on a new branch, not directly on `develop` or
`main`. Recommended branch name: `product-direction`.

Each phase should end with a small commit before starting the next phase. Commits
should stay phase-scoped so the history remains reviewable and it is easy to
roll back or inspect one conceptual change at a time.

### Phase 0: Baseline And Safety

Goal: establish the current behavior that must not regress.

- [ ] Record the current branch and current tracked/untracked files before
  changing code.
- [ ] Create and switch to the implementation branch before code changes.
- [ ] Confirm the existing public endpoints that must keep working:
  `/chat`, `/references/research`, `/references/research/stream`,
  `/compose/stream`, `/health`, and any enabled upload/audio endpoints on the
  active branch.
- [ ] Run or document the current backend and frontend checks for the branch.
- [ ] Confirm that `PRODUCT.md` and `DESIGN.md` remain unchanged until this
  direction document is explicitly promoted.
- [ ] Identify which existing tests cover research, chat, answer generation,
  composition streaming, and composer validation.

Repo areas: root docs, `apps/api/tests/`, `apps/web/lib/`.

Verification:

- [ ] `git status --short` is understood before implementation starts.
- [ ] The branch is not `develop`, `main`, or another shared integration branch.
- [ ] Existing tests to protect are listed in the implementation PR/notes.

Done when: the implementer knows what compatibility must be preserved and has a
baseline test list, and the branch is ready for phase-scoped commits.

### Phase 1: Domain Contracts

Goal: add the data shapes needed for web-first song knowledge and structured
composition without wiring behavior yet.

- [ ] Add domain models for `SongKnowledgeProfile`, `SongSectionProfile`,
  `EvidenceClaim`, `EvidenceConflict`, `InstrumentTrait`, and
  `CompositionBrief`.
- [ ] Keep `ReferenceProfile` compatible with current API responses. Either add
  a compatibility field pointing to the richer profile or provide explicit
  adapters between `SongKnowledgeProfile` and `ReferenceProfile`.
- [ ] Define confidence labels, source attribution fields, extraction method,
  and optional timestamp confidence.
- [ ] Model lyrics and tabs as section-scoped evidence, not as raw page dumps.
- [ ] Model missing data explicitly so chat can say "I do not have that yet"
  without guessing.
- [ ] Add small hand-authored fixtures for two or three known songs, including
  at least one conflict case and one incomplete-data case.

Repo areas: `apps/api/music_assistant/domain/`, `apps/api/tests/fixtures/`,
`apps/web/lib/types.ts` if public response types change.

Verification:

- [ ] Domain model tests cover required fields, optional fields, confidence
  labels, conflicts, and JSON serialization.
- [ ] Existing `ReferenceProfile` tests still pass or are updated through a
  deliberate compatibility adapter.

Done when: a profile fixture can represent identity, sections, chords, lyrics,
metadata, source claims, conflicts, and composition traits without needing raw
HTML or free-form LLM prose.

### Phase 2: Web Connector Contract

Goal: define one interface for source-specific song research connectors.

- [ ] Add a source connector port that accepts a resolved song query or search
  candidate and returns `EvidenceClaim` records plus explicit failure notes.
- [ ] Keep fetching/parsing details out of domain and application layers.
- [ ] Require each connector to report source name, URL, extraction method, and
  whether the page was fetched, blocked, empty, JS-rendered, or unsupported.
- [ ] Add fake connectors for tests: one successful, one conflicting, one
  blocked, and one empty/JS-only.
- [ ] Keep the existing generic research path available until the new connector
  pipeline is wired.

Repo areas: `apps/api/music_assistant/ports/`,
`apps/api/music_assistant/infrastructure/web_research/`,
`apps/api/tests/`.

Verification:

- [ ] Tests prove fake connectors return normalized claim objects and explicit
  failure notes.
- [ ] Architecture tests confirm application/domain code does not import
  concrete connector implementations.

Done when: a new source can be added by implementing the connector port without
changing chat, fusion, or composition code.

### Phase 3: First Source Connectors

Goal: replace broad shallow scraping with a small number of source-specific
connectors.

- [ ] Choose two initial sources before attempting four or five. Pick sources
  that provide different useful evidence, such as metadata plus chords.
- [ ] Implement connector-specific search/resolve/parsing for those sources.
- [ ] Use saved HTML fixtures for parser tests rather than live network tests.
- [ ] Return structured claims for supported data: key, BPM, chords, sections,
  lyrics snippets/sections, credits, instrumentation, or traits when available.
- [ ] Return explicit unsupported notes for pages that block access, contain no
  useful claims, or require JavaScript rendering.
- [ ] Do not add Playwright/browser fetching unless one selected source cannot
  work without it and the added Docker/runtime cost is accepted.

Repo areas: `apps/api/music_assistant/infrastructure/web_research/`,
`apps/api/tests/fixtures/`, `apps/api/tests/`.

Verification:

- [ ] Each connector has fixture-based tests for successful extraction.
- [ ] Each connector has at least one test for blocked/empty/unparseable input.
- [ ] No connector tests depend on the network.

Done when: the pipeline can extract useful claims from two real source formats
through deterministic parser tests.

### Phase 4: Evidence Fusion Into SongKnowledgeProfile

Goal: combine source claims into a profile while preserving uncertainty.

- [ ] Group claims by song identity, claim type, section, and source.
- [ ] Normalize BPM values, key labels, chord symbols, section names, source
  names, and obvious capo/transposition hints.
- [ ] Produce best candidates only when evidence supports them.
- [ ] Preserve conflicts when sources disagree on key, BPM, chords, section
  names, lyrics structure, credits, or version.
- [ ] Build `SongSectionProfile` entries when sources expose sections or
  section-like headings.
- [ ] Associate chords and lyrics to sections only when source formatting
  supports it.
- [ ] Leave timestamps empty unless a source provides them or audio enrichment
  later estimates them with confidence.

Repo areas: `apps/api/music_assistant/infrastructure/web_research/fusion.py`,
domain models, fusion tests.

Verification:

- [ ] Fusion tests cover matching claims, conflicting claims, transposed/capo
  interpretations, incomplete profiles, and section-level chords/lyrics.
- [ ] Tests prove timestamps are not fabricated when no timing evidence exists.

Done when: a list of claims can become a traceable `SongKnowledgeProfile` with
best-known values, conflicts, and missing-data markers.

### Phase 5: Research Use Case And API Compatibility

Goal: wire the new research pipeline without breaking existing API callers.

- [ ] Update `ResearchReference` or add a sibling use case to call source
  connectors and the fuser.
- [ ] Decide in code, not ad hoc in routes, whether `/references/research`
  returns a rich profile directly or adapts it to the existing
  `ReferenceProfile` response.
- [ ] Keep `/references/research` and `/references/research/stream` behavior
  stable for the frontend.
- [ ] Include source progress states that map cleanly to existing SSE progress
  events.
- [ ] Persist the resulting profile in the in-memory reference store or a
  compatible profile store.

Repo areas: `apps/api/music_assistant/application/`,
`apps/api/music_assistant/interfaces/`,
`apps/api/music_assistant/infrastructure/storage/`.

Verification:

- [ ] API tests cover normal research, no-claims research, blocked source, and
  conflicting source outputs.
- [ ] Existing frontend route proxies do not need UI changes for basic research.

Done when: the current research endpoints use the richer pipeline and existing
frontend calls still receive a usable response.

### Phase 6: Profile Q&A Tools

Goal: add deterministic query tools so the chat LLM does not need to reason over
raw profiles.

- [ ] Add profile query functions for key/BPM, chords, sections, lyrics by
  section, metadata/credits, instrumentation, conflicts, and missing data.
- [ ] Make each query return compact evidence summaries with source/confidence.
- [ ] Ensure queries distinguish web evidence, audio evidence, and inference.
- [ ] Preserve the existing deterministic answer path as a fallback or test
  oracle.
- [ ] Add "not enough evidence" responses for unsupported questions.

Repo areas: `apps/api/music_assistant/application/`,
`apps/api/music_assistant/infrastructure/explainer/`,
`apps/api/tests/`.

Verification:

- [ ] Unit tests cover every query function without any LLM.
- [ ] Tests prove the tools do not invent unavailable section lyrics, solo
  notes, performer credits, or timestamps.

Done when: common music questions can be answered from a profile by deterministic
tools alone.

### Phase 7: Chat LLM Tool Orchestrator

Goal: make chat conversational while keeping answers grounded in tools.

- [ ] Add a music-focused chat prompt that constrains the assistant to research,
  profile Q&A, composition, optional audio analysis, and concise clarification.
- [ ] Wrap or replace the regex router with an LLM tool orchestrator.
- [ ] Expose tools for song research, current profile lookup, profile Q&A,
  `CompositionBrief` creation, composition, and optional audio enrichment.
- [ ] Keep tool outputs compact and avoid placing raw HTML, full lyrics dumps,
  or full generated songs in the chat context.
- [ ] Require the final response to say whether claims came from web evidence,
  audio estimates, or inference when that distinction matters.
- [ ] Ask one short clarification when a multi-reference or trait-transfer
  request is ambiguous.
- [ ] Keep an off-topic refusal path for non-music requests.

Repo areas: `apps/api/music_assistant/application/chat_music.py`,
LLM provider adapters, chat tests.

Verification:

- [ ] Tests with fake LLM/tool calls cover research, Q&A, compose from scratch,
  compose from references, clarification, and off-topic refusal.
- [ ] Tests prove no LLM/provider call is needed for deterministic profile Q&A
  when using the fallback path.

Done when: chat can feel conversational but still routes through explicit tools
and evidence.

### Phase 8: Optional Audio Enrichment

Goal: keep audio useful without making it responsible for exact known-song
transcription.

- [ ] Keep upload/audio analysis as an optional tool where supported by the
  active branch.
- [ ] Convert audio-derived tempo, key, structure, energy, stems, and rough
  activity into `EvidenceClaim` records.
- [ ] Fuse audio claims with web claims without overwriting source conflicts.
- [ ] Label audio-only chord, note, instrument, and section guesses as
  approximate.
- [ ] Add profile notes when audio and web evidence disagree.

Repo areas: audio analyzer adapters, `AnalyzeReference`, fusion, tests.

Verification:

- [ ] Tests cover audio-only enrichment, web/audio agreement, web/audio
  conflict, and low-confidence audio estimates.
- [ ] Upload/audio API tests continue to pass if the active branch exposes
  upload endpoints.

Done when: local audio can enrich a song profile but cannot silently become a
fake source of exact truth.

### Phase 9: CompositionBrief Builder

Goal: turn user requests plus profiles into a structured composition contract.

- [ ] Add an application service that builds `CompositionBrief` from a message,
  selected profiles, and optional chat clarification state.
- [ ] Support composition from scratch by producing a brief with no references.
- [ ] Support one-reference prompts such as "use this song's drums".
- [ ] Support multi-reference prompts such as "drums from X and harmony from Y".
- [ ] Populate transfer policy explicitly: which reference contributes which
  trait.
- [ ] Include uncertainty notes for weak or missing traits.
- [ ] Return a clarification request instead of guessing when the requested
  transfer dimension is ambiguous.

Repo areas: `apps/api/music_assistant/application/`,
domain models, tests.

Verification:

- [ ] Tests cover scratch brief, single-reference brief, multi-reference brief,
  missing trait, conflicting references, and ambiguous request.

Done when: composition can receive a deterministic brief instead of parsing
reference intent from prose.

### Phase 10: Composer Consumes CompositionBrief

Goal: adapt the multi-agent composer to structured briefs while preserving
existing composition.

- [ ] Update the composition application service to accept either a text prompt
  or a `CompositionBrief`.
- [ ] Update the director prompt/schema to consume brief fields: global
  constraints, form, groove, harmony, references, and transfer policy.
- [ ] Preserve composition from scratch by converting the user prompt into a
  no-reference brief.
- [ ] Pass selected reference traits to instrument agents through structured
  state or compact prompt fields.
- [ ] Keep existing `SongState` as the canonical generated song output.

Repo areas: `apps/api/music_assistant/application/compose_song.py`,
`apps/api/music_assistant/agents/`, `apps/api/music_assistant/graph.py`.

Verification:

- [ ] Tests cover existing compose behavior, brief-based compose behavior, and
  generated `SongState` validation.
- [ ] Tests prove "inspired by X" is no longer the only reference guidance path.

Done when: the composer can use structured reference traits without breaking
current text-prompt composition.

### Phase 11: Instrument Constraints And Helpers

Goal: improve musical coherence by combining LLM agents with deterministic
musical helpers.

- [ ] Add or expand deterministic drum pattern helpers with editable fills and
  density controls.
- [ ] Add bass helpers that use chord roots, approach tones, register, and
  relationship to kick/groove.
- [ ] Add harmony helpers for chord voicings by register, density, and rhythm.
- [ ] Add melody constraints for scale, motif, range, repetition, tension, and
  resolution.
- [ ] Add synth/timbre traits as structured constraints even if playback only
  approximates them at first.
- [ ] Tighten validators for empty parts, invalid timing, range violations,
  impossible drum/pitched-note treatment, and harmonic fit.

Repo areas: `apps/api/music_assistant/music/`,
`apps/api/music_assistant/agents/instrument.py`,
composition tests.

Verification:

- [ ] Unit tests cover each helper independently.
- [ ] Agent tests prove constraints are present in prompts or structured input.
- [ ] Validator tests catch invalid helper or agent output.

Done when: instrument parts are guided by musical constraints rather than broad
"compose your full part" prompts alone.

### Phase 12: Reference Mixing

Goal: support user requests that combine traits from multiple songs.

- [ ] Allow a `CompositionBrief` to reference multiple profiles at once.
- [ ] Detect conflicts in requested tempo, meter, key, harmony, groove, or form.
- [ ] Define defaults for vague requests:
  - use tempo/form/energy from the strongest matching reference;
  - use explicitly requested dimensions first;
  - ask if two references conflict on a dimension the user requested.
- [ ] Preserve a clear explanation of which traits came from which song.
- [ ] Do not copy or transfer a trait that is missing or low confidence without
  saying so.

Repo areas: `CompositionBrief` builder, chat orchestrator, composer director,
tests.

Verification:

- [ ] Tests cover compatible multi-reference prompts, conflicting references,
  missing traits, and clarification behavior.

Done when: requests like "use the drums from X, harmony from Y, synths from Z"
produce a traceable brief and either compose or ask a precise question.

### Phase 13: Playback Improvements Only When Blocking

Goal: avoid letting UI/playback work derail core functionality.

- [ ] Keep generated MIDI and controllable per-instrument parts working.
- [ ] Improve render/playback only when poor output prevents validating
  composition behavior.
- [ ] Defer advanced UI, DAW-like editing, production-grade mixing, and realistic
  synth rendering until the profile/chat/composition contracts work.
- [ ] Document any playback limitation separately from symbolic composition
  limitations.

Repo areas: renderers, playback helpers, frontend only when required.

Verification:

- [ ] Existing MIDI export/playback checks still pass when touched.
- [ ] Any playback change has a focused test or manual smoke note.

Done when: playback remains good enough to inspect generated songs without
becoming the main implementation track.

### Phase 14: Evaluation Suite

Goal: create repeatable examples that prove the product works end to end.

- [ ] Add local fixtures for a small set of known songs with expected metadata,
  chords, sections, conflicts, and missing data.
- [ ] Add expected profile Q&A answers for common questions.
- [ ] Add expected `CompositionBrief` outputs for scratch, single-reference, and
  multi-reference prompts.
- [ ] Add symbolic composition checks for drums, bass, harmony, melody, and
  reference transfer.
- [ ] Add "not enough data" scenarios so uncertainty behavior is tested.

Repo areas: `apps/api/tests/fixtures/`, backend tests, frontend type tests only
when public contracts change.

Verification:

- [ ] A single documented command or small command set runs the evaluation suite
  without network access.
- [ ] Fixtures avoid private audio files, secrets, and generated commercial
  assets.

Done when: another developer can run local tests and see whether research,
chat, profiles, briefs, and composition still match the intended behavior.

## Testing Strategy

Tests should prove behavior at the layer where it lives.

Research tests:

- a connector extracts claims from representative saved HTML;
- blocked or JS-empty pages return explicit failure notes;
- fuser combines matching claims;
- fuser preserves conflicting key, chord, BPM, or section claims;
- section-level lyrics and chords are associated when source format supports it;
- missing timestamps remain missing instead of becoming fake precision.

Chat tests:

- chat calls research when asked to analyze a known song;
- chat answers from an existing profile without inventing;
- chat asks for clarification on ambiguous multi-reference requests;
- chat preserves uncertainty in its final response;
- chat refuses or redirects off-topic requests.

Composition tests:

- `CompositionBrief` represents "drums from X and harmony from Y";
- composition from scratch still works without references;
- composition from reference uses structured traits, not only a prose prompt;
- director produces groove, density, motif, roles, and transfer policy;
- instrument agents respect constraints for drums, bass, harmony, and melody;
- generated `SongState` validates and contains playable parts.

Audio tests:

- upload/audio remains available when enabled;
- audio claims can enrich a profile;
- audio/web conflicts are preserved;
- low-confidence audio estimates are labeled as approximate.

## Risks And Constraints

- Exact transcription from audio is hard, especially for guitar, piano, dense
  mixes, effects, bends, voicings, and solos.
- Web evidence can be wrong, incomplete, blocked, or inconsistent.
- JavaScript-rendered pages may require browser automation.
- Source-specific scrapers are more reliable but require maintenance.
- Lyrics and tabs should be treated carefully and kept local/research-oriented.
- LLM chat can still hallucinate unless forced through tools and evidence.
- Multi-agent composition can be expensive and slow without deterministic
  helpers and compact prompts.
- MIDI playback quality can make good symbolic output sound weak.

## Near-Term Recommendation

The fastest path to a useful product is:

1. build the chat LLM with tools;
2. make web-first song profiles reliable;
3. answer questions from evidence;
4. then feed those profiles into structured composition.

Composition remains a core feature, but it will become much stronger after the
analysis side can produce trustworthy traits.
