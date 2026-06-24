"""Phase 5: negotiation rounds — requests routed/resolved through shared state,
zero-new-requests early exit, round-cap force-convergence via the arbiter, and
the recursion_limit backstop. All LLMs mocked — no API key needed."""

from __future__ import annotations

import pytest
from langgraph.errors import GraphRecursionError

from llm_band.agents.arbiter import ArbiterOutput, ArbiterResolution
from llm_band.agents.instrument import InstrumentTurnOutput, NewRequest, RequestResolution
from llm_band.graph import _build_negotiation_graph, iter_negotiation_events, run_negotiation
from llm_band.domain.song_state import Header, Note, RosterItem, SongState
from llm_band.infrastructure.llm import LLMQuotaExceeded

HEADER = Header(genre="disco", key="C major", tempo_bpm=120, num_bars=4)
BASS = RosterItem(id="bass", instrument="electric_bass", midi_range=(28, 55), role="groove")
DRUMS = RosterItem(id="drums", instrument="kit", role="beat", is_drum=True)


def _song() -> SongState:
    return SongState(request="x", header=HEADER, roster=[BASS, DRUMS])


def _human_text(messages) -> str:
    return "\n".join(m for role, m in messages if role == "human")


class ScriptedInstrumentLLM:
    """Each call advances through a scripted list of InstrumentTurnOutput, keyed
    by call order (round 0: bass then drums; later rounds dispatched by `to`)."""

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


def test_negotiation_creates_routes_and_resolves_requests_through_shared_state():
    script = [
        InstrumentTurnOutput(  # round 0: bass
            notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0)],
            notes_summary="root notes",
            new_requests=[NewRequest(to="drums", bars=[1], request="leave beat 0 open", rationale="fill")],
        ),
        InstrumentTurnOutput(  # round 0: drums
            notes=[Note(bar=1, start_beat=0.0, pitch=36, dur=1.0)],
            notes_summary="four on the floor",
        ),
        InstrumentTurnOutput(  # round 1: drums (only addressee gets a turn)
            notes=[Note(bar=1, start_beat=0.5, pitch=36, dur=0.5)],
            notes_summary="left beat 0 of bar 1 open for bass",
            request_resolutions=[RequestResolution(request_id="req_0_bass_0", accepted=True, resolution="left space open")],
        ),
    ]
    llm = ScriptedInstrumentLLM(script)
    result = run_negotiation(_song(), llm=llm, max_rounds=3)

    assert llm.calls == 3  # bass round0, drums round0, drums round1 — bass never re-rolled
    req = next(r for r in result.negotiation_requests if r.id == "req_0_bass_0")
    assert req.status == "resolved"
    assert req.resolution == "left space open"
    # the visible accommodation: drums' bar-1 note moved off beat 0 as requested
    assert result.parts["drums"].notes[0].start_beat == 0.5
    assert result.converged is True


def test_zero_new_requests_exits_early_without_a_second_round():
    script = [
        InstrumentTurnOutput(notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0)], notes_summary="bass, no asks"),
        InstrumentTurnOutput(notes=[Note(bar=0, start_beat=0.0, pitch=36, dur=1.0)], notes_summary="drums, no asks"),
    ]
    llm = ScriptedInstrumentLLM(script)
    result = run_negotiation(_song(), llm=llm, max_rounds=5)

    assert llm.calls == 2  # only round 0 — no negotiation needed, no wasted rounds
    assert result.round == 0
    assert result.converged is True
    assert result.negotiation_requests == []


def test_round_cap_forces_arbiter_convergence_with_no_pending_left():
    class PingPongLLM:
        """Always raises a fresh request back at whoever it's negotiating with —
        would never converge on its own without the round cap."""

        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            text = _human_text(messages)
            target = "drums" if "drums" not in text else "bass"
            return InstrumentTurnOutput(
                notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0)],
                notes_summary="still negotiating",
                new_requests=[NewRequest(to=target, bars=[0], request="ping", rationale="pong")],
            )

    class ArbiterLLM:
        def with_structured_output(self, schema):
            assert schema is ArbiterOutput
            return self

        def invoke(self, messages):
            human = messages[-1][1]
            ids = [line.split("]")[0].lstrip("- [") for line in human.splitlines() if line.startswith("-")]
            return ArbiterOutput(
                resolutions=[ArbiterResolution(request_id=i, accepted=False, resolution="cap reached") for i in ids]
            )

    class CombinedLLM:
        def with_structured_output(self, schema):
            if schema is ArbiterOutput:
                return ArbiterLLM().with_structured_output(schema)
            return PingPongLLM().with_structured_output(schema)

    result = run_negotiation(_song(), llm=CombinedLLM(), max_rounds=3)

    assert result.round == 2  # hit the cap (rounds 0, 1, 2 -> next_round==3==max_rounds stops dispatch)
    assert result.converged is True
    assert all(r.status != "pending" for r in result.negotiation_requests)  # arbiter froze everything


def test_recursion_limit_is_a_real_backstop_independent_of_round_cap():
    """Even if the round-cap logic were absent/buggy, LangGraph's own
    recursion_limit must still stop a runaway negotiation."""

    class NeverConvergesLLM:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            text = _human_text(messages)
            target = "drums" if "drums" not in text else "bass"
            return InstrumentTurnOutput(
                notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0)],
                notes_summary="never settles",
                new_requests=[NewRequest(to=target, bars=[0], request="ping", rationale="pong")],
            )

    # max_rounds set absurdly high so the round cap never trips within a tiny
    # recursion_limit window — isolates the recursion_limit as the actual backstop.
    app = _build_negotiation_graph(llm=NeverConvergesLLM(), max_rounds=100_000)
    with pytest.raises(GraphRecursionError):
        app.invoke(
            {
                "header": HEADER, "roster": [BASS, DRUMS], "parts": {},
                "negotiation_requests": [], "round": 0, "converged": False,
            },
            config={"recursion_limit": 6},
        )


def test_iter_negotiation_events_keeps_song_updated_before_later_llm_error():
    class PartialThenQuotaLLM:
        calls = 0

        def with_structured_output(self, schema):
            assert schema is InstrumentTurnOutput
            return self

        def invoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                return InstrumentTurnOutput(
                    notes=[Note(bar=0, start_beat=0.0, pitch=40, dur=1.0)],
                    notes_summary="partial bass",
                )
            raise LLMQuotaExceeded(provider="gemini", model="gemini-2.5-flash", detail="quota")

    song = _song()
    stream = iter_negotiation_events(song, llm=PartialThenQuotaLLM(), max_rounds=3)
    first = next(stream)

    assert first["type"] == "agent_pass"
    assert song.parts["bass"].notes_summary == "partial bass"

    with pytest.raises(LLMQuotaExceeded):
        next(stream)
    assert song.parts["bass"].notes_summary == "partial bass"
