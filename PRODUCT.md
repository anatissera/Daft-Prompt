# Product - Daft Prompt

Daft Prompt is a chat-first AI music assistant for understanding songs,
learning playable parts, and composing or editing MIDI music.

The product answers song and music questions from scraped public evidence such
as Songsterr, tab/chord pages, metadata pages, artist/album information, and
style or corpus references. It can render requested playable views such as
guitar tabs, bass tabs, drum tabs, piano keys, chord charts, and piano rolls.
It can also compose original MIDI-first sketches through a dynamic multi-agent
band system.

This document is the product source of truth.

## Product Goal

The MVP goal is:

> A chat-first assistant that answers music questions from attributed public
> evidence, renders playable teaching views when useful, and composes or edits
> generated MIDI music through a multi-agent band.

The product should feel like a small conversational studio and teacher, not a
dashboard, a form-heavy generator, a full DAW, or a file-analysis utility.

## Core User

The initial user is a music-curious technical user: a student, musician,
producer, or course evaluator who wants grounded musical answers and playable
generated output.

They value:

- natural chat instead of mode selection;
- visible sources and uncertainty for song claims;
- practical playable tabs, keys, rolls, and chord guidance;
- original MIDI sketches that can be heard, exported, and edited;
- clear but compact agent transparency;
- low setup friction.

## MVP Capabilities

### 1. Conversational Chat

Chat is the primary interface.

The user can write naturally:

- "What chords are in One More Time?"
- "How do I play the main bass part?"
- "What scale should I improvise over the chorus?"
- "Compose a French-house groove with robot disco energy."
- "Make something similar to Twenty One Pilots, but with a funk bassline."
- "Keep the drums exactly and change the piano chords."

The assistant should route the request to the right use case:

- identify the referenced song, artist, album, genre, or prior generated song;
- fetch or reuse public evidence;
- answer a music theory or production question from evidence;
- render requested playable tabs, keys, rolls, or chord charts;
- build or reuse an artist/band style profile;
- compose from scratch or from evidence;
- edit an existing generated `SongState`;
- ask one concise clarification when required.

The user should not need to choose a mode first.

### 2. Evidence-Based Song Knowledge

Known-song knowledge must come from evidence connectors, not user-uploaded file
analysis.

Preferred sources include:

- Songsterr tab, chord, and metadata evidence;
- public chord/tab pages;
- metadata pages for artist, album, writer, performer, year, genre, and BPM/key
  claims;
- style and corpus references that can inform composition.

The product should build compact `SongKnowledgeProfile` objects that preserve:

- title, artist, album, writers, year, and version when available;
- likely key, tempo, meter, sections, and chord progressions;
- instrument-specific playable parts from tab evidence;
- instrumentation, groove, arrangement, tone, and production claims;
- source attribution, conflicts, and confidence.

The assistant must be honest about source quality:

- "Songsterr shows..."
- "This tab source suggests..."
- "A practical scale choice would be..."
- "I would treat this progression as probably..."

Do not claim perfect analysis or present a single scraped source as absolute
truth when confidence is limited.

### 3. Playable Teaching Views

When the user asks how to play something, the answer should combine concise
musical explanation with a playable representation.

Supported teaching views should include, as evidence allows:

- guitar tabs;
- bass tabs;
- drum tabs;
- piano keys;
- piano roll;
- chord chart;
- rhythm grid.

These views are contextual result blocks. They should not replace chat as the
main surface.

### 4. Artist/Band Style Profiles

For prompts like "compose something similar to this band", the app should build
an `ArtistStyleProfile`.

The profile should select representative evidence using a mix of:

- popular or canonical songs;
- songs with useful Songsterr/tab evidence;
- songs specifically mentioned by the user;
- genre and corpus references when source evidence is thin.

The resulting profile should summarize:

- genre and subgenre tags;
- tempo range, meter, key, mode, and harmonic habits;
- common chord progressions or scale choices;
- typical instruments and roles;
- drum, bass, guitar, keys, synth, hook, and production traits;
- section/form and energy patterns;
- sources and confidence.

For artist similarity prompts, the composer should use the compact
`ArtistStyleProfile` through a `CompositionBrief`. It should not copy a single
song unless the user explicitly asks for a specific transformation.

### 5. Composition And Editing

Composition is MIDI-first and uses the existing multi-agent band direction:

