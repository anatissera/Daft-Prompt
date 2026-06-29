# Agentic Workflow Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the LLM band composition pipeline so the director produces a chord progression, per-instrument playing style, and an ordered list of composition groups; the graph executes those groups sequentially with intra-batch mini-negotiation; and instrument agents receive full harmonic, sectional, and stylistic context before composing.

**Architecture:** The director gains three new output fields (`chord_progression`, `playing_style` per instrument, `composition_groups`). The LangGraph composition graph replaces its single parallel fan-out with a sequential batch loop: each batch runs its instruments in parallel, mini-negotiates within the batch up to `max_negotiation_rounds`, then closes and passes peer summaries to the next batch. Instrument system prompts consume chord maps, section energy arcs, and playing-style guidance from the enriched header and roster.

**Tech Stack:** Python 3.13, LangGraph, LangChain, Pydantic v2, pytest, uv

## Global Constraints

- All test runs use `uv run pytest <path> -v`
- No new dependencies — only existing imports
- All new Pydantic fields must have defaults so old serialized data remains deserializable where applicable
- `run_negotiation(style: str, ...)` and `iter_negotiation_events(style: str, ...)` public signatures unchanged
- Never raise inside a graph node — follow the existing "never-crash" contract (fallback to empty part on LLM failure)
- Follow existing code style: `from __future__ import annotations`, `@traceable` decorators, no type annotations in function bodies

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `apps/api/llm_band/domain/song_state.py` | Modify | Add `Section.energy`, `RosterItem.playing_style`, `CompositionGroup`, `SongState.composition_groups` |
| `apps/api/llm_band/agents/director.py` | Modify | New schema fields, enriched `arrangement_to_song()`, rewritten system prompt |
| `apps/api/llm_band/state.py` | Modify | New `BandState`/`InstrumentsState` fields, `merge_summaries` reducer |
| `apps/api/llm_band/agents/instrument.py` | Modify | New prompt helpers, enriched `_system_prompt`, `_negotiation_etiquette(batch_peer_ids)`, updated `run_instrument_turn` signature |
| `apps/api/llm_band/graph.py` | Modify | Batch sequencer replacing `_build_negotiation_graph`, updated `run_negotiation` / `iter_negotiation_events` |
| `apps/api/tests/test_director.py` | Modify | Tests for new fields, `arrangement_to_song` validation |
| `apps/api/tests/test_instrument.py` | Modify | Tests for new prompt helpers and updated `run_instrument_turn` signature |
| `apps/api/tests/test_graph.py` | Modify | Tests for batch sequencing, peer summary propagation, intra-batch scoping |
| `apps/api/tests/test_negotiation.py` | Modify | Update to use new graph API and state shape |

---

## Task 1: domain/song_state.py — Section energy, RosterItem playing style, CompositionGroup

**Files:**
- Modify: `apps/api/llm_band/domain/song_state.py`
- Test: `apps/api/tests/test_director.py`

**Interfaces:**
- Produces:
  - `Section.energy: Literal["low", "medium", "high"]` defaulting to `"medium"`
  - `RosterItem.playing_style: str` defaulting to `""`
  - `CompositionGroup(name, instrument_ids, max_negotiation_rounds)` Pydantic model
  - `SongState.composition_groups: list[CompositionGroup]` defaulting to `[]`

- [ ] **Step 1: Write the failing tests**

```python
# In apps/api/tests/test_director.py, add at the bottom:

from llm_band.domain.song_state import CompositionGroup, Section, RosterItem, SongState


def test_section_has_energy_field_defaulting_to_medium():
    s = Section(name="verse", start_bar=0, end_bar=8)
    assert s.energy == "medium"


def test_section_accepts_valid_energy_literals():
    assert Section(name="intro", start_bar=0, end_bar=2, energy="low").energy == "low"
    assert Section(name="chorus", start_bar=8, end_bar=12, energy="high").energy == "high"


def test_roster_item_has_playing_style_defaulting_to_empty():
    item = RosterItem(id="bass", instrument="electric_bass")
    assert item.playing_style == ""


def test_composition_group_fields():
    g = CompositionGroup(name="rhythm", instrument_ids=["drums", "bass"], max_negotiation_rounds=1)
    assert g.name == "rhythm"
    assert g.instrument_ids == ["drums", "bass"]
    assert g.max_negotiation_rounds == 1


def test_composition_group_max_negotiation_rounds_clamps_to_range():
    # pydantic should reject values outside ge=0, le=2
    import pytest
    with pytest.raises(Exception):
        CompositionGroup(name="x", instrument_ids=[], max_negotiation_rounds=5)


def test_song_state_has_composition_groups_defaulting_to_empty():
    from llm_band.domain.song_state import Header
    song = SongState(
        request="test",
        header=Header(genre="funk", key="D minor", tempo_bpm=100, num_bars=8),
    )
    assert song.composition_groups == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest apps/api/tests/test_director.py::test_section_has_energy_field_defaulting_to_medium apps/api/tests/test_director.py::test_composition_group_fields apps/api/tests/test_director.py::test_song_state_has_composition_groups_defaulting_to_empty -v
```

Expected: FAIL — `Section` has no `energy`, `CompositionGroup` not found, `SongState` has no `composition_groups`.

- [ ] **Step 3: Implement the domain changes**

Replace the contents of `apps/api/llm_band/domain/song_state.py`:

```python
"""Canonical `SongState` schema shared across the composition pipeline."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Section(BaseModel):
    name: str
    start_bar: int
    end_bar: int
    energy: Literal["low", "medium", "high"] = "medium"


class ChordSpan(BaseModel):
    bar: int
    chord: str


class CompositionGroup(BaseModel):
    name: str
    instrument_ids: list[str]
    max_negotiation_rounds: int = Field(1, ge=0, le=2)


class Header(BaseModel):
    """Immutable global plan set by the director."""

    genre: str
    key: str
    tempo_bpm: float
    time_signature: tuple[int, int] = (4, 4)
    num_bars: int
    sections: list[Section] = Field(default_factory=list)
    chord_progression: list[ChordSpan] = Field(default_factory=list)


class RosterItem(BaseModel):
    id: str
    instrument: str
    midi_program: int = 0
    midi_range: tuple[int, int] = (0, 127)
    role: str = ""
    playing_style: str = ""
    is_drum: bool = False


class Note(BaseModel):
    bar: int
    start_beat: float
    pitch: Optional[int] = None
    dur: float = 1.0
    velocity: int = 96


class Part(BaseModel):
    instrument_id: str
    version: int = 1
    notes: list[Note] = Field(default_factory=list)
    notes_summary: str = ""
    self_notes: str = ""


class NegotiationRequest(BaseModel):
    id: str
    from_: str = Field(alias="from")
    to: str
    round: int = 0
    bars: list[int] = Field(default_factory=list)
    request: str = ""
    rationale: str = ""
    status: Literal["pending", "resolved", "declined"] = "pending"
    resolution: str = ""

    model_config = {"populate_by_name": True}


class SongState(BaseModel):
    request: str
    header: Header
    roster: list[RosterItem] = Field(default_factory=list)
    parts: dict[str, Part] = Field(default_factory=dict)
    negotiation_requests: list[NegotiationRequest] = Field(default_factory=list)
    composition_groups: list[CompositionGroup] = Field(default_factory=list)
    round: int = 0
    converged: bool = False
    errors: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
uv run pytest apps/api/tests/test_director.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/llm_band/domain/song_state.py apps/api/tests/test_director.py
git commit -m "feat: add Section.energy, RosterItem.playing_style, CompositionGroup to domain"
```

---

## Task 2: agents/director.py — Schema additions

**Files:**
- Modify: `apps/api/llm_band/agents/director.py`
- Test: `apps/api/tests/test_director.py`

**Interfaces:**
- Consumes: `CompositionGroup`, `Section.energy`, `RosterItem.playing_style` from Task 1
- Produces:
  - `ArrangementSection.energy: Literal["low", "medium", "high"]`
  - `ArrangementInstrument.playing_style: str`
  - `DirectorOutput.chord_progression: list[ChordSpan]`
  - `DirectorOutput.composition_groups: list[CompositionGroup]`

- [ ] **Step 1: Write the failing tests**

