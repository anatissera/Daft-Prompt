"""Phase 3: director agent (LLM mocked — no API key needed)."""

from __future__ import annotations

import pytest

from llm_band.agents.director import (
    MAX_ROSTER,
    MAX_BARS,
    MIN_BARS,
    ArrangementInstrument,
    ArrangementSection,
    DirectorOutput,
    arrangement_to_song,
    run_director,
)
from llm_band.config import Settings
from llm_band.domain.song_state import ChordSpan, CompositionGroup, Header, RosterItem, Section, SongState
from llm_band.infrastructure.gemini.llm import make_llm


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
        sections=[ArrangementSection(name="verse", start_bar=0, end_bar=8)],
        instruments=[
            ArrangementInstrument(
                id=f"inst{k}", instrument="electric_bass", midi_program=33,
                midi_low=28, midi_high=55, role="groove", is_drum=(k == 0),
            )
            for k in range(n)
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
