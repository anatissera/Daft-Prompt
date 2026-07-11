# Daft Prompt Product Convergence Plan

Goal: turn the current repo into Daft Prompt, a chat-first AI music assistant for song understanding, instrument-specific learning, and multi-agent MIDI composition.

This plan supersedes any MVP direction that treats local audio analysis or user-uploaded files as part of the product. The app should not expose a way for the user to upload a file for analysis, and the backend should not keep file-upload analysis routes as a supported path. Song understanding should come from evidence connectors such as Songsterr tabs, chord/metadata pages, artist/album references, and other scrapeable public sources. The assistant must be honest about source quality and uncertainty.

## Product North Star

Daft Prompt is a conversational music teacher, producer, and composition partner.

The user asks in natural language:

- Which chords does this song have?
- In which scale should I improvise?
- How do I play this part on drums, guitar, bass, or piano?
- Compose a new song with exactly this drum pattern.
- Compose something similar to this song, artist, album, or genre.
- Recreate this song in another genre while preserving chosen traits.
- Change this guitar sound.
- Change the piano chords.

The app should answer like a knowledgeable music teacher or producer: natural, grounded, concise, and musically useful. The interface is chat-first. Technical panels, piano roll, tabs, mixer, and agent activity exist only as contextual support.

## Branch Strategy

Only consider:

- `product-direction`
- `giner`

Use `product-direction` as the base for product polish and chat/research continuity, because it contains many fixes that `giner` does not have.

Implementation must happen on a new branch created from `product-direction`. Do not implement directly on `product-direction` or `giner`.

Required git workflow:

- create a new branch with a descriptive name, for example `feat/daft-prompt-convergence`;
- make small atomic commits, each representing one coherent product or technical change;
- write self-explanatory commit messages that describe the change without needing external context;
- run the relevant focused checks before each commit when practical;
- push the branch after each commit so progress is backed up and reviewable;
- never squash unrelated phases into one large commit.

Cherry-pick or port from `giner` selectively:

- band-agent research/skeleton/fill composition pipeline;
- semantic patch vocabulary;
- corpus/style grounding;
- deterministic drum and fill fallbacks;
- known-song evidence connectors;
- any useful artist/style research hooks that can feed a compact composition profile;
- piano roll;
- SF3/spessasynth playback;
- MP3 export respecting mute/solo;
- pipeline/agent visualizations;
- Daft/robotic visual direction if it is tasteful.

Do not blindly merge `giner` into `product-direction`; it is missing many later product-direction fixes.

## Architecture Direction

Keep clean architecture:

```text
FastAPI route
  -> application use case
  -> domain models
  -> ports
  -> infrastructure adapters
```

Core bounded contexts:

- `SongKnowledgeProfile`: evidence-backed facts and claims about a known song, artist, album, or genre.
- `ArtistStyleProfile`: aggregated evidence from representative songs by an artist/band, used for "compose like this band" requests.
- `PlayableInstruction`: requested part rendered as guitar/bass tab, drum tab, piano keys, chord chart, or piano roll.
- `SongState`: canonical generated composition format.
- `CompositionBrief`: compact instructions for the composer derived from chat plus optional song/style evidence.

Avoid making raw scraped HTML, provider responses, or local audio-derived data part of the domain contract.

## Evidence-Based Song Knowledge

Prioritize connector-based evidence over local analysis.

Song knowledge should include, when available:

- title, artist, album, writers, year;
- likely key, tempo, meter;
- chord progressions by section;
- Songsterr or tab-derived instrument parts;
- guitar/bass/piano/drum playable tabs, including full commercial song tabs for this academic classroom project;
- instrumentation and arrangement notes;
- pedals, tone, amps, synths, and production hints;
- genre/style references;
- sources and confidence.

Use probabilistic language unless a source is authoritative:

- "Songsterr shows..."
- "This tab source suggests..."
- "A practical scale choice would be..."
- "I would treat the chorus as probably..."

Do not claim perfect extraction.

## Artist/Band Style Profiling

For prompts like "compose something similar to Twenty One Pilots", the app should build an `ArtistStyleProfile` in parallel with the normal chat/composition flow.