```python
# Add to apps/api/tests/test_director.py:

from llm_band.agents.director import (
    ArrangementInstrument,
    ArrangementSection,
    CompositionGroup,  # re-exported from director
    DirectorOutput,
)
from llm_band.domain.song_state import ChordSpan


def _full_output() -> DirectorOutput:
    return DirectorOutput(
        genre="funk",
        key="D minor",
        tempo_bpm=110,
        time_sig_numerator=4,
        time_sig_denominator=4,
        num_bars=16,
        sections=[
            ArrangementSection(name="Intro", start_bar=0, end_bar=4, energy="low"),
            ArrangementSection(name="Verse", start_bar=4, end_bar=12, energy="medium"),
            ArrangementSection(name="Chorus", start_bar=12, end_bar=16, energy="high"),
        ],
        chord_progression=[ChordSpan(bar=i, chord="Dm7") for i in range(16)],
        instruments=[
            ArrangementInstrument(
                id="drums", instrument="Acoustic Drums", midi_program=0,
                midi_low=0, midi_high=127, role="groove", playing_style="Four on the floor kick.", is_drum=True,
            ),
            ArrangementInstrument(
                id="bass", instrument="Electric Bass", midi_program=34,
                midi_low=28, midi_high=55, role="melodic bass", playing_style="Anchor beat 1.",
            ),
            ArrangementInstrument(
                id="epiano", instrument="Rhodes", midi_program=5,
                midi_low=48, midi_high=72, role="harmony", playing_style="Chord stabs on 2 and 4.",
            ),
        ],
        composition_groups=[
            CompositionGroup(name="rhythm", instrument_ids=["drums", "bass"], max_negotiation_rounds=1),
            CompositionGroup(name="harmony", instrument_ids=["epiano"], max_negotiation_rounds=0),
        ],
    )


def test_director_output_accepts_chord_progression():
    out = _full_output()
    assert len(out.chord_progression) == 16
    assert out.chord_progression[0].chord == "Dm7"


def test_director_output_accepts_composition_groups():
    out = _full_output()
    assert len(out.composition_groups) == 2
    assert out.composition_groups[0].name == "rhythm"
    assert out.composition_groups[0].instrument_ids == ["drums", "bass"]


def test_arrangement_instrument_has_playing_style():
    out = _full_output()
    assert out.instruments[0].playing_style == "Four on the floor kick."


def test_arrangement_section_has_energy():
    out = _full_output()
    assert out.sections[0].energy == "low"
    assert out.sections[1].energy == "medium"
    assert out.sections[2].energy == "high"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest apps/api/tests/test_director.py::test_director_output_accepts_chord_progression apps/api/tests/test_director.py::test_arrangement_instrument_has_playing_style -v
```

Expected: FAIL — `ArrangementInstrument` has no `playing_style`, `DirectorOutput` has no `composition_groups`.

- [ ] **Step 3: Update the schema in director.py**

In `apps/api/llm_band/agents/director.py`, replace the model section (lines 1–62) with:

```python
"""Director agent — reasons an arrangement (header + roster) from a style string.

This is the first LLM node. It does NOT compose notes (that's the instrument agents);
it decides key/tempo/meter/form, chord progression, per-instrument playing style, and
the ordered composition groups that control layering order.
"""

from __future__ import annotations

from typing import Literal, Optional

from langsmith import traceable
from pydantic import BaseModel, Field

from ..domain.song_state import (
    ChordSpan,
    CompositionGroup,
    Header,
    RosterItem,
    Section,
    SongState,
)

MIN_ROSTER = 3
MAX_ROSTER = 8
MIN_BARS = 4
MAX_BARS = 32


class ArrangementInstrument(BaseModel):
    id: str = Field(description="short unique id, e.g. 'bass', 'lead_synth'")
    instrument: str = Field(description="human name, e.g. 'electric_bass'")
    midi_program: int = Field(0, ge=0, le=127, description="General MIDI program")
    midi_low: int = Field(0, ge=0, le=127)
    midi_high: int = Field(127, ge=0, le=127)
    role: str = Field(description="this instrument's musical role in the arrangement")
    playing_style: str = Field(
        description=(
            "1-2 sentences of idiomatic technique for this instrument in this genre. "
            "Example: 'Anchor beat 1. Ghost notes on snare between 2 and 4. "
            "Hi-hat strictly 16ths, open on the and-of-4 in the last bar of each phrase.'"
        )
    )
    is_drum: bool = False


class ArrangementSection(BaseModel):
    name: str
    start_bar: int = Field(ge=0)
    end_bar: int = Field(ge=0)
    energy: Literal["low", "medium", "high"] = "medium"


class DirectorOutput(BaseModel):
    genre: str
    key: str = Field(description="e.g. 'F# minor', 'C major'")
    tempo_bpm: float = Field(gt=0)
    time_sig_numerator: int = Field(4, gt=0)
    time_sig_denominator: int = Field(4, gt=0)
    num_bars: int = Field(gt=0, description=f"between {MIN_BARS} and {MAX_BARS} bars")
    sections: list[ArrangementSection] = Field(
        description="3-6 named sections covering all bars without overlap"
    )
    chord_progression: list[ChordSpan] = Field(
        description="one ChordSpan per bar covering all bars (bar 0..num_bars-1)"
    )
    instruments: list[ArrangementInstrument] = Field(
        description=f"between {MIN_ROSTER} and {MAX_ROSTER} instruments"
    )
    composition_groups: list[CompositionGroup] = Field(
        description=(
            "ordered batches for layered composition. Each instrument_id must appear "
            "in exactly one group. Put rhythm foundation first, harmony second, "
            "melody/texture last."
        )
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest apps/api/tests/test_director.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/llm_band/agents/director.py apps/api/tests/test_director.py
git commit -m "feat: add playing_style, energy, chord_progression, composition_groups to director schema"
```

---

## Task 3: agents/director.py — arrangement_to_song() propagation and validation

**Files:**
- Modify: `apps/api/llm_band/agents/director.py`
- Test: `apps/api/tests/test_director.py`

**Interfaces:**
- Consumes: `DirectorOutput` with new fields from Task 2
- Produces:
  - `arrangement_to_song()` populates `header.chord_progression`, `section.energy`, `roster_item.playing_style`, and `song.composition_groups`
  - `arrangement_to_song()` raises `ValueError` if any instrument_id appears in multiple groups or if any instrument is missing from all groups

- [ ] **Step 1: Write the failing tests**

```python
# Add to apps/api/tests/test_director.py:

def test_arrangement_to_song_populates_chord_progression():
    out = _full_output()
    song = arrangement_to_song("funk", out)
    assert len(song.header.chord_progression) == 16
    assert song.header.chord_progression[0].chord == "Dm7"


def test_arrangement_to_song_propagates_section_energy():
    out = _full_output()
    song = arrangement_to_song("funk", out)
    assert song.header.sections[0].energy == "low"
    assert song.header.sections[2].energy == "high"


def test_arrangement_to_song_propagates_playing_style():
    out = _full_output()
    song = arrangement_to_song("funk", out)
    drums = next(r for r in song.roster if r.id == "drums")
    assert drums.playing_style == "Four on the floor kick."


def test_arrangement_to_song_populates_composition_groups():
    out = _full_output()
    song = arrangement_to_song("funk", out)
    assert len(song.composition_groups) == 2
    assert song.composition_groups[0].instrument_ids == ["drums", "bass"]


def test_arrangement_to_song_raises_on_duplicate_instrument_in_groups():
    out = _full_output()
    out.composition_groups = [
        CompositionGroup(name="a", instrument_ids=["drums", "bass"]),
        CompositionGroup(name="b", instrument_ids=["bass", "epiano"]),  # bass duplicated
    ]
    import pytest
    with pytest.raises(ValueError, match="multiple"):
        arrangement_to_song("funk", out)


def test_arrangement_to_song_raises_on_instrument_missing_from_all_groups():
    out = _full_output()
    out.composition_groups = [
        CompositionGroup(name="a", instrument_ids=["drums", "bass"]),
        # epiano missing
    ]
    import pytest
    with pytest.raises(ValueError, match="not assigned"):
        arrangement_to_song("funk", out)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest apps/api/tests/test_director.py::test_arrangement_to_song_populates_chord_progression apps/api/tests/test_director.py::test_arrangement_to_song_raises_on_duplicate_instrument_in_groups -v
```

Expected: FAIL.

- [ ] **Step 3: Update arrangement_to_song() and helpers in director.py**

Replace the `_clamp_*` functions and `arrangement_to_song` in `apps/api/llm_band/agents/director.py` with:

