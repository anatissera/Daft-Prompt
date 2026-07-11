# Design - Daft Prompt

Daft Prompt is a conversational music teacher, producer, and composition
partner. The interface should make the user feel like they are talking with a
musically useful assistant, not configuring a generator form or managing a
dashboard.

This document defines the UX direction. `PRODUCT.md` remains the product source
of truth.

## Design Goal

The UI should support five actions through one conversational flow:

1. ask evidence-backed questions about songs, artists, albums, or genres;
2. learn how to play parts through tabs, keys, rolls, and chord charts;
3. compose original MIDI music from scratch;
4. compose from song, artist, album, or genre evidence;
5. edit generated music in natural language.

The user should mostly type what they want. Controls appear only when they make
the current result easier to inspect, play, or export.

## Interaction Model

### One Primary Surface

Chat is the primary surface.

The user can write:

- "What chords are in the chorus?"
- "How do I play the drum groove?"
- "Show me the bass tab."
- "Compose a French-house loop with a darker bridge."
- "Make it more like this artist without copying a song."
- "Change the piano chords but keep the drums."

The app should infer intent from the conversation and current context.

### Contextual Details

Technical details should appear as contextual panels or expandable result
blocks.

Useful context includes:

- current song knowledge profile;
- current artist or band style profile;
- source claims, conflicts, and confidence;
- rendered tab, keys, roll, chord chart, or rhythm grid;
- generated song summary;
- agent roster and negotiation highlights;
- playback, mixer, and export controls.

The user should be able to ignore these details and continue chatting.

### Minimal Controls

Always useful controls:

- send message;
- play/stop generated audio when a song exists;
- export MIDI or audio when a song exists;
- show/hide evidence, playable views, and agent details.

Useful only after generation:

- mute/solo per generated instrument;
- selected track or section edit targets.

Avoid:

- upload-first analysis affordances;
- permanent forms of toggles for every musical trait;
- forcing the user to choose a mode before typing;
- making sheet music the default focus;
- showing raw JSON or logs as the primary representation.

When configuration is needed, ask conversationally:

> "I found two conflicting chord sources. Should I treat Songsterr as the main
> guide, or use the simpler chord-chart version?"

## Main States

### Empty / Start

The first screen should make it obvious that the user can ask, learn, compose,
or edit.

Good starter affordances:

- one chat input;
- a few example prompts;
- no large marketing hero;
- no upload prompt as a primary action.

### Evidence Search In Progress

When the assistant researches a song or artist, the UI should show progress in
plain language:

- resolving song or artist;
- checking Songsterr/tab evidence;
- checking metadata or style sources;
- summarizing sources;
- preserving uncertainty.

The user should see that tools are working without needing to understand the
implementation.

### Song Knowledge Result

The result should be readable at a glance:

- song identity and source confidence;
- key, tempo, meter, and sections when available;
- likely or source-backed chords;
- playable part availability;
- source list and conflicts.

Language should remain probabilistic when needed:

> "Songsterr suggests this guitar figure, while the chord page simplifies the
> chorus to four chords."

### Playable Teaching Result

After a playable request, the user should get:

- a short natural explanation;
- the relevant tab, keys view, chord chart, piano roll, or rhythm grid;
- source attribution;
- optional playback for the requested part when available.

Playable views should be compact by default and expandable for longer parts.

### Composition In Progress

Composition should show enough agent activity to prove the system is agentic:

- brief created from prompt and evidence;
- director selected arrangement constraints;
- instrument agents composed or preserved parts;
- important negotiation request or resolution;
- reviewer/arbiter status.

This should stay compact. The activity feed should not dominate the page.

### Generated Song

After composition, the user should get:

- a short assistant summary;
- play/stop;
- per-instrument mute/solo;
- MIDI export and audio export when available;
- optional piano roll or technical details;
- optional agent detail.

The next chat message should be able to modify the song:

- "Make it faster."
- "Regenerate only the bass."
- "Keep the drums exactly."
- "Change the guitar tone."
- "Simplify the piano part."

## Visual Direction

Daft Prompt should feel robotic, futuristic, musical, and modern, inspired by
Daft Punk without becoming gimmicky.

Use:

- dark metallic base;
- restrained chrome and gold accents;
- clean typography;
- subtle motion for streaming, evidence search, agent activity, and playback;
- compact panels for evidence, tabs, piano roll, mixer, and agents.

Avoid:

- dashboard-first layout;
- oversized marketing hero;
- permanent control walls;
- raw JSON as primary UI;
- overdesigned neon clutter;
- visual noise that makes the chat harder to read.

## Responsive Behavior

Desktop should prioritize:

- chat as the main column;
- contextual evidence/playback as a secondary area.

Mobile should prioritize:

- chat first;
- details behind collapsible sections;
- playback controls kept reachable after generation.

## Accessibility

The MVP should keep standard accessibility basics:

- keyboard-reachable controls;
- visible focus states;
- semantic buttons and form labels;
- readable contrast;
- no information conveyed only by color;
- audio controls with text labels.

## Content Tone

Copy should be direct, grounded, and conversational.

Good:

- "Songsterr shows a picked guitar part for this section."
- "This chord page suggests the chorus is probably Am - F - C - G."
- "I will preserve the drums exactly and rewrite the piano harmony."
- "I do not have strong enough evidence for the bridge yet."

Avoid:

- overstating uncertain evidence;
- pretending scraped claims are perfect;
- long technical dumps in the main chat;
- unexplained model or connector errors.
