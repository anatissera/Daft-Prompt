# Design — LLMinem

LLMinem is a conversational music workspace.

The interface should make the user feel like they are working with a musical
assistant, not filling out a generator form. The product can expose technical
analysis and agent activity, but those details should support the conversation
instead of becoming the main surface.

This document defines the UX direction. It does not lock the final visual style.

## Design Goal

The UI should support three actions through one conversational flow:

1. analyze a local audio file;
2. compose a song from scratch;
3. compose a song using a previous analysis as reference.

The user should mostly type what they want. Buttons and toggles should appear
only when they reduce friction.

## Interaction Model

### One Primary Surface

Chat is the primary surface.

The user can write:

- "Analyze this file."
- "What chords are probably in the chorus?"
- "Compose a dark cumbia villera loop."
- "Use this reference's energy but change the harmony."
- "Make the drums less busy."

The app should infer intent from the conversation and current context.

### Contextual Details

Technical details should appear as contextual panels or expandable sections.

Useful context includes:

- uploaded local reference;
- detected tempo, key, sections, energy, and probable chords;
- tool calls and confidence values;
- generated song summary;
- agent roster and negotiation highlights;
- playback and export controls.

The user should be able to ignore these details and continue chatting.

### Minimal Controls

Always useful controls:

- attach local audio;
- send message;
- play/stop generated audio;
- export MIDI;
- show/hide details.

Useful only after generation:

- mute/solo per generated instrument.

Avoid:

- a permanent form of toggles for every musical trait;
- forcing the user to choose a mode before typing;
- making sheet music the default focus;
- showing raw JSON or logs as the primary representation.

When configuration is needed, ask conversationally:

> "I detected the chorus chords with medium confidence. Should I use them as a
> guide, or only use the tempo and energy?"

## Main States

### Empty / Start

The first screen should make it obvious that the user can either ask or compose.

Good starter affordances:

- one chat input;
- local audio attachment;
- a few example prompts;
- no large marketing hero.

### Analysis In Progress

When analyzing a local audio file, the UI should show progress in plain language:

- file accepted;
- audio profile extraction running;
- chord estimation running;
- summary ready.

The user should see that tools are working without needing to understand the
implementation.

### Analysis Result

The result should be readable at a glance:

- tempo;
- key;
- sections;
- energy shape;
- probable chords with confidence.

Chord language should remain probabilistic:

> "Probably Am - F - C - G in this section."

### Composition In Progress

Composition should show enough agent activity to prove the system is agentic:

- director selected an arrangement;
- instrument agents composed parts;
- important negotiation request or resolution;
- convergence/done status.

This should be compact. The feed should not dominate the page.

### Generated Song

After composition, the user should get:

- a short assistant summary;
- play/stop;
- per-instrument mute/solo;
- MIDI export;
- optional technical details;
- optional notation if reliable.

The next chat message should be able to modify the song:

- "Make it faster."
- "Mute the guitar."
- "Regenerate the bass."
- "Use the reference chords after all."

These edit flows can be future work, but the UI should not make them impossible.

## Visual Direction

The visual style is still open.

What should stay true:

- modern and focused;
- musical but not gimmicky;
- comfortable for repeated local experimentation;
- clear hierarchy between chat, context, and playback;
- restrained animation;
- no dense dashboard-first layout.

The app can borrow from lightweight DAW concepts only where useful, such as a
simple mixer after a song exists. It should not attempt to become a full DAW.

## Responsive Behavior

Desktop should prioritize:

- chat as the main column;
- contextual details/playback as a secondary area.

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

Copy should be direct and conversational.

Good:

- "I found a likely 118 BPM tempo."
- "The chorus probably moves Am - F - C - G."
- "I will use the tempo and energy, but not copy the chords."

Avoid:

- overstating uncertain analysis;
- long technical dumps in the main chat;
- unexplained model/provider errors.

