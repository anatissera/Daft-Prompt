# Agentic Workflow Redesign

**Date:** 2026-06-29
**Status:** Approved
**Context:** Trace `032c963-dirty` ("Generate a song like Canned Heat from Jamiroquai") produced output with wrong pitch distribution, no funk character, and zero harmonic coordination between instruments.

---

## Root Causes

1. **No chord progression.** `arrangement_to_song()` hardcodes `chord_progression=[]`. Instruments have only a key name to work from — no harmonic anchor.
2. **All instruments compose in parallel with zero peer information.** Every instrument in round 0 sees "not composed yet" for all peers. They write independently with no shared harmonic or rhythmic reference.
3. **Director produces only one section.** The trace had a single "Verse" spanning all 16 bars. No intro, chorus, or bridge, so instruments have no energy arc to shape dynamics against.
4. **Director system prompt is too sparse.** No guidance on song form, chord progressions, or compositional layering order.
5. **Instrument system prompt has no harmonic or sectional context.** Just key, tempo, bars, MIDI range. Nothing about chords, section energy, or genre idioms.
6. **Drums are robotically repetitive.** Identical pattern for 8 bars; no fills, no variation, no section transitions.
7. **High-pitched output.** Agents tend to write notes at the top of their MIDI range. With multiple instruments (strings, synth lead, epiano) all sitting at the top of their ranges simultaneously, the mix is shrill.

---

## Design

### 1. Director output schema

The director gains three new capabilities in its structured output:

**Chord progression** — a `chord_progression: list[ChordSpan]` already exists in `Header` but is always set to `[]`. The director now generates it explicitly, bar by bar. `ChordSpan` already has `bar: int` and `chord: str`. `arrangement_to_song()` must be updated to pass `out.chord_progression` through instead of hardcoding `[]`.

**Per-instrument playing style** — each `ArrangementInstrument` gains a `playing_style: str` field: one or two sentences of genre-specific idiom guidance written by the director for that instrument in this specific arrangement. Examples: `"Lock the kick on beat 1 and the syncopated 16th before beat 3. Ghost notes on snare between 2 and 4. Hi-hat strictly 16ths, open on the and-of-4 in the last bar of each phrase."`, `"Short syncopated chord stabs on beats 2 and 4 with 16th-note muting between hits. Leave space for bass fills. Stay below the 5th fret register."`.

**Composition groups** — an ordered list of batches the director defines to control the layering sequence. Each instrument_id must appear in exactly one group; `arrangement_to_song()` validates this and raises if any id is duplicated or missing from the roster:

Both `ArrangementSection` (director.py) and `Section` (song_state.py) gain an `energy: Literal["low", "medium", "high"]` field so the value flows from the director's output through `_clamp_sections()` into `Header.sections` and is available to instrument prompts.

```python
class CompositionGroup(BaseModel):
    name: str                      # e.g. "rhythm_section", "harmony", "top_line"
    instrument_ids: list[str]      # roster ids in this batch; each id must appear in exactly one group
    max_negotiation_rounds: int = Field(1, ge=0, le=2)  # upper bound; stops early if no pending requests

class ArrangementInstrument(BaseModel):
    id: str
    instrument: str
    midi_program: int
    midi_low: int
    midi_high: int
    role: str
    playing_style: str             # NEW
    is_drum: bool = False

class DirectorOutput(BaseModel):
    genre: str
    key: str
    tempo_bpm: float
    time_sig_numerator: int = 4
    time_sig_denominator: int = 4
    num_bars: int
    sections: list[ArrangementSection]
    chord_progression: list[ChordSpan]          # NOW POPULATED
    instruments: list[ArrangementInstrument]
    composition_groups: list[CompositionGroup]  # NEW
```

### 2. Director system prompt

The revised director prompt frames the director as a session arranger who must think in layers:

- Produce a real song form with named sections (Intro, Verse, PreChorus, Chorus, Bridge, Outro) and assign an energy level to each (`low` / `medium` / `high`). The energy level is stored on each `ArrangementSection` and carried through to `Header.sections` so instrument agents can read it.
- Write a chord progression covering all bars, respecting the key and fitting the genre.
- For each instrument, write one or two sentences of `playing_style` that a musician of that instrument in this genre would immediately recognise as correct idiom.
- Assign instruments to `composition_groups` in the order they should be layered: foundational rhythm instruments first, harmony instruments second, melody and texture last. Each group composes only after all prior groups have finished. The director decides the groupings based on the genre — a funk band would group drums+bass first, then guitar+epiano, then synth lead+strings.
- `max_negotiation_rounds` on each group is a ceiling, not a fixed count.

