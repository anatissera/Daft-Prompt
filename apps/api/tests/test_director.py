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
    arrangement_to_song,
    run_director,
)
from music_assistant.config import Settings
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
