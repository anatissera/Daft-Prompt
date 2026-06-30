# Composition Skills

Give the director and instrument agents a small, deterministic toolbelt of music-theory "skills" they can call instead of inventing every musical decision from prose.

## Why

Today `director` (`apps/api/llm_band/agents/director.py`) picks key/tempo/form/roster purely from a prompt, and each `instrument` (`apps/api/llm_band/agents/instrument.py`) emits raw `Note` lists that are only checked after the fact by `music/validators.py`.
Two problems follow.

First, agents hallucinate notes that the validator then flags as out-of-key, out-of-range, or off-grid — every repair round costs a full LLM turn.
Second, higher-level musical primitives (chord progressions, voice leading, drum patterns, melodic contour over a progression) are reinvented per prompt with no shared vocabulary across instruments, so parts drift apart harmonically.

A small, deterministic skill layer fixes both: the LLM picks *which* primitive to apply (a creative decision), and Python computes the actual pitches/durations (a mechanical one).
This also gives the arbiter and future negotiation rounds something concrete to reference ("bass: voice-lead from Cmaj7 → Am7 over bar 7") instead of free-form prose.

## Non-goals

This plan is not a rewrite of the agent loop or the LangGraph topology.
We are not introducing a new agent framework (no `deepagents`, no langchain `AgentExecutor`); we keep LangGraph + structured output as today.
We are not building a full theory engine — only the primitives the current agents demonstrably need.
We are not touching the web app.

## Approach

Add a new package `apps/api/llm_band/skills/` that exposes pure, side-effect-free functions over `music21` + existing helpers in `llm_band/music/`.
Each skill returns plain data (lists of `Note`, chord symbols, scale-degree tables) that slot directly into `SongState.parts[*].notes` without further massaging.

Expose the skills to the LLM via LangChain's `@tool` decorator, then bind them to the chat model with `llm.bind_tools([...])` inside the existing director and instrument agents.
The agents keep their structured-output contract (`DirectorOutput`, `InstrumentTurnOutput`); tool calls happen *during* the agent's reasoning turn, not as a separate graph node, so the LangGraph shape stays identical.

Skills are stateless and idempotent.
They take explicit inputs (key, chord, range, bar count) and never read `SongState` directly — the agent is responsible for feeding them the right context.
This keeps them trivially testable and reusable from the arbiter, from canned demos, and from future CLI tools.

## Skills, first cut

Director-facing (used while choosing the arrangement):

- `suggest_chord_progression(key, mood, num_bars, sections)` — returns `list[ChordSpan]` covering the song, using common cadential patterns per mood (e.g. "melancholic" → i–VI–III–VII).
  Backed by a small hand-curated table of progressions per mode, then transposed into `key` via `music21`.
- `suggest_form(genre, num_bars)` — returns `list[Section]` (intro/verse/chorus/bridge/outro) sized to `num_bars`.
  Used when the LLM's free-form sectioning produces nonsense (overlaps, gaps).

Instrument-facing (used while composing a part):

- `scale_degrees(key, chord)` — returns the diatonic scale + chord tones as MIDI pitch classes; the agent picks pitches from this set.
- `voice_lead(prev_chord, next_chord, voices, prev_pitches)` — minimal-motion voicing for `voices` independent lines, clamped to a range.
  For the bass/keys/pads roles.
- `fit_to_range(pitches, midi_low, midi_high)` — octave-shifts each pitch into the instrument's range; used as a safety net before emitting notes.
- `quantize_rhythm(durations, meter, grid)` — snaps a rhythm list to `grid` (e.g. 1/16) within the bar.
- `drum_pattern(style, meter, num_bars)` — returns a `list[Note]` on GM drum keys for the named style ("four_on_floor", "boom_bap", "rock_basic").
  Bypasses the LLM entirely for drum parts where note-by-note generation buys us nothing.