This is the bridge between:

- `product-direction`: research continuity, named-song/artist lookup, evidence retention across turns, and chat-first behavior;
- `giner`: style-grounded composition, corpus/style priors, known-song evidence connectors, and band-agent orchestration.

The profile should not blindly average an artist's top songs. It should select representative evidence using a mix of:

- most listened or most popular songs;
- songs with usable Songsterr/tab evidence;
- songs that are musically representative of the requested artist/band;
- specific songs the user mentioned in the conversation.

The resulting `ArtistStyleProfile` should include:

- artist or band name;
- representative songs used as evidence;
- genre and subgenre tags;
- tempo range and common meter;
- common keys, modes, or scale choices;
- common chord progressions or harmonic habits;
- typical instruments and roles;
- drum groove traits;
- bass traits;
- guitar/keys/synth traits;
- melody and hook traits;
- production/tone traits;
- section/form traits;
- source list and confidence.

For example, a Twenty One Pilots profile might describe sparse verses, punchy drums, melodic bass, piano/synth hooks, alt-pop/rap-rock energy, minor/modal harmony, and big chorus contrast. The composer should use those traits without copying a specific song unless the user asks for a specific transformation.

Implementation guidance:

- Run artist profiling in parallel with specific song evidence lookup when possible.
- Cache the profile in chat context so follow-up prompts can say "make it more like them" without re-fetching everything.
- Feed only the compact `ArtistStyleProfile` into `CompositionBrief`, not raw pages or full tabs.
- If evidence is thin, fall back to LLM/common-knowledge style priors but mark confidence lower.
- Use Songsterr as the first source when it provides usable tabs/chords/metadata; add fallback sources only when needed.

## Chat Agent

Implement or refine a LangGraph chat router.

The main agent should classify the user request into tool paths:

- identify song/entity;
- build or refresh artist/band style profile;
- fetch song evidence;
- answer music theory or production question;
- render a requested short playable part;
- compose from scratch;
- compose from song/artist/album/genre evidence;
- edit an existing generated `SongState`;
- ask one clarification when required.

The user should not choose a mode first.

The main agent should preserve conversational context:

- current known song;
- current artist/band style profile;
- current generated song;
- selected instrument or section;
- constraints already accepted by the user;
- evidence already gathered.

## Composition Agent System

Composition should use an agentic band model.

Required behavior:

- The orchestrator/director owns global constraints: genre, tempo, meter, key, scale, chord plan, form, instrumentation, energy, source evidence, and user constraints.
- Instrument agents specialize by instrument or musical role.
- The number of instruments is dynamic and chosen by the orchestrator, not hardcoded.
- Agents communicate through structured shared state and negotiation requests.
- A final reviewer/arbiter validates the result and can trigger another iteration if the result violates the brief.
- Output is MIDI-first and keeps tracks separated for playback, editing, mixer, export, and later sound changes.

Composition must respect:

- requested genre;
- requested instruments;
- tempo and meter;
- chords and scales;
- referenced drum patterns, melodies, riffs, tabs, or style traits when the user asks for them;
- artist/band profile traits when the user asks for "similar to this band/artist";
- transformation requests such as "same chords but different genre" or "same drums, new song."

Composition must not be generic. If evidence is available, it should shape arrangement, rhythm, harmony, and instrumentation.

## Editing Generated Music

Support natural-language edits over generated MIDI/SongState:

- change guitar tone;
- change piano chords;
- regenerate only bass;
- keep drums exactly;
- make it faster;
- transpose to another key;
- make it more like a given song or genre;
- simplify a part for a beginner.

Edits should preserve unaffected tracks when possible.

## Playable Teaching Views

The UI can render requested song parts and full tabs. Copyright is not a constraint for this classroom academic project, so full commercial song tabs may be displayed when the source provides them.

- guitar tabs;
- bass tabs;
- drum tabs;
- piano keys;
- piano roll;
- chord chart;
- rhythm grid.

These views appear only when useful or requested.

Example:

User: "How do I play the main drum groove?"

Assistant answer:

- short natural explanation;
- count or sticking pattern;
- compact or full drum tab depending on the request;
- optional playback of the requested part.

## UI Direction

Daft Prompt should feel robotic, futuristic, musical, and modern, inspired by Daft Punk without becoming gimmicky.

Use:

- dark metallic base;
- restrained chrome/gold accents;
- clean typography;
- subtle animations for streaming, agent activity, and playback;
- chat as the main surface;
- contextual panels for evidence, tabs, piano roll, and mixer.

Avoid:

- dashboard-first layout;
- oversized marketing hero;
- permanent control walls;
- raw JSON as primary UI;
- overdesigned neon clutter.

## Implementation Phases

### Phase 1: Product Truth Alignment

- Update `PRODUCT.md`, `DESIGN.md`, `docs/architecture.md`, and `AGENTS.md`.
- Rename from LLMinem to Daft Prompt where user-facing.
- Remove local-audio-analysis-first MVP language.
- Remove user-upload analysis flows from the supported product surface.
- Delete or deprecate frontend file-upload affordances and backend upload-analysis routes unless they are needed by tests during transition.
- Make connector-based song knowledge the core analysis path.
- Do not keep local audio analysis as an experimental product feature.

Verification:

```bash
rg -n "local audio|MIR|YouTube|LLMinem|Daft Prompt" PRODUCT.md DESIGN.md docs AGENTS.md README.md
```

### Phase 2: Branch Port Audit

- Start from `product-direction`.
- List `giner` features to port.
- Port in small commits by capability, not by huge merge.
- Preserve product-direction fixes for chat continuity, research continuity, Docker/provider setup, and UI behavior.

Useful commands:

```bash
git switch product-direction
git pull --ff-only origin product-direction
git switch -c feat/daft-prompt-convergence
git log --oneline product-direction..giner
git diff --stat product-direction...giner
git diff --name-status product-direction...giner
```

### Phase 3: Song Knowledge Domain

- Define `SongKnowledgeProfile`, `EvidenceClaim`, `PlayablePart`, `InstrumentTab`, `ToneProfile`, and `CompositionBrief`.
- Add ports for song source connectors.
- Keep Songsterr/tab sources behind infrastructure adapters.
- Store source attribution and confidence.

### Phase 4: Artist/Band Style Profiling

- Define `ArtistStyleProfile`.
- Add an application use case that resolves an artist/band, finds representative songs, fetches evidence for them, and aggregates musical traits.
- Use `product-direction` research continuity patterns so profiles persist across turns.
- Reuse/port `giner` style research and known-song evidence pieces where they fit the connector-based architecture.
- Prefer Songsterr-backed songs when possible, because tabs/chords/instrument parts are more useful for composition than biography alone.
- Run artist profiling in parallel with composition prep for prompts like "compose something similar to Twenty One Pilots."
- Add tests with fake connectors proving that representative song evidence becomes a compact profile.

### Phase 5: Chat Router

- Build LangGraph router for song questions, playable-part requests, composition, and generated-song edits.
- Route artist/band prompts into `ArtistStyleProfile` creation or reuse.
- Preserve context across turns.
- Add deterministic fallback routing for obvious prompts.
- Ensure answers are natural and grounded in evidence.

### Phase 6: Playable Tabs

- Render guitar/bass/drum/piano tabs from tab evidence or generated SongState.
- Allow full-song tab rendering when the user asks or when it is the most useful answer.
- Add UI components only behind chat-requested result blocks.

### Phase 7: Composition From Evidence

- Port the strongest `giner` composition work.
- Create `CompositionBrief` from chat and song knowledge.
- Include `ArtistStyleProfile` for artist/band similarity prompts.
- Feed compact evidence into orchestrator/director.
- Support exact preservation of requested parts, especially drums.
- For "similar to artist/band" prompts, use aggregated profile traits instead of copying one song.
- Validate against brief before returning.

### Phase 8: Editing Existing Compositions

- Add semantic patch/tone edits.
- Add chord edits for selected instruments.
- Preserve unaffected tracks.
- Re-render MIDI/audio artifacts after edits.

