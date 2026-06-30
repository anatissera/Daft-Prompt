"""Phase 5: arbiter force-resolution (LLM mocked — no API key needed)."""

from __future__ import annotations

from music_assistant.agents.arbiter import ArbiterOutput, ArbiterResolution, run_arbiter
from music_assistant.domain.song_state import NegotiationRequest


def _req(rid: str) -> NegotiationRequest:
    return NegotiationRequest(id=rid, from_="bass", to="drums", round=0, request="x", rationale="y")


class _Structured:
    def __init__(self, resolutions):
        self.resolutions = resolutions
        self.calls = 0

    def invoke(self, _messages):
        self.calls += 1
        return ArbiterOutput(resolutions=self.resolutions)


class FakeLLM:
    def __init__(self, resolutions):
        self.structured = _Structured(resolutions)

    def with_structured_output(self, schema):
        assert schema is ArbiterOutput
        return self.structured


def test_arbiter_resolves_every_pending_request():
    pending = [_req("a"), _req("b")]
    llm = FakeLLM([
        ArbiterResolution(request_id="a", accepted=True, resolution="ok"),
        ArbiterResolution(request_id="b", accepted=False, resolution="no room"),
    ])
    resolved = run_arbiter(pending, llm=llm)
    by_id = {r.id: r for r in resolved}
    assert by_id["a"].status == "resolved"
    assert by_id["b"].status == "declined"
    assert all(r.status != "pending" for r in resolved)


def test_arbiter_auto_declines_anything_llm_skips():
    pending = [_req("a"), _req("b")]
    llm = FakeLLM([ArbiterResolution(request_id="a", accepted=True, resolution="ok")])
    resolved = run_arbiter(pending, llm=llm)
    by_id = {r.id: r for r in resolved}
    assert by_id["a"].status == "resolved"
    assert by_id["b"].status == "declined"
    assert "auto-declined" in by_id["b"].resolution


def test_arbiter_skips_llm_call_when_nothing_pending():
    llm = FakeLLM([])
    resolved = run_arbiter([], llm=llm)
    assert resolved == []
    assert llm.structured.calls == 0
