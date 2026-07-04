"""Phase 3: director agent (LLM mocked — no API key needed)."""

from __future__ import annotations

import pytest

from music_assistant.agents.director import (
    MAX_ROSTER,
    MAX_BARS,
    MIN_BARS,
    ArrangementInstrument,
    ArrangementSection,
    DirectorOutput,
    _prompt,
    arrangement_to_song,
    run_director,
)
from music_assistant.config import Settings
from music_assistant.domain.song_state import ChordSpan, CompositionGroup, Header, RosterItem, Section, SongState
from music_assistant.infrastructure.gemini.llm import make_llm


class _FakeStructured:
    def __init__(self, out):
        self.out = out

    def invoke(self, _prompt):
        return self.out


class FakeLLM:
    """Stands in for a LangChain chat model with .with_structured_output()."""

    def __init__(self, out):
        self.out = out

    def with_structured_output(self, schema):
        assert schema is DirectorOutput
        return _FakeStructured(self.out)


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


def test_run_director_maps_to_songstate():
    song = run_director("disco", llm=FakeLLM(_output(4)))
    assert song.request == "disco"
    assert song.header.key == "F# minor"
    assert song.header.time_signature == (4, 4)
    assert song.header.num_bars == 32
    assert len(song.roster) == 4
    assert song.parts == {}  # director sets no notes (Phase 4 does)
    assert song.roster[0].is_drum is True


def test_roster_is_capped():
    song = run_director("huge orchestra", llm=FakeLLM(_output(12)))
    assert len(song.roster) == MAX_ROSTER


def test_midi_range_is_normalized():
    out = _output(3)
    out.instruments[0].midi_low = 60
    out.instruments[0].midi_high = 40  # backwards on purpose
    song = arrangement_to_song("x", out)
    assert song.roster[0].midi_range == (40, 60)


def test_director_clamps_bar_count_and_sections():
    out = _output(3)
    out.num_bars = 160
    out.sections = [
        ArrangementSection(name="long", start_bar=0, end_bar=160),
        ArrangementSection(name="outside", start_bar=64, end_bar=100),
    ]

    song = arrangement_to_song("oversized", out)

    assert MIN_BARS <= song.header.num_bars <= MAX_BARS
    assert song.header.num_bars == MAX_BARS
    assert song.header.sections[0].end_bar == MAX_BARS
    assert song.header.sections[1].start_bar == MAX_BARS - 1
    assert song.header.sections[1].end_bar == MAX_BARS


def test_make_llm_requires_configuration():
    with pytest.raises(RuntimeError):
        make_llm("director", settings=Settings(llm_provider=None))


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
    with pytest.raises(Exception):
        CompositionGroup(name="x", instrument_ids=[], max_negotiation_rounds=5)


def test_song_state_has_composition_groups_defaulting_to_empty():
    song = SongState(
        request="test",
        header=Header(genre="funk", key="D minor", tempo_bpm=100, num_bars=8),
    )
    assert song.composition_groups == []


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
    with pytest.raises(ValueError, match="multiple"):
        arrangement_to_song("funk", out)


def test_arrangement_to_song_raises_on_instrument_missing_from_all_groups():
    out = _full_output()
    out.composition_groups = [
        CompositionGroup(name="a", instrument_ids=["drums", "bass"]),
        # epiano missing
    ]
    with pytest.raises(ValueError, match="not assigned"):
        arrangement_to_song("funk", out)


def _split_drums_output() -> DirectorOutput:
    """A director that wrongly split the kit into separate kick/snare/hat entries."""
    out = _full_output()
    out.instruments = [
        ArrangementInstrument(id="kick", instrument="Kick", midi_program=0,
                              midi_low=35, midi_high=36, role="kick", playing_style="x", is_drum=True),
        ArrangementInstrument(id="snare", instrument="Snare", midi_program=0,
                              midi_low=38, midi_high=40, role="snare", playing_style="x", is_drum=True),
        ArrangementInstrument(id="hat", instrument="Hi-hat", midi_program=0,
                              midi_low=42, midi_high=46, role="hat", playing_style="x", is_drum=True),
        ArrangementInstrument(id="bass", instrument="Electric Bass", midi_program=34,
                              midi_low=28, midi_high=55, role="bass", playing_style="x"),
        ArrangementInstrument(id="epiano", instrument="Rhodes", midi_program=5,
                              midi_low=48, midi_high=72, role="harmony", playing_style="x"),
    ]
    out.composition_groups = [
        CompositionGroup(name="rhythm", instrument_ids=["kick", "snare", "hat", "bass"], max_negotiation_rounds=1),
        CompositionGroup(name="harmony", instrument_ids=["epiano"], max_negotiation_rounds=0),
    ]
    return out