```python
def _clamp_roster(items: list[ArrangementInstrument]) -> list[ArrangementInstrument]:
    return items[:MAX_ROSTER]


def _clamp_num_bars(value: int) -> int:
    return max(MIN_BARS, min(MAX_BARS, value))


def _clamp_sections(sections: list[ArrangementSection], num_bars: int) -> list[Section]:
    clamped = []
    for section in sections:
        start = max(0, min(section.start_bar, num_bars - 1))
        end = max(start + 1, min(section.end_bar, num_bars))
        clamped.append(
            Section(name=section.name, start_bar=start, end_bar=end, energy=section.energy)
        )
    return clamped


def _validate_groups(
    groups: list[CompositionGroup], instruments: list[ArrangementInstrument]
) -> None:
    instrument_ids = {i.id for i in instruments}
    seen: set[str] = set()
    for group in groups:
        for iid in group.instrument_ids:
            if iid not in instrument_ids:
                raise ValueError(f"composition group references unknown instrument: {iid!r}")
            if iid in seen:
                raise ValueError(
                    f"instrument {iid!r} appears in multiple composition groups"
                )
            seen.add(iid)
    missing = instrument_ids - seen
    if missing:
        raise ValueError(f"instruments not assigned to any group: {missing}")


def arrangement_to_song(style: str, out: DirectorOutput) -> SongState:
    clamped_instruments = _clamp_roster(out.instruments)
    num_bars = _clamp_num_bars(out.num_bars)
    _validate_groups(out.composition_groups, clamped_instruments)
    header = Header(
        genre=out.genre,
        key=out.key,
        tempo_bpm=out.tempo_bpm,
        time_signature=(out.time_sig_numerator, out.time_sig_denominator),
        num_bars=num_bars,
        sections=_clamp_sections(out.sections, num_bars),
        chord_progression=list(out.chord_progression),
    )
    roster = [
        RosterItem(
            id=i.id,
            instrument=i.instrument,
            midi_program=i.midi_program,
            midi_range=(min(i.midi_low, i.midi_high), max(i.midi_low, i.midi_high)),
            role=i.role,
            playing_style=i.playing_style,
            is_drum=i.is_drum,
        )
        for i in clamped_instruments
    ]
    return SongState(
        request=style,
        header=header,
        roster=roster,
        parts={},
        composition_groups=list(out.composition_groups),
    )
```

- [ ] **Step 4: Update the existing `_output()` test helper** to include required new fields so it doesn't break old tests. Edit `_output()` in `test_director.py` to add `playing_style`, `chord_progression`, and `composition_groups`:

```python
def _output(n: int = 4) -> DirectorOutput:
    return DirectorOutput(
        genre="disco",
        key="F# minor",
        tempo_bpm=116,
        time_sig_numerator=4,
        time_sig_denominator=4,
        num_bars=32,
        sections=[ArrangementSection(name="verse", start_bar=0, end_bar=8, energy="medium")],
        chord_progression=[ChordSpan(bar=i, chord="Am7") for i in range(32)],
        instruments=[
            ArrangementInstrument(
                id=f"inst{k}", instrument="electric_bass", midi_program=33,
                midi_low=28, midi_high=55, role="groove", playing_style="Root notes.", is_drum=(k == 0),
            )
            for k in range(n)
        ],
        composition_groups=[
            CompositionGroup(name="all", instrument_ids=[f"inst{k}" for k in range(min(n, MAX_ROSTER))]),
        ],
    )
```

- [ ] **Step 5: Run all director tests**

```bash
uv run pytest apps/api/tests/test_director.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/llm_band/agents/director.py apps/api/tests/test_director.py
git commit -m "feat: arrangement_to_song propagates chord progression, energy, playing style, and validates groups"
```

---

## Task 4: agents/director.py — System prompt rewrite

**Files:**
- Modify: `apps/api/llm_band/agents/director.py`
- Test: `apps/api/tests/test_director.py`

**Interfaces:**
- Produces: `_SYSTEM` and `_prompt()` that elicit all new fields from the LLM

- [ ] **Step 1: Write a test verifying the prompt structure**

```python
# Add to apps/api/tests/test_director.py:

from llm_band.agents.director import _prompt


def test_director_prompt_contains_key_musical_concepts():
    messages = _prompt("funk like Jamiroquai")
    system_text = next(m for role, m in messages if role == "system")
    human_text = next(m for role, m in messages if role == "human")
    # verify the prompt requests the new fields
    assert "chord progression" in system_text.lower()
    assert "playing_style" in system_text or "playing style" in system_text.lower()
    assert "composition_group" in system_text or "composition group" in system_text.lower()
    assert "energy" in system_text.lower()
    assert "Jamiroquai" in human_text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest apps/api/tests/test_director.py::test_director_prompt_contains_key_musical_concepts -v
```

Expected: FAIL — current prompt doesn't mention chord progression, playing_style, or composition groups.

- [ ] **Step 3: Rewrite `_SYSTEM` and `_prompt()` in director.py**

```python
_SYSTEM = f"""You are the musical director of an ensemble. Given a style description, produce a complete arrangement plan with the following required outputs:

1. ARRANGEMENT: key, tempo, time signature, num_bars ({MIN_BARS}-{MAX_BARS}). Reason about what genuinely fits the style.

2. SONG FORM: 3-6 named sections (e.g. Intro, Verse, PreChorus, Chorus, Bridge, Outro). Each section has start_bar, end_bar, and an energy level: "low", "medium", or "high". Sections must cover all bars 0..num_bars-1 without overlap or gap.

3. CHORD PROGRESSION: one ChordSpan per bar covering every bar (0..num_bars-1). Use chord names like "Dm7", "G7", "Cm9". Chords must fit the key and genre idiom.

4. INSTRUMENTATION: {MIN_ROSTER}-{MAX_ROSTER} instruments. For each instrument:
   - A General MIDI program number and a sensible MIDI pitch range for that instrument in that register (e.g. bass: 28-55, not 0-127).
   - Its musical role.
   - A playing_style: 1-2 sentences of idiomatic technique a real musician of this instrument in this genre would immediately recognise. Be specific about rhythm, articulation, and register. Examples:
     * Funk bass: "Anchor beat 1 firmly. Use ghost notes between the 2 and 4. Slap on the upbeat 16th just before beat 3 in bar-ending phrases."
     * Funk guitar: "Short 16th-note chord stabs on beats 2 and 4 with percussive muting between hits. Wah on fill bars. Stay in the mid register."
     * String pad: "Sustained whole-note pads below the melody register. Swell into the chorus. Avoid the top octave to leave room for the lead."

5. COMPOSITION GROUPS: ordered batches specifying which instruments compose in which wave. Each instrument_id must appear in exactly one group. Put rhythmic foundation first (drums, bass), harmonic layer second, melodic/textural layer last. Set max_negotiation_rounds (0-2) — use 1 for rhythm section, 0 for texture layers.

Do not use a fixed genre-to-instrument mapping. Reason about what genuinely fits the requested style."""


def _prompt(style: str) -> list[tuple[str, str]]:
    return [("system", _SYSTEM), ("human", f"Style: {style}")]
```

- [ ] **Step 4: Run all director tests**

```bash
uv run pytest apps/api/tests/test_director.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/llm_band/agents/director.py apps/api/tests/test_director.py
git commit -m "feat: rewrite director system prompt to elicit chords, playing style, and composition groups"
```

---

## Task 5: state.py — New BandState and InstrumentsState fields

**Files:**
- Modify: `apps/api/llm_band/state.py`

**Interfaces:**
- Consumes: `CompositionGroup` from `domain/song_state.py` (Task 1)
- Produces:
  - `merge_summaries(left, right) -> dict[str, str]` reducer
  - `BandState` with new fields: `composition_groups`, `current_group_index`, `batch_instrument_ids`, `max_negotiation_rounds`, `peer_summaries`
  - `InstrumentsState` with new fields: `batch_instrument_ids`, `max_negotiation_rounds`, `peer_summaries`

- [ ] **Step 1: Write a test for merge_summaries**

```python
# Create apps/api/tests/test_state.py:

from llm_band.state import merge_summaries


def test_merge_summaries_right_wins_on_conflict():
    left = {"drums": "old summary", "bass": "bass summary"}
    right = {"drums": "new summary", "epiano": "epiano summary"}
    result = merge_summaries(left, right)
    assert result["drums"] == "new summary"
    assert result["bass"] == "bass summary"
    assert result["epiano"] == "epiano summary"


def test_merge_summaries_empty_inputs():
    assert merge_summaries({}, {}) == {}
    assert merge_summaries({"a": "x"}, {}) == {"a": "x"}
    assert merge_summaries({}, {"b": "y"}) == {"b": "y"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest apps/api/tests/test_state.py -v
```

Expected: FAIL — `merge_summaries` not found.

- [ ] **Step 3: Update state.py**

Replace `apps/api/llm_band/state.py` with:

```python
"""LangGraph state schema for the composition pipeline."""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict

from .domain.song_state import CompositionGroup, Header, NegotiationRequest, Part, RosterItem


def merge_parts(left: dict[str, Part], right: dict[str, Part]) -> dict[str, Part]:
    merged = dict(left)
    merged.update(right)
    return merged


def merge_summaries(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    merged = dict(left)
    merged.update(right)
    return merged


def merge_requests(
    left: list[NegotiationRequest], right: list[NegotiationRequest]
) -> list[NegotiationRequest]:
    """Merge by id: a later entry with the same id replaces the earlier one."""
    by_id = {r.id: r for r in left}
    for r in right:
        by_id[r.id] = r
    return list(by_id.values())


def take_latest(_left: int, right: int) -> int:
    return right


class BandState(TypedDict):
    request: str
    header: Optional[Header]
    roster: list[RosterItem]
    composition_groups: list[CompositionGroup]
    current_group_index: int
    batch_instrument_ids: list[str]
    max_negotiation_rounds: int
    parts: Annotated[dict[str, Part], merge_parts]
    negotiation_requests: Annotated[list[NegotiationRequest], merge_requests]
    round: Annotated[int, take_latest]
    converged: bool
    peer_summaries: Annotated[dict[str, str], merge_summaries]


class InstrumentsState(TypedDict):
    """Shares keys with BandState so LangGraph passes state between parent and subgraph automatically."""
    header: Optional[Header]
    roster: list[RosterItem]
    batch_instrument_ids: list[str]
    max_negotiation_rounds: int
    parts: Annotated[dict[str, Part], merge_parts]
    negotiation_requests: Annotated[list[NegotiationRequest], merge_requests]
    round: Annotated[int, take_latest]
    peer_summaries: Annotated[dict[str, str], merge_summaries]
```

**Note:** `BandState` and `InstrumentsState` are declared as subclasses of `dict` (not `TypedDict`) to allow `Annotated` fields with reducers — the same pattern LangGraph uses internally. The type annotations are still accurate for tooling.

- [ ] **Step 4: Run tests**

```bash
uv run pytest apps/api/tests/test_state.py apps/api/tests/test_graph.py apps/api/tests/test_negotiation.py -v
```

Expected: `test_state.py` all PASS. Graph/negotiation tests may fail due to the state shape change — those are fixed in Task 7.

- [ ] **Step 5: Commit**

```bash
git add apps/api/llm_band/state.py apps/api/tests/test_state.py
git commit -m "feat: add peer_summaries, composition_groups, batch fields to BandState and InstrumentsState"
```

---

## Task 6: agents/instrument.py — Prompt helpers and updated signature

**Files:**
- Modify: `apps/api/llm_band/agents/instrument.py`
- Test: `apps/api/tests/test_instrument.py`

**Interfaces:**
- Consumes: `Header.chord_progression`, `Header.sections` (with `energy`), `RosterItem.playing_style` from Task 1; `batch_peer_ids: list[str]` new parameter
- Produces:
  - `_chord_map_text(chord_progression: list[ChordSpan]) -> str`
  - `_section_map_text(sections: list[Section]) -> str`
  - `_system_prompt(header, roster_item)` — enriched (no signature change; reads new fields from header/roster_item)
  - `_negotiation_etiquette(batch_peer_ids: list[str]) -> str` — adds scope hint
  - `run_instrument_turn(..., batch_peer_ids: list[str], ...)` — new parameter, used for etiquette and request scoping

- [ ] **Step 1: Write the failing tests**

```python
# Add to apps/api/tests/test_instrument.py:

from llm_band.agents.instrument import _chord_map_text, _section_map_text, _negotiation_etiquette
from llm_band.domain.song_state import ChordSpan, Section


def test_chord_map_text_formats_bar_chord_pairs():
    chords = [ChordSpan(bar=0, chord="Dm7"), ChordSpan(bar=1, chord="G7"), ChordSpan(bar=2, chord="Cm9")]
    text = _chord_map_text(chords)
    assert "bar 0: Dm7" in text
    assert "bar 1: G7" in text
    assert "bar 2: Cm9" in text


def test_chord_map_text_with_empty_list_returns_placeholder():
    assert "no chord" in _chord_map_text([]).lower()


def test_section_map_text_includes_energy_and_bar_range():
    sections = [
        Section(name="Intro", start_bar=0, end_bar=4, energy="low"),
        Section(name="Chorus", start_bar=8, end_bar=12, energy="high"),
    ]
    text = _section_map_text(sections)
    assert "Intro" in text
    assert "low" in text
    assert "Chorus" in text
    assert "high" in text
    assert "0" in text and "4" in text


def test_section_map_text_with_empty_list_returns_placeholder():
    assert "no section" in _section_map_text([]).lower()


def test_negotiation_etiquette_includes_scope_hint_when_batch_peers_provided():
    text = _negotiation_etiquette(["drums", "bass"])
    assert "drums" in text
    assert "bass" in text
    assert "only" in text.lower() or "group" in text.lower()


def test_negotiation_etiquette_no_scope_hint_when_no_peers():
    text = _negotiation_etiquette([])
    # should still return the base etiquette text
    assert "request" in text.lower()


def test_system_prompt_includes_chord_map_and_section_map():
    from llm_band.agents.instrument import _system_prompt
    from llm_band.domain.song_state import Header, RosterItem, ChordSpan, Section
    header = Header(
        genre="funk", key="D minor", tempo_bpm=110, num_bars=8,
        chord_progression=[ChordSpan(bar=i, chord="Dm7") for i in range(8)],
        sections=[Section(name="Verse", start_bar=0, end_bar=8, energy="medium")],
    )
    roster_item = RosterItem(
        id="bass", instrument="Electric Bass", midi_range=(28, 55),
        role="groove", playing_style="Lock to the kick.",
    )
    text = _system_prompt(header, roster_item)
    assert "Dm7" in text
    assert "Verse" in text
    assert "medium" in text
    assert "Lock to the kick." in text


def test_run_instrument_turn_accepts_batch_peer_ids():
    from llm_band.agents.instrument import InstrumentTurnOutput, run_instrument_turn
    from llm_band.domain.song_state import Header, Note, RosterItem

    class TurnLLM:
        def with_structured_output(self, schema):
            assert schema is InstrumentTurnOutput
            return self

        def invoke(self, _messages):
            return InstrumentTurnOutput(
                notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0)],
                notes_summary="bass root note",
            )

    header = Header(genre="funk", key="D minor", tempo_bpm=110, num_bars=4)
    bass = RosterItem(id="bass", instrument="Electric Bass", midi_range=(28, 55), role="groove")
    roster = [bass, RosterItem(id="drums", instrument="kit", role="beat", is_drum=True)]

    part, resolutions, new_requests = run_instrument_turn(
        header, bass, roster, {}, ["drums"], [], None, llm=TurnLLM()
    )
    assert part.instrument_id == "bass"
    assert resolutions == []
    assert new_requests == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest apps/api/tests/test_instrument.py::test_chord_map_text_formats_bar_chord_pairs apps/api/tests/test_instrument.py::test_run_instrument_turn_accepts_batch_peer_ids -v
```

Expected: FAIL — `_chord_map_text` not found, `run_instrument_turn` takes no `batch_peer_ids`.

- [ ] **Step 3: Update instrument.py**

Replace `apps/api/llm_band/agents/instrument.py` with:

```python
"""Instrument agent — composes one part.

Phase 4: single pass via `compose_part` (non-negotiation graph).
Phase 5: full negotiation via `run_instrument_turn`, called once per round per
         addressed instrument. The `batch_peer_ids` parameter scopes negotiation
         requests to instruments within the same composition group.
"""

from __future__ import annotations

from typing import Optional

from langsmith import get_current_run_tree, traceable
from pydantic import BaseModel, Field

from ..config import get_settings
from ..infrastructure.llm import LLMError
from ..music.theory import beats_per_bar
from ..music.validators import ValidationIssue, errors_only, validate_song
from ..domain.song_state import (
    ChordSpan,
    Header,
    NegotiationRequest,
    Note,
    Part,
    RosterItem,
    Section,
    SongState,
)

MAX_REPAIRS = 2
STRUCTURED_OUTPUT_RETRIES = 1


class InstrumentOutput(BaseModel):
    notes: list[Note] = Field(description="this instrument's notes for the whole song")
    notes_summary: str = Field(
        description="1-2 sentence compact summary peers can read instead of the full note list"
    )
    self_notes: str = Field(default="", description="optional notes to self for later revision")


def _chord_map_text(chord_progression: list[ChordSpan]) -> str:
    if not chord_progression:
        return "(no chord map provided)"
    lines = [f"  bar {cs.bar}: {cs.chord}" for cs in sorted(chord_progression, key=lambda x: x.bar)]
    return "Chord map:\n" + "\n".join(lines)


def _section_map_text(sections: list[Section]) -> str:
    if not sections:
        return "(no section map provided)"
    lines = [
        f"  {s.name:<14} bars {s.start_bar}-{s.end_bar}  energy: {s.energy}"
        for s in sections
    ]
    return "Song form:\n" + "\n".join(lines)


def _peer_context(roster: list[RosterItem], self_id: str, peer_summaries: dict[str, str]) -> str:
    lines = [
        f"- {r.id} ({r.instrument}, {r.role}): {peer_summaries.get(r.id, 'not composed yet')}"
        for r in roster
        if r.id != self_id
    ]
    return "\n".join(lines) or "(no other instruments)"


def _system_prompt(header: Header, roster_item: RosterItem) -> str:
    bpb = beats_per_bar(header.time_signature)
    drum_note = (
        " (percussion kit — pitch is a GM drum key, not a melodic pitch; range/key checks don't apply)"
        if roster_item.is_drum
        else ""
    )
    playing_style_block = (
        f"\nPlaying style: {roster_item.playing_style}" if roster_item.playing_style else ""
    )
    return (
        f"You are the {roster_item.instrument} player ({roster_item.role}) in a "
        f"{header.genre} ensemble.\n\n"
        f"Hard constraints:\n"
        f"- key: {header.key}, tempo: {header.tempo_bpm} BPM, "
        f"time signature {header.time_signature[0]}/{header.time_signature[1]} "
        f"({bpb} beats/bar)\n"
        f"- song length: {header.num_bars} bars (bar indices 0..{header.num_bars - 1})\n"
        f"- your MIDI pitch range: {roster_item.midi_range[0]}-{roster_item.midi_range[1]}{drum_note}\n\n"
        f"{_section_map_text(header.sections)}\n\n"
        f"{_chord_map_text(header.chord_progression)}"
        f"{playing_style_block}\n\n"
        "Compose your full part for the whole song: a list of notes with absolute bar "
        "+ start_beat (0-indexed within the bar), MIDI pitch (null = rest), duration in "
        "beats, and velocity (0-127). Shape your dynamics to the section energy levels "
        "(low = quieter/sparser, high = louder/fuller). Stay within your pitch range and "
        "bar/beat bounds. Also return a short notes_summary other musicians can read."
    )


def _repair_prompt(issues: list[ValidationIssue]) -> str:
    bullets = "\n".join(f"- {i.message}" for i in issues)
    return (
        "Your part had validation errors — return a complete, corrected part "
        f"(not a diff) that fixes:\n{bullets}"
    )


def _negotiation_etiquette(batch_peer_ids: list[str]) -> str:
    scope = (
        f" You may only raise requests to instruments in your current composition group: "
        f"{', '.join(batch_peer_ids)}. Do not address instruments outside this group."
        if batch_peer_ids
        else ""
    )
    return (
        "\nYou may also ask another instrument for a specific accommodation (e.g. "
        "leave space in a bar for a fill, change a note to fit a chord). Phrase each "
        "as: which instrument (by roster id), which bar(s), what you're asking, and why. "
        "Only raise a request if it meaningfully improves the arrangement — don't "
        "manufacture requests for their own sake." + scope
    )


def _validate_part(header: Header, roster_item: RosterItem, part: Part) -> list[ValidationIssue]:
    temp = SongState(request="", header=header, roster=[roster_item], parts={roster_item.id: part})
    return errors_only(validate_song(temp))


def _to_part(roster_item: RosterItem, out: InstrumentOutput) -> Part:
    return Part(
        instrument_id=roster_item.id,
        notes=out.notes,
        notes_summary=out.notes_summary,
        self_notes=out.self_notes,
    )


def _fallback_part(roster_item: RosterItem, reason: str = "model did not return structured output") -> Part:
    return Part(
        instrument_id=roster_item.id,
        notes=[],
        notes_summary=f"fallback: {reason}",
        self_notes=reason,
    )


def _invoke_structured(structured, messages, schema_name: str):
    last_error = None
    retries = max(0, get_settings().llm_max_retries)
    for attempt in range(retries + 1):
        try:
            out = structured.invoke(messages)
        except LLMError:
            raise
        except Exception as exc:
            last_error = exc
            out = None
        if out is not None:
            return out
        if attempt < retries:
            messages = messages + [
                (
                    "human",
                    f"Return only a valid {schema_name} object matching the requested structured schema. Do not return prose.",
                )
            ]
    if last_error is not None:
        return None
    return None


@traceable(run_type="chain", name="instrument:compose")
def compose_part(
    header: Header,
    roster_item: RosterItem,
    roster: list[RosterItem],
    peer_summaries: dict[str, str],
    llm=None,
) -> Part:
    """Compose one instrument's part, with a bounded repair loop on validation failure.

    Used by the non-negotiation graph (Phase 4 / `run_instruments`).
    """
    run = get_current_run_tree()
    if run is not None:
        run.name = roster_item.instrument
    if llm is None:
        from llm_band.infrastructure.gemini.llm import make_llm
        llm = make_llm("instrument")
    structured = llm.with_structured_output(InstrumentOutput)

    messages = [
        ("system", _system_prompt(header, roster_item)),
        ("human", f"Other instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"),
    ]
    out = _invoke_structured(structured, messages, "InstrumentOutput")
    if out is None:
        return _fallback_part(roster_item)
    part = _to_part(roster_item, out)

    for _ in range(MAX_REPAIRS):
        issues = _validate_part(header, roster_item, part)
        if not issues:
            break
        messages = messages + [
            ("ai", f"My part: {out.notes_summary}"),
            ("human", _repair_prompt(issues)),
        ]
        out = _invoke_structured(structured, messages, "InstrumentOutput")
        if out is None:
            return _fallback_part(roster_item)
        part = _to_part(roster_item, out)

    return part


# ---- Phase 5: negotiation turn ---------------------------------------------

class RequestResolution(BaseModel):
    request_id: str = Field(description="id of a pending request addressed to you")
    accepted: bool
    resolution: str = Field(description="short note on what you did (or why you declined)")


class NewRequest(BaseModel):
    to: str = Field(description="roster id of the instrument you're asking")
    bars: list[int] = Field(default_factory=list)
    request: str
    rationale: str


class InstrumentTurnOutput(InstrumentOutput):
    request_resolutions: list[RequestResolution] = Field(default_factory=list)
    new_requests: list[NewRequest] = Field(default_factory=list)


def _pending_context(pending: list[NegotiationRequest]) -> str:
    if not pending:
        return "(no pending requests addressed to you)"
    lines = [
        f"- [{r.id}] from {r.from_}, bars {r.bars}: {r.request} (why: {r.rationale})"
        for r in pending
    ]
    return "Pending requests addressed to you — accept (and patch your part) or decline each:\n" + "\n".join(lines)


@traceable(run_type="chain", name="instrument:turn")
def run_instrument_turn(
    header: Header,
    roster_item: RosterItem,
    roster: list[RosterItem],
    peer_summaries: dict[str, str],
    batch_peer_ids: list[str],
    pending: list[NegotiationRequest],
    existing_part: Optional[Part],
    llm=None,
) -> tuple[Part, list[RequestResolution], list[NewRequest]]:
    """One negotiation-round turn: revise (or compose on round 0) this instrument's
    part, resolve requests addressed to it, and optionally raise new ones.

    `batch_peer_ids` lists the other roster ids in this composition group — the
    negotiation etiquette block tells the model to only raise requests to those ids.
    """
    run = get_current_run_tree()
    if run is not None:
        run.name = roster_item.instrument
    if llm is None:
        from llm_band.infrastructure.gemini.llm import make_llm
        llm = make_llm("instrument")
    structured = llm.with_structured_output(InstrumentTurnOutput)

    messages = [
        ("system", _system_prompt(header, roster_item) + _negotiation_etiquette(batch_peer_ids)),
        ("human", f"Other instruments:\n{_peer_context(roster, roster_item.id, peer_summaries)}"),
    ]
    if existing_part is not None:
        messages.append(("ai", f"My current part: {existing_part.notes_summary}"))
    messages.append(("human", _pending_context(pending)))

    out = _invoke_structured(structured, messages, "InstrumentTurnOutput")
    if out is None:
        return _fallback_part(roster_item), [], []
    part = _to_part(roster_item, out)

    for _ in range(MAX_REPAIRS):
        issues = _validate_part(header, roster_item, part)
        if not issues:
            break
        messages = messages + [
            ("ai", f"My part: {out.notes_summary}"),
            ("human", _repair_prompt(issues)),
        ]
        out = _invoke_structured(structured, messages, "InstrumentTurnOutput")
        if out is None:
            return _fallback_part(roster_item), [], []
        part = _to_part(roster_item, out)

    return part, out.request_resolutions, out.new_requests
```