### 3. Graph architecture

The current graph is a single parallel fan-out followed by a global negotiation loop. The redesigned graph introduces a **batch sequencer** driven by `composition_groups`:

```
START → director → batch_0 → batch_1 → ... → batch_N → arbiter → END
```

Each batch is a subgraph:

```
batch_START
  → instrument_turns (parallel, all group members)
  → batch_check_convergence
      → batch_next_round (if pending requests and round < max_negotiation_rounds)
          → instrument_turns (only instruments with pending requests addressed to them)
      → batch_END (if converged or round cap reached)
```

When a batch closes, the `notes_summary` of all its instruments is merged into the global `peer_summaries` dict, which is passed as input to every subsequent batch. This is how the rhythm section's groove becomes visible to the harmony layer before the harmony layer starts composing.

The `BandState` gains a `peer_summaries: dict[str, str]` field (previously derived inline) and a `current_group_index: int` field to track which batch is executing.

The arbiter runs once at the end, force-resolving any requests that survived all batch rounds. Its behaviour is unchanged.

### 4. Instrument system prompt

The revised instrument system prompt injects four layers of context that the current prompt omits entirely:

**Chord progression** — formatted as a readable bar list:
```
Chord map:
  bar 0: Dm7  |  bar 1: G7  |  bar 2: Cm7  |  bar 3: F7  | ...
```

**Section map with energy** — formatted as a form summary:
```
Song form:
  Intro      bars 0-3    energy: low
  Verse      bars 4-11   energy: medium
  Chorus     bars 12-15  energy: high
```

**Playing style** — the director's per-instrument idiom guidance, injected verbatim after the hard constraints.

**Prior batch summaries** — the `notes_summary` of every instrument from earlier batches, formatted identically to today's peer context block. The rhythm section's groove is readable before the harmony layer composes. Within round 0 of a batch, the instrument sees summaries from all prior batches but "not composed yet" for batch peers (same as today). In subsequent rounds within the batch, it sees the actual summaries of its batch peers.

### 5. Intra-batch mini-negotiation

The existing `NegotiationRequest` / `RequestResolution` / `NewRequest` schema is reused unchanged. Two additions:

**Scope enforcement in dispatch** — when building the `Send` list for a negotiation round within a batch, pending requests are filtered to those where `request.to` is in the current batch's `instrument_ids`. Requests to instruments outside the batch are not dispatched and remain pending for the arbiter.

**Prompt scope hint** — one sentence is appended to the negotiation etiquette block: `"You may only raise requests to instruments in your current composition group: {batch_peer_ids}. Do not address instruments in other groups."` This prevents the model from raising cross-batch requests that can never be fulfilled within the batch.

**Convergence** — identical logic to the current `check_convergence` node: if no pending requests remain scoped to the batch, or `max_negotiation_rounds` is reached, the batch closes. Early exit is the common case.

---

## What is not changing

- `Note` schema (`bar`, `start_beat`, `pitch`, `dur`, `velocity`) — tracked in [issue #22](https://github.com/anatissera/Daft-Prompt/issues/22).
- `render_midi.py` and `render_sheet.py` — no downstream changes.
- `validate_song` and all validators — no changes.
- The arbiter — behaviour unchanged.
- The `NegotiationRequest` / `RequestResolution` / `NewRequest` schemas — reused as-is.
- Genre idiom library — tracked in [issue #21](https://github.com/anatissera/Daft-Prompt/issues/21).

---

## Files affected

| File | Change |
|---|---|
| `agents/director.py` | New `CompositionGroup` model, `playing_style` on `ArrangementInstrument`, chord progression populated, revised system prompt |
| `agents/instrument.py` | Revised `_system_prompt()` with chord map, section map, playing style; revised `_peer_context()` to include prior-batch summaries; scope hint in negotiation etiquette |
| `graph.py` | Replace `_build_negotiation_graph` with batch sequencer; add `_build_batch_subgraph`; update `BandState` |
| `state.py` | Add `peer_summaries: dict[str, str]` and `current_group_index: int` to `BandState` |
| `domain/song_state.py` | Add `energy: Literal["low", "medium", "high"]` to `Section` |