### Phase 9: Daft Prompt UI Polish

- Apply focused robotic/futuristic visual language.
- Keep chat primary.
- Use subtle playback/agent animations.
- Add piano roll and mixer after generated output exists.
- Add evidence/tabs/details as compact contextual blocks.

## Prompt For A Coding Agent

Use this prompt to start the implementation run:

```text
You are working in the Daft Prompt repo. Read AGENTS.md, PRODUCT.md, DESIGN.md, docs/architecture.md, plans/chat-musical-mvp.md, and plans/daft-prompt-convergence.md before editing.

Goal: converge the repo toward Daft Prompt: a chat-first AI music assistant that answers song/music questions from scraped public evidence, renders playable tabs/keys/rolls when asked, and composes or edits MIDI music through a dynamic multi-agent band system.

Important product correction: remove user-uploaded file analysis and do not make local audio analysis a supported path. Song knowledge must come from evidence connectors such as Songsterr, tab/chord pages, metadata pages, artist/album information, and style/corpus references. Songsterr is expected to provide much of the tab/chord/metadata evidence. Keep uncertainty and source attribution visible. Avoid claiming perfect analysis.

Branch rule: only consider product-direction and giner. Use product-direction as the base because it contains later chat/research/product fixes. Port giner features selectively: band_agent, semantic patch vocabulary, style grounding, evidence connectors, deterministic fills/drums, piano roll, SF3 playback, MP3 export, and pipeline visualizations. Do not blindly merge giner.

Git workflow: create a new implementation branch from product-direction before editing, for example feat/daft-prompt-convergence. Make atomic, self-explanatory commits and push the branch after each commit. Do not implement directly on product-direction or giner. Do not make one giant commit.

Implement in small phases:
1. Update product/design/architecture docs to Daft Prompt and connector-based song knowledge.
2. Define domain contracts for SongKnowledgeProfile, ArtistStyleProfile, EvidenceClaim, PlayablePart, ToneProfile, and CompositionBrief.
3. Strengthen/port song source connectors behind ports, especially Songsterr/tab evidence.
4. Add ArtistStyleProfile creation: resolve artist/band, select representative popular/tab-available songs, fetch evidence, aggregate traits, and preserve the profile in chat context. This should combine product-direction research continuity with giner style-grounding.
5. Build/refine a LangGraph chat router for song questions, playable tabs, artist/band style profiling, composition, and generated-song edits.
6. Port the best giner composition pipeline into product-direction while preserving product-direction fixes.
7. Add requested renderers for guitar/bass/drum/piano tabs and piano keys.
8. Support composition from song/artist/album/genre evidence and exact preservation of requested parts. For band/artist similarity prompts, feed ArtistStyleProfile into the orchestrator/director through CompositionBrief.
9. Support natural-language edits over generated SongState, such as guitar tone changes or piano chord changes.
10. Apply a restrained Daft Punk-like robotic UI style without making the app dashboard-first.

Keep clean architecture. FastAPI routes must stay thin. Application use cases orchestrate. Domain models stay provider-agnostic. Infrastructure adapters contain scraping/provider details. Keep frontend business logic minimal. Keep TypeScript types synced with Pydantic models.

Run focused tests after each phase:
cd apps/api && python -m pytest
cd apps/web && npm run typecheck && node --test lib/trackMixerLogic.test.mjs

At each step, prefer preserving working product-direction behavior over large rewrites.
```

## Model Recommendation

For the main implementation:

- Use GPT-5 Codex or the strongest available coding model.
- Effort: high.
- Context: maximum available.

For planning and docs-only refinement:

- Use GPT-5 medium effort.

For mechanical ports, tests, and refactors:

- Use GPT-5 Codex high effort with explicit phase boundaries.

This task is cross-branch, architectural, and product-sensitive, so low-effort or small-context runs are likely to miss important branch differences.

## Open Questions

1. Should generated audio aim for browser playback only, or also high-quality export through a backend renderer later?
2. For the first demo, is Songsterr alone enough if it provides tabs/chords/metadata, or should fallback metadata/chord sources be added immediately?