- an orchestrator/director owns global constraints;
- instrument or role agents compose specialized parts;
- the number of instruments can be dynamic;
- agents communicate through shared `SongState` and structured negotiation
  requests;
- an arbiter/reviewer validates the result;
- renderers create playable artifacts.

Composition should respect:

- requested genre, tempo, meter, key, scale, and form;
- requested instruments and exact preservation constraints;
- referenced drum patterns, riffs, tabs, chords, or style traits when the user
  asks for them;
- `SongKnowledgeProfile` and `ArtistStyleProfile` evidence supplied through a
  compact `CompositionBrief`.

Generated-song edits should preserve unaffected tracks when possible.

Useful edits include:

- change guitar tone;
- change piano chords;
- regenerate only bass;
- keep drums exactly;
- make it faster;
- transpose to another key;
- make it more like a given song, artist, album, or genre;
- simplify a part for a beginner.

### 6. Playable Output

Generated songs should be playable in the UI.

The MVP should support:

- play/stop;
- per-instrument mute/solo after a song exists;
- MIDI export;
- generated or browser-rendered audio playback;
- MP3 export when the playback path supports it.

The mixer is useful after generation, but it should not dominate the initial
chat experience.

### 7. Agent Transparency

The user should be able to understand what happened without reading raw logs.

The UI should expose, compactly:

- which evidence connectors were used;
- what claims were found and how confident they are;
- what playable views were rendered;
- which agents participated in composition or editing;
- important negotiation requests and resolutions;
- final composition status.

This belongs in contextual details, not as the main interaction.

## Non-Goals

The MVP does not support:

- user-uploaded file analysis as a product path;
- local audio analysis as a supported song-knowledge source;
- YouTube download, conversion, or commercial-song acquisition;
- persistent user accounts;
- a database;
- long-term chat history;
- collaborative editing;
- production-grade audio mastering;
- perfect chord, tab, stem, or tone extraction;
- a full DAW interface;
- notation as the primary experience.

Legacy audio-analysis modules may exist during migration, but they are not part
of the supported Daft Prompt product surface.

## Product Principles

### Chat First

The user should mostly type what they want. Buttons and toggles should appear
only when they reduce friction.

Useful controls:

- send message;
- play/stop;
- mute/solo generated instruments;
- export MIDI or audio;
- show/hide evidence, tabs, roll, and agent details.

Avoid permanent panels full of switches. When configuration is needed, ask
conversationally.

### Evidence Over Memory

Musical explanations should be grounded in tool outputs and source claims. The
assistant can interpret, but it must distinguish interpretation from sourced or
estimated facts.

### Source Attribution And Uncertainty

Every nontrivial song claim should retain where it came from and how reliable it
appears. Conflicts should stay visible instead of being flattened into certainty.

### Reference As Traits, Not Copying

Using a song, artist, album, or genre as a reference should mean transferring
explicitly requested traits:

- groove;
- harmonic language;
- section shape;
- instrumentation;
- energy;
- tone or production choices;
- playable part constraints.

Default behavior should be transformative and original.

### Simplicity First

Keep the application local-friendly and production-minded. Do not add a
database, event bus, microservice split, or dashboard layer unless the product
requirements clearly change.

## Architecture Expectations

The repository should keep a clean separation of responsibilities:

- UI renders chat, evidence, tabs, piano roll, playback, mixer, and compact
  details.
- API boundaries accept chat, composition, evidence, render, and edit requests.
- Application use cases orchestrate behavior.
- Domain models represent song knowledge, style profiles, composition briefs,
  playable parts, tones, and generated song state.
- Ports define LLM, source connector, storage, renderer, and composition
  dependencies.
- Infrastructure adapters implement scraping, provider, storage, and rendering
  details.
- Composition agents consume compact domain profiles and briefs, never raw
  scraped pages or provider-specific responses.

## MVP Success Criteria

The MVP is successful when a user can:

1. Open the app locally.
2. Chat naturally with the assistant.
3. Ask about a known song and receive an attributed, uncertainty-aware answer.
4. Ask how to play a part and see a relevant tab, keys view, chord chart, or
   piano roll when evidence supports it.
5. Ask for an original composition from scratch.
6. Ask for a composition using song, artist, album, or genre evidence.
7. Hear the generated result.
8. Mute or solo generated instruments.
9. Request a natural-language edit and keep unaffected parts intact when
   possible.
10. Understand, at a high level, which evidence connectors and agents were
    involved.