def test_split_percussion_collapses_to_single_drum_kit():
    song = arrangement_to_song("funk", _split_drums_output())
    drum_items = [r for r in song.roster if r.is_drum]
    assert len(drum_items) == 1
    assert drum_items[0].id == "drums"
    # the three split components are gone from the roster
    assert {r.id for r in song.roster} == {"drums", "bass", "epiano"}


def test_collapsed_drums_appear_once_in_composition_groups():
    song = arrangement_to_song("funk", _split_drums_output())
    rhythm = next(g for g in song.composition_groups if g.name == "rhythm")
    assert rhythm.instrument_ids == ["drums", "bass"]  # kick/snare/hat → one "drums"
    # validation passed: every roster id is in exactly one group
    grouped = [iid for g in song.composition_groups for iid in g.instrument_ids]
    assert sorted(grouped) == ["bass", "drums", "epiano"]


def test_single_drum_kit_is_left_unchanged():
    # the normal case (one is_drum item) must not be rewritten
    song = arrangement_to_song("funk", _full_output())
    drum_items = [r for r in song.roster if r.is_drum]
    assert len(drum_items) == 1
    assert drum_items[0].id == "drums"
    assert drum_items[0].instrument == "Acoustic Drums"  # not replaced by the canonical kit


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

# --- chord/form backfill via skills (plans/composition-skills.md step 2) ---


def test_empty_chord_progression_is_backfilled_for_every_bar():
    out = _full_output()
    out = out.model_copy(update={"chord_progression": []})
    song = arrangement_to_song("funk", out)
    covered = {span.bar for span in song.header.chord_progression}
    assert covered == set(range(song.header.num_bars))
    assert all(span.chord for span in song.header.chord_progression)


def test_backfill_is_deterministic():
    out = _full_output().model_copy(update={"chord_progression": []})
    first = arrangement_to_song("funk", out).header.chord_progression
    second = arrangement_to_song("funk", out).header.chord_progression
    assert [ (s.bar, s.chord) for s in first ] == [ (s.bar, s.chord) for s in second ]


def test_partial_chord_progression_keeps_director_spans_and_fills_gaps():
    out = _full_output()
    out = out.model_copy(update={"chord_progression": [ChordSpan(bar=3, chord="Gm7")]})
    song = arrangement_to_song("funk", out)
    by_bar = {span.bar: span.chord for span in song.header.chord_progression}
    assert by_bar[3] == "Gm7"
    assert set(by_bar) == set(range(song.header.num_bars))


def test_out_of_range_chord_spans_are_dropped_then_backfilled():
    out = _full_output()
    out = out.model_copy(
        update={"chord_progression": [ChordSpan(bar=99, chord="C"), ChordSpan(bar=-1, chord="C")]}
    )
    song = arrangement_to_song("funk", out)
    bars = [span.bar for span in song.header.chord_progression]
    assert bars == sorted(bars)
    assert all(0 <= bar < song.header.num_bars for bar in bars)


def test_full_progression_from_director_is_untouched():
    out = _full_output()
    song = arrangement_to_song("funk", out)
    assert all(span.chord == "Dm7" for span in song.header.chord_progression)


def test_empty_sections_get_a_suggested_form():
    out = _full_output().model_copy(update={"sections": []})
    song = arrangement_to_song("funk", out)
    assert song.header.sections
    assert song.header.sections[0].start_bar == 0
    assert song.header.sections[-1].end_bar == song.header.num_bars
