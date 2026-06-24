"""Phase 4: instrument agent — single-pass composition + bounded repair loop
(LLM mocked — no API key needed)."""

from __future__ import annotations

import pytest

from llm_band.agents.instrument import (
    MAX_REPAIRS,
    InstrumentOutput,
    InstrumentTurnOutput,
    _peer_context,
    compose_part,
    run_instrument_turn,
)
from llm_band.domain.song_state import Header, Note, RosterItem
from llm_band.infrastructure.llm import LLMQuotaExceeded


class _FakeStructured:
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = 0

    def invoke(self, _messages):
        self.calls += 1
        # repeat the last output once exhausted, so a "never recovers" test doesn't crash
        out = self._outputs[min(self.calls - 1, len(self._outputs) - 1)]
        return out


class FakeLLM:
    def __init__(self, outputs):
        self.structured = _FakeStructured(outputs)

    def with_structured_output(self, schema):
        assert schema is InstrumentOutput
        return self.structured


HEADER = Header(genre="disco", key="C major", tempo_bpm=120, num_bars=4)
BASS = RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="groove")
ROSTER = [BASS, RosterItem(id="drums", instrument="kit", role="beat", is_drum=True)]


def _valid_output() -> InstrumentOutput:
    return InstrumentOutput(
        notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0, velocity=100)],
        notes_summary="root notes on the downbeat",
    )


def _out_of_range_output() -> InstrumentOutput:
    return InstrumentOutput(
        notes=[Note(bar=0, start_beat=0.0, pitch=10, dur=1.0, velocity=100)],  # below bass range
        notes_summary="too low",
    )


def test_compose_part_accepts_valid_output_first_try():
    llm = FakeLLM([_valid_output()])
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=llm)
    assert part.instrument_id == "bass"
    assert part.notes[0].pitch == 40
    assert llm.structured.calls == 1  # no repair needed


def test_compose_part_repairs_after_validation_failure():
    llm = FakeLLM([_out_of_range_output(), _valid_output()])
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=llm)
    assert part.notes[0].pitch == 40
    assert llm.structured.calls == 2  # one repair round-trip


def test_compose_part_never_crashes_when_repairs_exhausted():
    llm = FakeLLM([_out_of_range_output()])  # always invalid
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=llm)
    assert part.notes[0].pitch == 10  # shipped as-is
    assert llm.structured.calls == 1 + MAX_REPAIRS


def test_compose_part_falls_back_when_structured_output_is_none():
    llm = FakeLLM([None, None])
    part = compose_part(HEADER, BASS, ROSTER, {}, llm=llm)

    assert part.instrument_id == "bass"
    assert part.notes == []
    assert "structured output" in part.notes_summary
    assert llm.structured.calls == 2


def test_compose_part_propagates_quota_errors_instead_of_empty_fallback():
    class QuotaStructured:
        def invoke(self, _messages):
            raise LLMQuotaExceeded(provider="gemini", model="gemini-2.5-flash", detail="quota")

    class QuotaLLM:
        def with_structured_output(self, schema):
            assert schema is InstrumentOutput
            return QuotaStructured()

    with pytest.raises(LLMQuotaExceeded):
        compose_part(HEADER, BASS, ROSTER, {}, llm=QuotaLLM())


def test_run_instrument_turn_falls_back_when_structured_output_is_none():
    class TurnLLM(FakeLLM):
        def with_structured_output(self, schema):
            assert schema is InstrumentTurnOutput
            return self.structured

    llm = TurnLLM([None, None])
    part, resolutions, new_requests = run_instrument_turn(
        HEADER, BASS, ROSTER, {}, [], None, llm=llm
    )

    assert part.instrument_id == "bass"
    assert part.notes == []
    assert "structured output" in part.notes_summary
    assert resolutions == []
    assert new_requests == []
    assert llm.structured.calls == 2


def test_peer_context_uses_summary_strings_not_note_lists():
    text = _peer_context(ROSTER, "bass", {"drums": "four-on-the-floor kick"})
    assert "four-on-the-floor kick" in text
    assert "bass" not in text  # self excluded
    assert "[" not in text  # no serialized note list leaking in