- `melodic_contour(chords, range, density)` — produces a chord-tone-anchored melody as `list[Note]` given a progression and a density (notes/bar).
  The lead/melody roles use it as a starting skeleton they can then ornament.

Shared:

- `transpose(notes, semitones)` — utility for key changes / octave fixes.
- `validate_against_header(notes, header, roster_item)` — wraps the existing per-part validation so a skill can self-check before returning.

The list above is the v1 surface, not a frozen contract.
We pick from it in order: chord progression + scale degrees + drum patterns first (biggest quality win), the rest as we see which gaps remain.

## Wiring into the agents

Director keeps its current `with_structured_output(DirectorOutput)` flow but additionally binds `suggest_chord_progression` and `suggest_form` as tools.
The system prompt is updated to say: "Use the tools to fill `chord_progression` and `sections` when uncertain — do not invent them from scratch."
The returned `SongState` then carries a real `header.chord_progression` (today it ships empty per `arrangement_to_song`), which downstream instruments can read.

Each instrument agent binds the instrument-facing skills.
The system prompt for melodic instruments names the progression in `header.chord_progression` and instructs the agent to call `scale_degrees` / `melodic_contour` / `voice_lead` per chord span instead of free-generating pitches.
The system prompt for drums says: "If the genre matches a known pattern, call `drum_pattern` and return its notes verbatim."

The repair loop in `compose_part` / `run_instrument_turn` is unchanged — skills reduce *how often* repairs trigger, they don't replace the safety net.

## File layout

```
apps/api/llm_band/skills/
  __init__.py          # public exports + tool list per agent
  progression.py       # suggest_chord_progression, suggest_form
  harmony.py           # scale_degrees, voice_lead, transpose
  rhythm.py            # quantize_rhythm, drum_pattern
  melody.py            # melodic_contour, fit_to_range
  _tables.py           # hand-curated progression / drum-pattern tables
tests/skills/
  test_progression.py
  test_harmony.py
  test_rhythm.py
  test_melody.py
  test_director_with_tools.py   # integration: director uses suggest_chord_progression
  test_instrument_with_tools.py # integration: instrument uses scale_degrees
```

Skills live next to `music/` rather than inside it because they are *agent-callable* (decorated with `@tool`, with LLM-friendly docstrings) whereas `music/` is pure infrastructure.
Keeping the two separate prevents the tool decorator from leaking into validators and renderers.

## Tests

Each skill gets a pure-function unit test asserting determinism, range correctness, and key fidelity (no out-of-key pitches in melodic outputs).
The two integration tests use a fake LLM (already a pattern in the repo — see how `compose_part` accepts `llm=None`) that asserts the model received the bound tools and that a tool call round-trips correctly into the structured output.
We also add one end-to-end run via `run_director` + `run_instruments` with a stub LLM that always calls `suggest_chord_progression`, asserting the resulting `SongState` has a non-empty `header.chord_progression` and that every melodic part's pitches are in-key per `music/theory.in_key`.

## Rollout

1. Land the skills package + unit tests with no agent changes — pure addition, zero risk.
2. Wire director to `suggest_chord_progression` only; verify on the canned demo (`apps/api/llm_band/canned.py`) that the progression now ships in `header.chord_progression`.
3. Wire one instrument role (drums) to `drum_pattern`; compare against current drum output on the canned demo.
4. Wire melodic instruments to `scale_degrees` + `melodic_contour`.
5. Wire `voice_lead` for bass/keys; measure repair-loop frequency before/after.

Each step is its own PR so we can revert independently if a wiring change degrades output quality.

## Open questions

Should `suggest_chord_progression` be a deterministic table lookup, or a tiny secondary LLM call constrained to chord-symbol output?
The table is more predictable; the LLM is more flexible.
Default to the table for v1 and revisit once we see how often the director's prompt asks for moods/styles outside the table's coverage.

Do we let the arbiter call skills too?
Probably yes (e.g. `validate_against_header` for cross-part checks), but defer until we see what the arbiter actually needs after steps 1–4.