- [ ] **Step 4: Run all instrument tests**

```bash
uv run pytest apps/api/tests/test_instrument.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/llm_band/agents/instrument.py apps/api/tests/test_instrument.py
git commit -m "feat: enrich instrument prompts with chord map, section energy, playing style; add batch_peer_ids scope to negotiation"
```

---

## Task 7: graph.py — Batch sequencer

**Files:**
- Modify: `apps/api/llm_band/graph.py`
- Modify: `apps/api/tests/test_graph.py`
- Modify: `apps/api/tests/test_negotiation.py`

**Interfaces:**
- Consumes: all prior tasks
- Produces:
  - `_build_instruments_subgraph(llm)` — fan-out scoped to current batch
  - `_build_negotiation_graph(llm, max_rounds)` — batch sequencer (same public name, new implementation)
  - `run_negotiation(style, llm, max_rounds)` — unchanged signature
  - `iter_negotiation_events(style, llm, max_rounds)` — unchanged signature

- [ ] **Step 1: Write the failing tests**

```python
# Replace apps/api/tests/test_negotiation.py entirely:

"""Phase 5: batch sequencer graph — batches execute in order, intra-batch
mini-negotiation scoped to batch members, peer summaries propagate forward.
All LLMs mocked — no API key needed."""

from __future__ import annotations

import pytest
from langgraph.errors import GraphRecursionError

from llm_band.agents.arbiter import ArbiterOutput, ArbiterResolution
from llm_band.agents.instrument import InstrumentTurnOutput, NewRequest, RequestResolution
from llm_band.agents.director import DirectorOutput, ArrangementInstrument, ArrangementSection, CompositionGroup as DCompositionGroup
from llm_band.graph import _build_negotiation_graph, run_negotiation
from llm_band.domain.song_state import (
    ChordSpan, CompositionGroup, Header, Note, RosterItem, SongState,
)
from llm_band.infrastructure.llm import LLMQuotaExceeded

HEADER = Header(genre="funk", key="D minor", tempo_bpm=110, num_bars=4)
DRUMS = RosterItem(id="drums", instrument="kit", role="beat", is_drum=True)
BASS = RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="groove")
EPIANO = RosterItem(id="epiano", instrument="rhodes", midi_range=(48, 72), role="harmony")

GROUPS = [
    CompositionGroup(name="rhythm", instrument_ids=["drums", "bass"], max_negotiation_rounds=2),
    CompositionGroup(name="harmony", instrument_ids=["epiano"], max_negotiation_rounds=0),
]


def _make_director_output(roster, groups):
    return DirectorOutput(
        genre="funk", key="D minor", tempo_bpm=110,
        time_sig_numerator=4, time_sig_denominator=4, num_bars=4,
        sections=[ArrangementSection(name="Verse", start_bar=0, end_bar=4, energy="medium")],
        chord_progression=[ChordSpan(bar=i, chord="Dm7") for i in range(4)],
        instruments=[
            ArrangementInstrument(
                id=r.id, instrument=r.instrument, midi_program=0,
                midi_low=r.midi_range[0], midi_high=r.midi_range[1],
                role=r.role, playing_style="play your role", is_drum=r.is_drum,
            )
            for r in roster
        ],
        composition_groups=[
            DCompositionGroup(name=g.name, instrument_ids=g.instrument_ids, max_negotiation_rounds=g.max_negotiation_rounds)
            for g in groups
        ],
    )


class DirectorLLM:
    """Returns a pre-built DirectorOutput."""

    def __init__(self, director_output):
        self._output = director_output

    def with_structured_output(self, schema):
        from llm_band.agents.director import DirectorOutput as DO
        if schema is DO:
            return self
        raise AssertionError(f"DirectorLLM called with unexpected schema: {schema}")

    def invoke(self, _messages):
        return self._output


class ScriptedInstrumentLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def with_structured_output(self, schema):
        assert schema is InstrumentTurnOutput
        return self

    def invoke(self, _messages):
        out = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return out


class CombinedLLM:
    def __init__(self, director_output, instrument_script, arbiter_script=None):
        self._director = DirectorLLM(director_output)
        self._instrument = ScriptedInstrumentLLM(instrument_script)
        self._arbiter_script = arbiter_script or []
        self._arbiter_calls = 0

    def with_structured_output(self, schema):
        from llm_band.agents.director import DirectorOutput as DO
        from llm_band.agents.arbiter import ArbiterOutput as AO
        if schema is DO:
            return self._director
        if schema is ArbiterOutput:
            return self
        assert schema is InstrumentTurnOutput
        return self._instrument

    def invoke(self, _messages):
        # arbiter path
        out = self._arbiter_script[min(self._arbiter_calls, len(self._arbiter_script) - 1)] if self._arbiter_script else ArbiterOutput(resolutions=[])
        self._arbiter_calls += 1
        return out


def _silent_note(pitch=40) -> Note:
    return Note(bar=0, start_beat=0.0, pitch=pitch, dur=1.0)


def _turn(pitch=40, summary="ok", requests=None, resolutions=None) -> InstrumentTurnOutput:
    return InstrumentTurnOutput(
        notes=[_silent_note(pitch)],
        notes_summary=summary,
        new_requests=requests or [],
        request_resolutions=resolutions or [],
    )


def test_batches_execute_in_order_and_peer_summaries_propagate():
    """The epiano (batch 2) must see drums and bass summaries in peer context."""
    seen_peer_summaries = {}

    class SpyLLM:
        calls = 0

        def with_structured_output(self, schema):
            from llm_band.agents.director import DirectorOutput as DO
            if schema is DO:
                return DirectorLLM(_make_director_output([DRUMS, BASS, EPIANO], GROUPS))
            assert schema is InstrumentTurnOutput
            return self

        def invoke(self, messages):
            self.calls += 1
            human_text = "\n".join(m for role, m in messages if role == "human")
            # record what the epiano sees
            if "epiano" not in human_text or self.calls <= 2:
                return _turn(40, f"part_{self.calls}")
            seen_peer_summaries["epiano_saw"] = human_text
            return _turn(60, "epiano part")

    llm = SpyLLM()
    result = run_negotiation("funk", llm=llm)

    # epiano should see drums and bass summaries
    assert "epiano_saw" in seen_peer_summaries
    assert "part_1" in seen_peer_summaries["epiano_saw"] or "part_2" in seen_peer_summaries["epiano_saw"]
    assert "epiano" in result.parts
    assert "drums" in result.parts
    assert "bass" in result.parts


def test_intra_batch_negotiation_resolves_within_group():
    director_out = _make_director_output([DRUMS, BASS, EPIANO], GROUPS)
    instrument_script = [
        _turn(36, "drums round0", requests=[NewRequest(to="bass", bars=[0], request="leave beat 1", rationale="fill")]),
        _turn(40, "bass round0"),
        _turn(40, "bass round1", resolutions=[RequestResolution(request_id="req_0_drums_0", accepted=True, resolution="done")]),
        _turn(60, "epiano"),  # epiano batch, no negotiation
    ]
    llm = CombinedLLM(director_out, instrument_script)
    result = run_negotiation("funk", llm=llm)

    req = next((r for r in result.negotiation_requests if r.id == "req_0_drums_0"), None)
    assert req is not None
    assert req.status == "resolved"


def test_cross_batch_requests_are_not_dispatched_within_batch():
    """A request from the rhythm batch to epiano (harmony batch) must not
    trigger an epiano turn in the rhythm batch's negotiation rounds."""
    director_out = _make_director_output([DRUMS, BASS, EPIANO], GROUPS)
    instrument_calls = []

    class TrackingLLM:
        def with_structured_output(self, schema):
            from llm_band.agents.director import DirectorOutput as DO
            if schema is DO:
                return DirectorLLM(director_out)
            assert schema is InstrumentTurnOutput
            return self

        def invoke(self, messages):
            system_text = next((m for role, m in messages if role == "system"), "")
            instrument_calls.append(system_text[:40])
            if len(instrument_calls) <= 2:
                # drums raises a cross-batch request to epiano — should be ignored within rhythm batch
                return _turn(36, "rhythm", requests=[NewRequest(to="epiano", bars=[0], request="support me", rationale="texture")])
            return _turn(60, "epiano part")

    result = run_negotiation("funk", llm=TrackingLLM())
    # epiano should only get called once (in its own batch), not dragged into rhythm batch negotiation
    epiano_calls = sum(1 for s in instrument_calls if "epiano" in s.lower() or "rhodes" in s.lower())
    assert epiano_calls == 1


def test_zero_new_requests_exits_batch_early():
    director_out = _make_director_output([DRUMS, BASS], [
        CompositionGroup(name="rhythm", instrument_ids=["drums", "bass"], max_negotiation_rounds=2),
    ])
    instrument_script = [
        _turn(36, "drums no ask"),
        _turn(40, "bass no ask"),
    ]
    llm = CombinedLLM(director_out, instrument_script)
    result = run_negotiation("funk", llm=llm)

    assert llm._instrument.calls == 2  # only round 0 — no negotiation
    assert result.converged is True


def test_arbiter_resolves_surviving_requests_after_all_batches():
    director_out = _make_director_output([DRUMS, BASS], [
        CompositionGroup(name="rhythm", instrument_ids=["drums", "bass"], max_negotiation_rounds=1),
    ])
    # drums raises a request that bass never resolves → goes to arbiter
    instrument_script = [
        _turn(36, "drums", requests=[NewRequest(to="bass", bars=[0], request="leave space", rationale="fill")]),
        _turn(40, "bass round0"),
        _turn(40, "bass round1"),  # no resolutions
    ]
    arbiter_script = [
        ArbiterOutput(resolutions=[ArbiterResolution(request_id="req_0_drums_0", accepted=False, resolution="arbiter declined")])
    ]
    llm = CombinedLLM(director_out, instrument_script, arbiter_script)
    result = run_negotiation("funk", llm=llm)

    req = next((r for r in result.negotiation_requests if r.id == "req_0_drums_0"), None)
    assert req is not None
    assert req.status == "declined"
    assert result.converged is True
```

