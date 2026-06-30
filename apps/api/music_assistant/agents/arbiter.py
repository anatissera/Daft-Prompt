"""Arbiter — force-converges any negotiation requests still pending when the
round cap is hit. One LLM call decides accept/decline + a short resolution note
for each; it does not regenerate instrument parts (the negotiation rounds already
patch parts as requests are accepted) — this just freezes the bookkeeping so
nothing is left "pending" forever.
"""

from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel, Field

from ..domain.song_state import NegotiationRequest


class ArbiterResolution(BaseModel):
    request_id: str = Field(description="id of the pending request being resolved")
    accepted: bool
    resolution: str = Field(description="short note on the final call and why")


class ArbiterOutput(BaseModel):
    resolutions: list[ArbiterResolution]


def _prompt(pending: list[NegotiationRequest]) -> list[tuple[str, str]]:
    lines = [
        f"- [{r.id}] {r.from_} -> {r.to}, bars {r.bars}: {r.request} (why: {r.rationale})"
        for r in pending
    ]
    system = (
        "/no_think You are the arbiter for a band's arrangement negotiation. The round cap "
        "was reached with these requests still unresolved. Decide accept or decline "
        "for each, with a short resolution note. Resolve every request listed. "
        "Respond directly with the structured output only. Do not think out loud or write any reasoning."
    )
    return [("system", system), ("human", "\n".join(lines))]


@traceable(run_type="chain", name="arbiter")
def run_arbiter(pending: list[NegotiationRequest], llm=None) -> list[NegotiationRequest]:
    """Resolve every still-pending request. Never leaves one unresolved: anything
    the LLM doesn't address is auto-declined as a safety net."""
    if not pending:
        return []
    if llm is None:
        from music_assistant.infrastructure.gemini.llm import make_llm

        llm = make_llm("arbiter")
    structured = llm.with_structured_output(ArbiterOutput)
    out: ArbiterOutput = structured.invoke(_prompt(pending))

    by_id = {r.id: r for r in pending}
    resolved: list[NegotiationRequest] = []
    addressed: set[str] = set()
    for res in out.resolutions:
        orig = by_id.get(res.request_id)
        if orig is None:
            continue
        status = "resolved" if res.accepted else "declined"
        resolved.append(orig.model_copy(update={"status": status, "resolution": res.resolution}))
        addressed.add(res.request_id)

    for r in pending:
        if r.id not in addressed:
            resolved.append(
                r.model_copy(update={"status": "declined", "resolution": "auto-declined: round cap reached"})
            )
    return resolved
