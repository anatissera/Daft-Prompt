"""Conversational agent that delegates to explicit musical tools."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from music_assistant.application.music_tool_models import (
    ChatAgentDecision,
    AnswerProfileToolInput,
    ArtistStyleToolInput,
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
        invoker = self.chat_model.with_structured_output(ChatAgentDecision)
        messages = _decision_messages(
            request,
            web_research_enabled=bool(getattr(self.tools, "enable_web_research", True)),
        )
        decision = invoker.invoke(messages)
        if decision is None:
            decision = invoker.invoke(messages)
        if decision is None:
            raise RuntimeError("chat classifier returned no structured decision")
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
        if decision.tool in {"answer_profile", "answer_from_current_profile"}:
            return self.tools.answer_profile(
                AnswerProfileToolInput(reference_id=_required_reference(reference_id), question=request.message)
            )
        if decision.tool in {"compose", "compose_from_reference", "compose_music"}:
            return self.tools.request_composition(
                CompositionRequestToolInput(
                    composition_request=decision.composition_request or request.message,
                    reference_id=reference_id if decision.tool == "compose_from_reference" else None,
                    reference_ids=request.reference_ids if decision.tool == "compose_from_reference" else [],
                )
            )
        if decision.tool in {"research_song", "search_song_evidence"}:
            return self.tools.research_song(
                ResearchSongToolInput(
                    query=_research_query(decision, request.message),
                    song_title=decision.song_title,
                    artist_name=decision.song_artist,
                    featured_artists=decision.song_featured_artists,
                    requested_info=decision.requested_info,
                    original_query=decision.original_query or request.message,
                )
            )
        if decision.tool == "search_artist_or_band_profile":
            return self.tools.search_artist_or_band_profile(
                ArtistStyleToolInput(
                    artist_or_band_name=_required_artist_or_band(decision),
                    purpose=decision.purpose if decision.purpose in {"style_profile", "composition", "similarity"} else "style_profile",
                    wants_composition=decision.wants_composition,
                    composition_request=decision.composition_request or request.message,
                    original_query=decision.original_query or request.message,
                )
            )
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
        if decision.tool in {"get_tab_excerpt", "get_playable_part"}:
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
        if decision.tool == "edit_generated_song":
            return ToolOutput(
                tool="edit_generated_song",
                answer="I need the current generated song context before I can edit it.",
                intent="clarify",
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


def _required_artist_or_band(decision: ChatAgentDecision) -> str:
    return (decision.artist_or_band_name or decision.query or "").strip() or "__missing_artist_or_band__"


def _research_query(decision: ChatAgentDecision, user_message: str) -> str:
    if decision.research_scope == "song" and decision.song_title:
        query = " by ".join(
            part.strip() for part in [decision.song_title, decision.song_artist] if part and part.strip()
        )
        featured = decision.song_featured_artists or _explicit_featured_artists(user_message)
        if featured:
            query += " featuring " + " & ".join(featured)
        return query
    candidate = (decision.query or "").strip()
    # The original message can preserve a title/artist separator that an LLM
    # accidentally removed while "cleaning" the query.
    original_has_credit = bool(re.search(r"\s+(?:by|de)\s+", user_message, re.IGNORECASE))
    candidate_has_credit = bool(re.search(r"\s+(?:by|de)\s+", candidate, re.IGNORECASE))
    return user_message if original_has_credit and not candidate_has_credit else (candidate or user_message)


def _explicit_featured_artists(message: str) -> list[str]:
    match = re.search(r"\b(?:feat\.?|ft\.?|featuring)\s+(.+?)(?:\s+(?:use|uses|usa|tiene)\b|[?]|$)", message, re.IGNORECASE)
    if not match:
        return []
    value = match.group(1).strip(" .,")
    return [value] if value else []


def _decision_messages(request: Any, *, web_research_enabled: bool) -> list[dict[str, str]]:
    reference_context = request.reference_id or ", ".join(request.reference_ids) or "none"
    profile_context = getattr(request, "reference_context", "") or "No current profile."
    conversation_context = getattr(request, "conversation_context", "") or "No earlier turns in this session."
    research_instruction = (
        "Use research_song before answering about an unresearched named song. "
        "If the user asks to analyze a named song, use research_song with a clean title and artist query. "
        if web_research_enabled
        else "Web research is disabled for this session. Do not choose research_song or imply that a named song was looked up; "
        "briefly explain that ENABLE_WEB_RESEARCH=true enables song lookup. "
    )
    return [
        {
            "role": "system",
            "content": (
                "You are Daft Prompt's LLM tool router. Choose exactly one explicit tool action; do not answer directly. "
                f"{research_instruction}Identify whether the named entity is a song, artist/band, album, genre, era, "
                "or the current generated song. If the user asks factual info about a named song and no evidence profile exists, "
                "call action='search_song_evidence'. This includes chords, key, tabs, tempo, authorship, structure, sections, "
                "instrumentation, or lyrics-adjacent metadata. For a song, always populate research_scope='song', "
                "song_title, song_artist when present, song_featured_artists, requested_info, and original_query; preserve exact "
                "title, artist/band, featured artists, and user wording. If the user asks for artist/band similarity, style, "
                "influences, representative songs, or composition like an artist/band, call action='search_artist_or_band_profile' "
                "and populate artist_or_band_name, purpose, wants_composition, and composition_request when needed. "
                "If the user says this song, this reference, esta canción, or similar while a current reference is listed, "
                "use that current reference and call action='answer_from_current_profile' for factual questions. "
                "Use action='get_playable_part' for tabs, keys, piano roll, drum/bass/guitar parts from an existing profile. "
                "Use action='compose_music' for new MIDI generation. Use action='edit_generated_song' for natural-language edits "
                "to the current generated SongState. Use clarify only when the entity or task is genuinely ambiguous. "
                "Do not answer factual song questions from model memory; use public evidence/search tools. "
                "Do not classify an artist from keywords inside its name: Daft Punk is an artist, not the punk genre. "
                "If they ask to analyze an audio/file upload, clarify that Daft Prompt uses public evidence connectors instead of local audio analysis. "
                "Never request raw tabs/full lyrics. Reply in the same language as the user, including clarifications and teaching notes."
            ),
        },
        {"role": "system", "content": f"Current reference ids: {reference_context}"},
        {"role": "system", "content": f"Current reference profile context: {profile_context}"},
        {"role": "system", "content": f"Recent in-session conversation:\n{conversation_context}"},
        {"role": "user", "content": request.message},
    ]