Also update `apps/api/tests/test_graph.py` to work with the new graph API — the `run_instruments` function is unchanged so most tests should still pass, but verify them:

```python
# run_instruments tests do not touch the negotiation graph — just verify they still pass
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest apps/api/tests/test_negotiation.py -v
```

Expected: FAIL (graph API changes not yet implemented).

- [ ] **Step 3: Implement the new graph.py**

Replace `apps/api/llm_band/graph.py` with:

```python
"""Composition graphs.

Phase 4: one-shot fan-out via `build_graph` / `run_instruments`.
Phase 5: batched sequential composition via `_build_negotiation_graph` /
         `run_negotiation` / `iter_negotiation_events`.

The batch sequencer graph:
  START → director → instruments (batch subgraph) → check_convergence
        → batch_next_round → instruments (intra-batch loop)
        → advance_batch → instruments (next batch)
        → arbiter → END

`composition_groups` from the director define the ordered batches. Each batch
runs its instruments in parallel, mini-negotiates up to `max_negotiation_rounds`,
then advances to the next batch. Prior-batch peer summaries are visible to all
later batches via `peer_summaries` in the shared state.
"""

from __future__ import annotations

from typing import Iterator, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .agents.arbiter import run_arbiter
from .agents.instrument import NewRequest, RequestResolution, compose_part, run_instrument_turn
from .config import get_settings
from .domain.song_state import CompositionGroup, Header, NegotiationRequest, Part, RosterItem, SongState
from .state import BandState, InstrumentsState, merge_parts, merge_requests, merge_summaries, take_latest


class _InstrumentPayload(TypedDict):
    header: Header
    roster_item: RosterItem
    roster: list[RosterItem]
    peer_summaries: dict[str, str]


def _dispatch(state: BandState) -> list[Send]:
    peer_summaries = {rid: p.notes_summary for rid, p in state["parts"].items() if p.notes_summary}
    return [
        Send(
            "instrument",
            {
                "header": state["header"],
                "roster_item": r,
                "roster": state["roster"],
                "peer_summaries": peer_summaries,
            },
        )
        for r in state["roster"]
    ]


def build_graph(llm=None):
    def _instrument_node(payload: _InstrumentPayload) -> dict:
        part = compose_part(
            payload["header"], payload["roster_item"], payload["roster"],
            payload["peer_summaries"], llm=llm,
        )
        return {"parts": {payload["roster_item"].id: part}}

    graph = StateGraph(BandState)
    graph.add_node("instrument", _instrument_node)
    graph.add_conditional_edges(START, _dispatch, ["instrument"])
    graph.add_edge("instrument", END)
    return graph.compile()


def run_instruments(song: SongState, llm=None) -> SongState:
    """Compose all roster parts in one shot and merge them onto `song`."""
    if not song.roster:
        return song
    app = build_graph(llm=llm)
    result = app.invoke({
        "request": song.request,
        "header": song.header,
        "roster": song.roster,
        "parts": dict(song.parts),
        "composition_groups": song.composition_groups,
        "current_group_index": 0,
        "batch_instrument_ids": [],
        "max_negotiation_rounds": 0,
        "negotiation_requests": [],
        "round": 0,
        "converged": False,
        "peer_summaries": {},
    })
    song.parts = result["parts"]
    return song


# ---- Phase 5: batch sequencer -----------------------------------------------


class _TurnPayload(TypedDict):
    header: Header
    roster_item: RosterItem
    roster: list[RosterItem]
    peer_summaries: dict[str, str]
    batch_peer_ids: list[str]
    pending: list[NegotiationRequest]
    existing_part: Optional[Part]
    round: int


def _new_requests_to_pending(
    from_id: str, round_num: int, new_requests: list[NewRequest]
) -> list[NegotiationRequest]:
    return [
        NegotiationRequest(
            id=f"req_{round_num}_{from_id}_{i}",
            from_=from_id,
            to=nr.to,
            round=round_num,
            bars=nr.bars,
            request=nr.request,
            rationale=nr.rationale,
            status="pending",
        )
        for i, nr in enumerate(new_requests)
    ]


def _resolutions_to_updates(
    pending_for_self: list[NegotiationRequest], resolutions: list[RequestResolution]
) -> list[NegotiationRequest]:
    by_id = {r.id: r for r in pending_for_self}
    updates = []
    for res in resolutions:
        orig = by_id.get(res.request_id)
        if orig is None:
            continue
        status = "resolved" if res.accepted else "declined"
        updates.append(orig.model_copy(update={"status": status, "resolution": res.resolution}))
    return updates


def _build_instruments_subgraph(llm=None):
    """Subgraph: one round of instrument turns for the current batch.

    On round 0 all batch members compose. On subsequent rounds only instruments
    that have pending requests addressed to them get a turn.
    Requests raised to instruments outside the batch are silently dropped —
    they belong to the arbiter.
    """

    def _dispatch_instruments(state: InstrumentsState) -> list[Send]:
        batch_ids = set(state["batch_instrument_ids"])
        roster_by_id = {r.id: r for r in state["roster"]}
        peer_summaries = state.get("peer_summaries", {})

        if state["round"] == 0:
            targets = [(r, []) for r in state["roster"] if r.id in batch_ids]
        else:
            pending = [r for r in state["negotiation_requests"] if r.status == "pending" and r.to in batch_ids]
            pending_by_to: dict[str, list[NegotiationRequest]] = {}
            for r in pending:
                pending_by_to.setdefault(r.to, []).append(r)
            targets = [
                (roster_by_id[to_id], reqs)
                for to_id, reqs in pending_by_to.items()
                if to_id in roster_by_id
            ]

        return [
            Send(
                "instrument_turn",
                {
                    "header": state["header"],
                    "roster_item": r,
                    "roster": state["roster"],
                    "peer_summaries": {k: v for k, v in peer_summaries.items() if k != r.id},
                    "batch_peer_ids": [bid for bid in state["batch_instrument_ids"] if bid != r.id],
                    "pending": reqs,
                    "existing_part": state["parts"].get(r.id) if state["round"] > 0 else None,
                    "round": state["round"],
                },
            )
            for r, reqs in targets
        ]

    def _instrument_turn_node(payload: _TurnPayload) -> dict:
        part, resolutions, new_requests = run_instrument_turn(
            payload["header"], payload["roster_item"], payload["roster"],
            payload["peer_summaries"], payload["batch_peer_ids"],
            payload["pending"], payload["existing_part"], llm=llm,
        )
        batch_ids = set(payload["batch_peer_ids"]) | {payload["roster_item"].id}
        updates = _resolutions_to_updates(payload["pending"], resolutions)
        all_new = _new_requests_to_pending(payload["roster_item"].id, payload["round"], new_requests)
        # Scope: only intra-batch requests are dispatched; cross-batch ones survive
        # to be resolved by the arbiter at the end.
        updates += all_new  # keep all (arbiter handles orphans)
        new_summary = (
            {payload["roster_item"].id: part.notes_summary} if part.notes_summary else {}
        )
        return {
            "parts": {payload["roster_item"].id: part},
            "negotiation_requests": updates,
            "peer_summaries": new_summary,
            "round": payload["round"],
        }

    subgraph = StateGraph(InstrumentsState)
    subgraph.add_node("instrument_turn", _instrument_turn_node)
    subgraph.add_conditional_edges(START, _dispatch_instruments, ["instrument_turn"])
    subgraph.add_edge("instrument_turn", END)
    return subgraph.compile()


def _build_negotiation_graph(llm=None, max_rounds: Optional[int] = None):
    instruments = _build_instruments_subgraph(llm=llm)

    def _director_node(state: BandState) -> dict:
        from .agents.director import run_director
        song = run_director(state["request"], llm=llm)
        first_group = song.composition_groups[0] if song.composition_groups else None
        return {
            "header": song.header,
            "roster": song.roster,
            "composition_groups": song.composition_groups,
            "current_group_index": 0,
            "round": 0,
            "batch_instrument_ids": first_group.instrument_ids if first_group else [r.id for r in song.roster],
            "max_negotiation_rounds": (
                max_rounds
                if max_rounds is not None
                else (first_group.max_negotiation_rounds if first_group else 1)
            ),
        }

    def _batch_next_round(state: BandState) -> dict:
        return {"round": state["round"] + 1}

    def _advance_batch(state: BandState) -> dict:
        next_idx = state["current_group_index"] + 1
        next_group = state["composition_groups"][next_idx]
        return {
            "current_group_index": next_idx,
            "round": 0,
            "batch_instrument_ids": next_group.instrument_ids,
            "max_negotiation_rounds": (
                max_rounds if max_rounds is not None else next_group.max_negotiation_rounds
            ),
        }

    def _check_convergence(state: BandState):
        batch_ids = set(state["batch_instrument_ids"])
        current_max = state["max_negotiation_rounds"]
        pending = [
            r for r in state["negotiation_requests"]
            if r.status == "pending" and r.to in batch_ids
        ]
        # `max_negotiation_rounds` counts rounds AFTER the initial composition (round 0).
        # round 0 = compose; rounds 1..max = negotiate. Check: current round < max.
        if pending and state["round"] < current_max:
            return "batch_next_round"
        if state["current_group_index"] + 1 < len(state["composition_groups"]):
            return "advance_batch"
        return "arbiter"

    def _arbiter_node(state: BandState) -> dict:
        pending = [r for r in state["negotiation_requests"] if r.status == "pending"]
        resolved = run_arbiter(pending, llm=llm) if pending else []
        return {"negotiation_requests": resolved, "converged": True}

    graph = StateGraph(BandState)
    graph.add_node("director", _director_node)
    graph.add_node("instruments", instruments)
    graph.add_node("batch_next_round", _batch_next_round)
    graph.add_node("advance_batch", _advance_batch)
    graph.add_node("arbiter", _arbiter_node)
    graph.add_edge(START, "director")
    graph.add_edge("director", "instruments")
    graph.add_conditional_edges(
        "instruments", _check_convergence,
        ["batch_next_round", "advance_batch", "arbiter"],
    )
    graph.add_edge("batch_next_round", "instruments")
    graph.add_edge("advance_batch", "instruments")
    graph.add_edge("arbiter", END)
    return graph.compile()


def _initial_band_state(request: str) -> dict:
    return {
        "request": request,
        "header": None,
        "roster": [],
        "composition_groups": [],
        "current_group_index": 0,
        "batch_instrument_ids": [],
        "max_negotiation_rounds": 1,
        "parts": {},
        "negotiation_requests": [],
        "round": 0,
        "converged": False,
        "peer_summaries": {},
    }


def run_negotiation(style: str, llm=None, max_rounds: Optional[int] = None) -> SongState:
    """Compose + negotiate via the batch sequencer."""
    settings_rounds = max_rounds if max_rounds is not None else get_settings().max_rounds
    app = _build_negotiation_graph(llm=llm, max_rounds=max_rounds)
    result = app.invoke(
        _initial_band_state(style),
        config={"recursion_limit": 4 * settings_rounds * 8 + 20},
    )
    return SongState(
        request=style,
        header=result["header"],
        roster=result["roster"],
        parts=result.get("parts", {}),
        composition_groups=result.get("composition_groups", []),
        negotiation_requests=result.get("negotiation_requests", []),
        round=result.get("round", 0),
        converged=result.get("converged", True),
    )


def iter_negotiation_events(
    style: str, llm=None, max_rounds: Optional[int] = None
) -> Iterator[tuple[dict, Optional[SongState]]]:
    """Same run as `run_negotiation` but streaming events."""
    settings_rounds = max_rounds if max_rounds is not None else get_settings().max_rounds
    app = _build_negotiation_graph(llm=llm, max_rounds=max_rounds)
    state: dict = _initial_band_state(style)
    song: Optional[SongState] = None

    stream = app.stream(
        state,
        config={"recursion_limit": 4 * settings_rounds * 8 + 20},
        stream_mode="updates",
        subgraphs=True,
    )
    for ns, chunk in stream:
        for node, update in chunk.items():
            if not update:
                continue

            if "parts" in update:
                state["parts"] = merge_parts(state["parts"], update["parts"])
            if "negotiation_requests" in update:
                state["negotiation_requests"] = merge_requests(
                    state["negotiation_requests"], update["negotiation_requests"]
                )
            if "peer_summaries" in update:
                state["peer_summaries"] = merge_summaries(
                    state.get("peer_summaries", {}), update["peer_summaries"]
                )
            if "round" in update:
                state["round"] = take_latest(state["round"], update["round"])
            if "converged" in update:
                state["converged"] = update["converged"]
            if "header" in update:
                state["header"] = update["header"]
            if "roster" in update:
                state["roster"] = update["roster"]
            if "composition_groups" in update:
                state["composition_groups"] = update["composition_groups"]

            if node == "director" and not ns:
                song = SongState(
                    request=style,
                    header=update["header"],
                    roster=update["roster"],
                    parts={},
                )
                yield {
                    "type": "director",
                    "source": "director",
                    "header": update["header"].model_dump(mode="json"),
                    "roster": [r.model_dump(mode="json") for r in update["roster"]],
                }, song

            elif node == "instrument_turn" and ns and song is not None:
                song.parts = state["parts"]
                song.negotiation_requests = state["negotiation_requests"]
                song.round = state["round"]
                instrument_id = next(iter(update["parts"]))
                reqs = update.get("negotiation_requests", [])
                yield {
                    "type": "agent_pass",
                    "round": update["round"],
                    "instrument_id": instrument_id,
                    "notes_summary": state["parts"][instrument_id].notes_summary,
                    "new_requests": [
                        r.model_dump(by_alias=True) for r in reqs if r.status == "pending"
                    ],
                    "resolved_requests": [
                        r.model_dump(by_alias=True) for r in reqs if r.status != "pending"
                    ],
                }, None

            elif node == "arbiter" and not ns and song is not None:
                song.converged = True
                song.negotiation_requests = state["negotiation_requests"]
                yield {
                    "type": "convergence",
                    "round": state["round"],
                    "converged": True,
                    "resolved_requests": [
                        r.model_dump(by_alias=True)
                        for r in update.get("negotiation_requests", [])
                    ],
                }, None

    if song is not None:
        song.parts = state["parts"]
        song.negotiation_requests = state["negotiation_requests"]
        song.round = state["round"]
        song.converged = state["converged"]
```

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest apps/api/tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/llm_band/graph.py apps/api/tests/test_negotiation.py apps/api/tests/test_graph.py
git commit -m "feat: replace negotiation graph with batched sequential composer; intra-batch mini-negotiation scoped to group"
```

---

## Self-Review Notes

- **Task 5 note:** `BandState` and `InstrumentsState` are declared as `dict` subclasses rather than `TypedDict` so that `Annotated` reducer fields work correctly. LangGraph requires this pattern. The type annotations serve tooling only.
- **Cross-batch requests:** the current design keeps cross-batch requests in `negotiation_requests` with status `pending` until the arbiter runs. The instrument prompt scope hint discourages raising them, but any that do appear are cleaned up by the arbiter at the end.
- **`run_instruments` (Phase 4):** receives the new `BandState` fields with defaults; `composition_groups` comes from `song.composition_groups` which defaults to `[]` for songs without groups — no breaking change.
- **`iter_negotiation_events` streaming:** the event types (`director`, `agent_pass`, `convergence`) are unchanged; downstream consumers (the API SSE endpoint) need no modification.
