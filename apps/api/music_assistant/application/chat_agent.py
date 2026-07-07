"""Conversational agent that delegates to explicit musical tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from music_assistant.application.music_tool_models import (
    ChatAgentDecision,
    AnswerProfileToolInput,
    ChordsToolInput,
    CompositionRequestToolInput,
    InstrumentSummaryToolInput,
    InstrumentsToolInput,
    ResearchSongToolInput,
    SectionsToolInput,
    SongReferenceToolInput,
    TabExcerptToolInput,
    ToolOutput,
)
from music_assistant.ports.llm import ChatModel


class ChatAgentResult(BaseModel):
    intent: str
    reply: str
    reference_id: str | None = None
    tool_output: ToolOutput | None = None
    clarification: str | None = None


class ChatAgent:
    def __init__(self, *, chat_model: ChatModel, tools) -> None:
        self.chat_model = chat_model
        self.tools = tools

    def run(self, request: Any) -> ChatAgentResult:
        decision = self.chat_model.with_structured_output(ChatAgentDecision).invoke(
            _decision_messages(request)
        )
        output = self._execute(decision, request)
        if decision.tool == "clarify":
            clarification = decision.clarification or output.answer or "Which song or musical task should I use?"
            return ChatAgentResult(intent="clarify", reply=clarification, clarification=clarification, tool_output=output)
        if decision.tool == "off_topic":
            return ChatAgentResult(
                intent="off_topic",
                reply=decision.clarification or output.answer or "I can help with music research, analysis, and composition.",
                tool_output=output,
            )
        return ChatAgentResult(
            intent=output.intent,
            reply=output.answer or output.summary,
            reference_id=output.reference_id,
            tool_output=output,
            clarification=output.answer if output.intent == "clarify" else None,
        )

    def _execute(self, decision: ChatAgentDecision, request: ChatRequest) -> ToolOutput:
        reference_id = decision.reference_id or request.reference_id
        if decision.tool == "answer_profile":
            return self.tools.answer_profile(
                AnswerProfileToolInput(reference_id=_required_reference(reference_id), question=request.message)
            )
        if decision.tool in {"compose", "compose_from_reference"}:
            return self.tools.request_composition(
                CompositionRequestToolInput(
                    composition_request=decision.composition_request or request.message,
                    reference_id=reference_id if decision.tool == "compose_from_reference" else None,
                    reference_ids=request.reference_ids if decision.tool == "compose_from_reference" else [],
                )
            )
        if decision.tool == "research_song":
            return self.tools.research_song(ResearchSongToolInput(query=decision.query or request.message))
        if decision.tool == "get_song_profile":
            return self.tools.get_song_profile(SongReferenceToolInput(reference_id=_required_reference(reference_id)))
        if decision.tool == "get_chords":
            return self.tools.get_chords(
                ChordsToolInput(reference_id=_required_reference(reference_id), section_name=decision.section_name)
            )
        if decision.tool == "get_sections":
            return self.tools.get_sections(SectionsToolInput(reference_id=_required_reference(reference_id)))
        if decision.tool == "get_instruments":
            return self.tools.get_instruments(
                InstrumentsToolInput(reference_id=_required_reference(reference_id), instrument=decision.instrument)
            )
        if decision.tool == "get_instrument_summary":
            return self.tools.get_instrument_summary(
                InstrumentSummaryToolInput(
                    reference_id=_required_reference(reference_id),
                    instrument=decision.instrument or "instrument",
                )
            )
        if decision.tool == "get_tab_excerpt":
            return self.tools.get_tab_excerpt(
                TabExcerptToolInput(
                    reference_id=_required_reference(reference_id),
                    instrument=decision.instrument or "guitar",
                    start_measure=decision.start_measure or 0,
                    measure_count=decision.measure_count or 4,
                )
            )
        if decision.tool == "get_conflicts":
            return self.tools.get_conflicts(SongReferenceToolInput(reference_id=_required_reference(reference_id)))
        if decision.tool == "get_missing_data":
            return self.tools.get_missing_data(SongReferenceToolInput(reference_id=_required_reference(reference_id)))
        if decision.tool == "request_composition":
            return self.tools.request_composition(
                CompositionRequestToolInput(
                    composition_request=decision.composition_request or request.message,
                    reference_id=reference_id,
                    reference_ids=request.reference_ids,
                )
            )
        if decision.tool == "off_topic":
            return ToolOutput(tool="off_topic", answer=decision.clarification or "Music only.", intent="off_topic")
        return ToolOutput(
            tool="clarify",
            answer=decision.clarification or "Which song or musical task should I use?",
            intent="clarify",
        )


def _required_reference(reference_id: str | None) -> str:
    if reference_id is None:
        return "__missing_reference__"
    return reference_id


def _decision_messages(request: Any) -> list[dict[str, str]]:
    reference_context = request.reference_id or ", ".join(request.reference_ids) or "none"
    profile_context = getattr(request, "reference_context", "") or "No current profile."
    return [
        {
            "role": "system",
            "content": (
                "You are LLMinem's chat agent. Choose exactly one explicit music tool. "
                "Use research_song before answering about an unresearched named song. "
                "Use get_chords/get_sections/get_instruments/get_instrument_summary/get_tab_excerpt "
                "for existing profiles. Use request_composition for composition and keep composition "
                "delegated to the composer/orchestrator. If the user says this song, this reference, "
                "esta canción, or similar while a current reference is listed, use that current reference; "
                "do not ask which song. Never answer from memory or request raw tabs/full lyrics."
            ),
        },
        {"role": "system", "content": f"Current reference ids: {reference_context}"},
        {"role": "system", "content": f"Current reference profile context: {profile_context}"},
        {"role": "user", "content": request.message},
    ]
