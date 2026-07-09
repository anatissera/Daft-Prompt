"""Explicit musical tools used by the conversational chat agent."""

from __future__ import annotations

from typing import Any

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.composition_brief import BuildCompositionBrief
from music_assistant.application.compose_song import ComposeSong
from music_assistant.application.language import is_spanish
from music_assistant.application.reference_instruments import ReferenceInstrumentProfileBuilder
from music_assistant.application.reference_transfer_intent import BuildReferenceTransferIntent
from music_assistant.application.music_tool_models import (
    AnswerToolOutput,
    AnswerProfileToolInput,
    ChordsToolInput,
    CompositionRequestToolInput,
    CompositionToolOutput,
    InstrumentsToolInput,
    InstrumentsToolOutput,
    ProfileToolOutput,
    ResearchSongToolInput,
    ResearchSongToolOutput,
    SectionsToolInput,
    SongReferenceToolInput,
    TabExcerptMeasure,
    TabExcerptEvent,
    TabExcerptToolInput,
    TabExcerptToolOutput,
    ToolOutput,
    TrackIndexItem,
    InstrumentSummaryToolInput,
)
from music_assistant.application.profile_queries import ProfileQueryTools
from music_assistant.domain.audio_profile import (
    ExplanationAnswer,
    ReferenceInstrumentProfile,
    ReferenceProfile,
    ReferenceTransferIntent,
    ReferenceTransferItem,
)
from music_assistant.domain.errors import OffTopicRequest
from music_assistant.ports.llm import ChatModel
from music_assistant.ports.reference_store import ReferenceStore
from music_assistant.ports.song_researcher import SongResearcher
from music_assistant.ports.songsterr_tab_store import SongsterrTabStore


class MusicTools:
    def __init__(
        self,
        *,
        reference_store: ReferenceStore,
        answer_music_question: AnswerMusicQuestion,
        song_researcher: SongResearcher | None = None,
        compose_song: ComposeSong | None = None,
        songsterr_tab_store: SongsterrTabStore | None = None,
        chat_model: ChatModel | None = None,
        enable_web_research: bool = False,
    ) -> None:
        self.reference_store = reference_store
        self.answer_music_question = answer_music_question
        self.song_researcher = song_researcher
        self.compose_song = compose_song
        self.songsterr_tab_store = songsterr_tab_store
        self.chat_model = chat_model
        self.enable_web_research = enable_web_research
        self.profile_queries = ProfileQueryTools()

    def research_song(self, payload: ResearchSongToolInput) -> ResearchSongToolOutput:
        if not self.enable_web_research:
            return ResearchSongToolOutput(
                answer=(
                    "La búsqueda web está desactivada en esta instancia."
                    if is_spanish(payload.query)
                    else "Web research is disabled in this instance."
                ),
                error="web_research_disabled",
                intent="clarify",
            )
        if self.song_researcher is None:
            return ResearchSongToolOutput(
                answer="Song research is not configured.",
                error="song_researcher_missing",
                intent="clarify",
            )
        profile = self.song_researcher.research(payload.query)
        self.reference_store.save(profile)
        evidence_count = len(profile.knowledge.evidence_claims) if profile.knowledge else 0
        instrument_summary = _instrument_profile_summary(profile, self.songsterr_tab_store)
        return ResearchSongToolOutput(
            reference_id=profile.reference_id,
            answer=_research_song_answer(profile, instrument_summary),
            summary=profile.summary or "",
            evidence_count=evidence_count,
            evidence=_profile_evidence_summary(profile),
            instrument_profile_summary=instrument_summary,
        )

    def get_song_profile(self, payload: SongReferenceToolInput) -> ProfileToolOutput:
        profile = self._profile(payload.reference_id)
        if profile is None:
            return ProfileToolOutput(
                reference_id=payload.reference_id,
                answer="I could not find that reference profile.",
                error="reference_not_found",
            )
        knowledge = profile.knowledge
        if knowledge is None:
            return ProfileToolOutput(
                reference_id=profile.reference_id,
                answer="This reference does not have a song knowledge profile yet.",
                error="knowledge_missing",
            )
        sources = sorted({claim.source_name for claim in knowledge.evidence_claims})
        index = knowledge.metadata.get("songsterr_tab_index") if isinstance(knowledge.metadata, dict) else {}
        return ProfileToolOutput(
            reference_id=profile.reference_id,
            answer=profile.summary or f"Profile for {knowledge.identity.title}.",
            summary=profile.summary or "",
            title=knowledge.identity.title,
            artist=knowledge.identity.artist,
            sources=sources,
            songsterr_tab_index=index or {},
            instrument_profile_summary=_instrument_profile_summary(profile, self.songsterr_tab_store),
            evidence=_profile_evidence_summary(profile),
        )

    def answer_profile(self, payload: AnswerProfileToolInput) -> AnswerToolOutput:
        profile = self._profile(payload.reference_id)
        if profile is None:
            return AnswerToolOutput(
                tool="answer_profile",
                reference_id=payload.reference_id,
                answer="I could not find that reference profile.",
                error="reference_not_found",
            )
        answer = self.answer_music_question.execute(payload.question, profile)
        return AnswerToolOutput(
            tool="answer_profile",
            reference_id=profile.reference_id,
            answer=answer.answer,
            evidence=answer.evidence,
            explanation=answer,
        )

    def get_chords(self, payload: ChordsToolInput) -> AnswerToolOutput:
        return self._profile_query(
            tool="get_chords",
            reference_id=payload.reference_id,
            question=(
                f"What chords are in the {payload.section_name}?"
                if payload.section_name
                else "What chords are in this song?"
            ),
            query=lambda profile: self.profile_queries.chords(profile.knowledge, payload.section_name),  # type: ignore[arg-type]
        )

    def get_sections(self, payload: SectionsToolInput) -> AnswerToolOutput:
        return self._profile_query(
            tool="get_sections",
            reference_id=payload.reference_id,
            question="What sections are known?",
            query=lambda profile: self.profile_queries.sections(profile.knowledge),  # type: ignore[arg-type]
        )

    def get_conflicts(self, payload: SongReferenceToolInput) -> AnswerToolOutput:
        return self._profile_query(
            tool="get_conflicts",
            reference_id=payload.reference_id,
            question="What source conflicts exist?",
            query=lambda profile: self.profile_queries.conflicts(profile.knowledge),  # type: ignore[arg-type]
        )

    def get_missing_data(self, payload: SongReferenceToolInput) -> AnswerToolOutput:
        return self._profile_query(
            tool="get_missing_data",
            reference_id=payload.reference_id,
            question="What data is missing?",
            query=lambda profile: self.profile_queries.missing_data(profile.knowledge),  # type: ignore[arg-type]
        )

    def get_instruments(self, payload: InstrumentsToolInput) -> InstrumentsToolOutput:
        profile = self._profile(payload.reference_id)
        if profile is None or profile.knowledge is None:
            return InstrumentsToolOutput(
                reference_id=payload.reference_id,
                answer="I could not find instrument evidence for that reference.",
                error="reference_not_found",
            )
        index = profile.knowledge.metadata.get("songsterr_tab_index") or {}
        tracks = [
            TrackIndexItem(
                instrument=str(track.get("instrument", "")),
                name=str(track.get("name", "")),
                part_id=int(track.get("part_id", 0)),
            )
            for track in index.get("tracks", [])
            if isinstance(track, dict)
        ]
        instruments = [str(item) for item in index.get("instruments", [])]
        if payload.instrument:
            needle = _normalize_instrument(payload.instrument)
            tracks = [track for track in tracks if _normalize_instrument(track.instrument) == needle]
            instruments = [item for item in instruments if _normalize_instrument(item) == needle]
        if not index:
            answer = "I do not have loaded Songsterr instrument tabs for this song yet."
        elif tracks:
            answer = "Loaded Songsterr instruments: " + ", ".join(instruments) + "."
        else:
            answer = f"I do not have {payload.instrument}-specific Songsterr tab data for this song yet."
        return InstrumentsToolOutput(
            reference_id=profile.reference_id,
            answer=answer,
            loaded=bool(index.get("loaded")),
            instruments=instruments,
            tracks=tracks,
            sections=[str(section) for section in index.get("sections", [])],
            source_urls=[str(url) for url in index.get("source_urls", [])],
            warnings_count=int(index.get("warnings_count", 0)),
            evidence=[f"songsterr:index:tracks={len(tracks)}"] if index else [],
        )

    def get_instrument_summary(self, payload: InstrumentSummaryToolInput) -> AnswerToolOutput:
        profile = self._profile(payload.reference_id)
        if profile is None:
            return AnswerToolOutput(
                tool="get_instrument_summary",
                reference_id=payload.reference_id,
                answer="I could not find that reference profile.",
                error="reference_not_found",
            )
        answer = self.answer_music_question.execute(f"What does the {payload.instrument} do?", profile)
        return AnswerToolOutput(
            tool="get_instrument_summary",
            reference_id=profile.reference_id,
            answer=answer.answer,
            evidence=answer.evidence,
            explanation=answer,
        )

    def get_tab_excerpt(self, payload: TabExcerptToolInput) -> TabExcerptToolOutput:
        if self.songsterr_tab_store is None:
            return TabExcerptToolOutput(
                reference_id=payload.reference_id,
                instrument=payload.instrument,
                answer="Songsterr tab storage is not configured.",
                error="songsterr_store_missing",
            )
        bundle = self.songsterr_tab_store.get(payload.reference_id)
        if bundle is None:
            return TabExcerptToolOutput(
                reference_id=payload.reference_id,
                instrument=payload.instrument,
                answer="I do not have loaded Songsterr tab data for this reference.",
                error="songsterr_bundle_missing",
            )
        tracks = bundle.tracks_for_instrument(payload.instrument)
        if not tracks:
            return TabExcerptToolOutput(
                reference_id=payload.reference_id,
                instrument=payload.instrument,
                answer=f"I do not have {payload.instrument}-specific Songsterr tab data for this song yet.",
                error="instrument_missing",
            )
        track = tracks[0]
        selected = track.measures[payload.start_measure : payload.start_measure + payload.measure_count]
        measures = [
            TabExcerptMeasure(
                index=measure.index,
                marker=measure.marker,
                note_events=sum(1 for event in measure.events if not event.rest),
                durations=_unique_durations(measure.events),
                events=[
                    TabExcerptEvent(
                        beat_index=event.beat_index,
                        duration=event.duration,
                        string=event.string,
                        fret=event.fret,
                        pitch=event.pitch,
                        rest=event.rest,
                        tie=event.tie,
                        ghost=event.ghost,
                    )
                    for event in measure.events
                ],
            )
            for measure in selected
        ]
        marker_text = ", ".join(measure.marker for measure in selected if measure.marker) or "no markers"
        summary = (
            f"{track.instrument_family.title()} excerpt from Songsterr track {track.name}: "
            f"measures {payload.start_measure}-{payload.start_measure + max(len(selected) - 1, 0)}, "
            f"{sum(measure.note_events for measure in measures)} note events, markers: {marker_text}."
        )
        return TabExcerptToolOutput(
            reference_id=payload.reference_id,
            answer=summary,
            summary=summary,
            evidence=[f"songsterr:part:{track.part_id}:excerpt_measures={len(measures)}"],
            instrument=track.instrument_family,
            track_name=track.name,
            tuning=track.tuning,
            measures=measures,
        )

    def request_composition(self, payload: CompositionRequestToolInput) -> CompositionToolOutput:
        if self.compose_song is None:
            return CompositionToolOutput(
                answer="Composition is not configured.",
                error="compose_song_missing",
                intent="compose",
            )
        profiles = self._profiles(payload.reference_id, payload.reference_ids)
        try:
            if profiles and all(profile.knowledge is not None for profile in profiles):
                instrument_profiles = {
                    profile.reference_id: ReferenceInstrumentProfileBuilder(
                        songsterr_tab_store=self.songsterr_tab_store,
                    ).build(profile)
                    for profile in profiles
                }
                has_instrument_profiles = any(instruments for instruments in instrument_profiles.values())
                if has_instrument_profiles:
                    operational_notes: list[str] = []
                    intent_result = BuildReferenceTransferIntent(chat_model=self.chat_model).execute(
                        payload.composition_request,
                        instrument_profiles,
                    )
                    if intent_result.clarification:
                        operational_notes = _operational_clarification_notes(
                            intent_result.clarification,
                            instrument_profiles,
                            payload.composition_request,
                        )
                        if operational_notes:
                            intent_result.intent = _default_reference_transfer_intent(instrument_profiles)
                            intent_result.clarification = None
                        else:
                            return CompositionToolOutput(
                                reference_id=profiles[0].reference_id,
                                answer=intent_result.clarification,
                                error="clarification_needed",
                                intent="compose_from_reference",
                            )
                    if intent_result.intent is not None:
                        intent_result.intent = _filter_transfer_intent_to_available_instruments(
                            intent_result.intent,
                            instrument_profiles,
                            payload.composition_request,
                        )
                        built = BuildCompositionBrief().execute(
                            payload.composition_request,
                            [profile.knowledge for profile in profiles if profile.knowledge is not None],
                            transfer_intent=intent_result.intent,
                            instrument_profiles=instrument_profiles,
                        )
                        assert built.brief is not None
                        if operational_notes:
                            built.brief.uncertainty_notes.extend(operational_notes)
                        song, source = self.compose_song.compose(built.brief)
                        warnings = _composition_warnings(song)
                        warnings.extend(note for note in operational_notes if note not in warnings)
                        return CompositionToolOutput(
                            reference_id=profiles[0].reference_id,
                            answer=_compose_tool_answer(song, source, warnings=warnings),
                            song=song,
                            source=source,
                            intent="compose_from_reference",
                            reference_transfer_intent=intent_result.intent.model_dump(mode="json"),
                            instrument_requests_summary=_instrument_requests_summary(built.brief.instrument_requests),
                            literal_applications=_literal_applications_summary(built.brief.instrument_requests),
                            uncertainty_notes=list(built.brief.uncertainty_notes),
                            warnings=warnings,
                        )
                built = BuildCompositionBrief().execute(
                    payload.composition_request,
                    [profile.knowledge for profile in profiles if profile.knowledge is not None],
                )
                if built.clarification:
                    return CompositionToolOutput(
                        reference_id=profiles[0].reference_id,
                        answer=built.clarification,
                        error="clarification_needed",
                        intent="compose_from_reference",
                    )
                if built.brief is not None:
                    song, source = self.compose_song.compose(built.brief)
                    warnings = _composition_warnings(song)
                    return CompositionToolOutput(
                        reference_id=profiles[0].reference_id,
                        answer=_compose_tool_answer(song, source, warnings=warnings),
                        song=song,
                        source=source,
                        intent="compose_from_reference",
                        instrument_requests_summary=_instrument_requests_summary(built.brief.instrument_requests),
                        literal_applications=_literal_applications_summary(built.brief.instrument_requests),
                        uncertainty_notes=list(built.brief.uncertainty_notes),
                        warnings=warnings,
                    )
            song, source = self.compose_song.compose(payload.composition_request)
        except OffTopicRequest as refusal:
            return CompositionToolOutput(answer=refusal.message, error="off_topic", intent="compose")
        warnings = _composition_warnings(song)
        return CompositionToolOutput(
            answer=_compose_tool_answer(song, source, warnings=warnings),
            song=song,
            source=source,
            intent="compose",
            warnings=warnings,
        )

    def _profile(self, reference_id: str) -> ReferenceProfile | None:
        return self.reference_store.get(reference_id)

    def _profiles(self, reference_id: str | None, reference_ids: list[str]) -> list[ReferenceProfile]:
        ids = list(reference_ids)
        if reference_id and reference_id not in ids:
            ids.insert(0, reference_id)
        return [profile for ref_id in ids if (profile := self.reference_store.get(ref_id)) is not None]

    def _profile_query(self, *, tool: str, reference_id: str, question: str, query) -> AnswerToolOutput:
        profile = self._profile(reference_id)
        if profile is None:
            return AnswerToolOutput(
                tool=tool,
                reference_id=reference_id,
                answer="I could not find that reference profile.",
                error="reference_not_found",
            )
        if profile.knowledge is None:
            answer = self.answer_music_question.execute(question, profile)
            return AnswerToolOutput(
                tool=tool,
                reference_id=reference_id,
                answer=answer.answer,
                evidence=answer.evidence,
                explanation=answer,
            )
        result = query(profile)
        explanation = ExplanationAnswer(reference_id=reference_id, answer=result.answer, evidence=result.evidence)
        return AnswerToolOutput(
            tool=tool,
            reference_id=reference_id,
            answer=result.answer,
            evidence=result.evidence,
            explanation=explanation,
        )


def _profile_evidence_summary(profile: ReferenceProfile) -> list[str]:
    if profile.knowledge is None:
        return []
    return [
        f"{claim.claim_type}:{claim.source_name}:{claim.confidence}"
        for claim in profile.knowledge.evidence_claims[:8]
    ]


def _research_song_answer(profile: ReferenceProfile, instrument_summary: list[dict]) -> str:
    bits: list[str] = []
    if profile.summary:
        bits.append(profile.summary)
    audio = profile.audio
    facts = []
    if audio is not None and audio.tempo_bpm is not None:
        facts.append(f"tempo {audio.tempo_bpm:g} BPM")
    if audio is not None and audio.key:
        facts.append(f"key {audio.key}")
    if facts:
        bits.append("Found " + ", ".join(facts) + ".")
    instruments = [
        str(item.get("instrument_family") or item.get("track_name"))
        for item in instrument_summary
        if item.get("instrument_family") or item.get("track_name")
    ]
    if instruments:
        bits.append("Loaded Songsterr instruments: " + ", ".join(instruments) + ".")
    return " ".join(bits) or "Research ready from source-backed evidence."


def _instrument_profile_summary(profile: ReferenceProfile, songsterr_tab_store: SongsterrTabStore | None) -> list[dict]:
    summaries: list[dict] = []
    for instrument_profile in ReferenceInstrumentProfileBuilder(songsterr_tab_store=songsterr_tab_store).build(profile).values():
        memory = instrument_profile.musical_memory
        summaries.append(
            {
                "instrument_family": instrument_profile.instrument_family,
                "track_name": instrument_profile.track_name,
                "confidence": instrument_profile.confidence,
                "midi_program": instrument_profile.timbre.midi_program,
                "note_packs": [
                    {
                        "note_pack_id": pack.pack_id,
                        "section_name": pack.section_name,
                        "bar_count": pack.bar_count,
                        "note_count": len(pack.notes),
                    }
                    for pack in memory.note_packs
                ],
                "motif_count": len(memory.motifs),
                "summary": memory.summary,
                "uncertainty_notes": instrument_profile.uncertainty_notes,
            }
        )
    return summaries


def _unique_durations(events: list[Any]) -> list[str]:
    durations: list[str] = []
    for event in events:
        if event.duration and event.duration not in durations:
            durations.append(event.duration)
    return durations[:4]


def _normalize_instrument(value: str) -> str:
    aliases = {"drum": "drums", "keyboard": "piano", "keys": "piano", "synth": "piano"}
    normalized = value.strip().lower()
    return aliases.get(normalized, normalized)


def _compose_tool_answer(song, source: str, *, warnings: list[str] | None = None) -> str:
    answer = (
        f"Generated a {song.header.genre} sketch at {song.header.tempo_bpm} BPM in {song.header.key} "
        f"({len(song.roster)} instruments, source={source})."
    )
    if warnings:
        answer += f" Generated with partial failures: {'; '.join(warnings)}."
    return answer


def _composition_warnings(song) -> list[str]:
    warnings: list[str] = []
    for instrument_id, part in song.parts.items():
        summary = part.notes_summary or ""
        marker = "(failed to compose:"
        if marker not in summary:
            continue
        reason = summary.split(marker, 1)[1].split(")", 1)[0].strip()
        warnings.append(f"{instrument_id} failed to compose: {reason}")
    warnings.extend(str(error) for error in getattr(song, "errors", []) if error)
    return warnings


def _default_reference_transfer_intent(
    instrument_profiles: dict[str, dict[str, ReferenceInstrumentProfile]],
) -> ReferenceTransferIntent:
    items: list[ReferenceTransferItem] = []
    for reference_id, profiles in instrument_profiles.items():
        for family, profile in sorted(profiles.items()):
            has_symbolic_notes = bool(profile.musical_memory.note_packs or profile.symbolic_seed)
            items.append(
                ReferenceTransferItem(
                    instrument_family=family,  # type: ignore[arg-type]
                    reference_id=reference_id,
                    transfer_mode="literal" if has_symbolic_notes else "similar",
                    fidelity=1.0 if has_symbolic_notes else 0.65,
                )
            )
    return ReferenceTransferIntent(items=items)


def _filter_transfer_intent_to_available_instruments(
    intent: ReferenceTransferIntent,
    instrument_profiles: dict[str, dict[str, ReferenceInstrumentProfile]],
    message: str,
) -> ReferenceTransferIntent:
    available = _available_instrument_families(instrument_profiles)
    explicit = _explicitly_requested_instrument_families(message)
    items = [
        item
        for item in intent.items
        if item.instrument_family in available or item.instrument_family in explicit
    ]
    return intent.model_copy(update={"items": items})


def _operational_clarification_notes(
    clarification: str,
    instrument_profiles: dict[str, dict[str, ReferenceInstrumentProfile]],
    message: str,
) -> list[str]:
    cleaned = clarification.strip()
    if not cleaned or _is_blocking_clarification(cleaned):
        return []
    available = _available_instrument_families(instrument_profiles)
    explicit = _explicitly_requested_instrument_families(message)
    notes: list[str] = []
    for sentence in _sentences(cleaned):
        mentioned = _mentioned_instrument_families(sentence)
        if mentioned and not mentioned.intersection(available | explicit):
            continue
        notes.append(sentence)
    return notes


def _is_blocking_clarification(text: str) -> bool:
    normalized = text.strip().lower()
    if "?" in normalized:
        return True
    blocking_prefixes = (
        "which ",
        "what ",
        "please provide",
        "provide ",
        "i need",
        "need ",
        "necesito",
        "a que ",
        "a qué ",
        "que cancion",
        "qué canción",
        "cual ",
        "cuál ",
    )
    return normalized.startswith(blocking_prefixes)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in text.replace("\n", " ").split(".") if part.strip()]


def _available_instrument_families(
    instrument_profiles: dict[str, dict[str, ReferenceInstrumentProfile]],
) -> set[str]:
    return {
        family
        for profiles in instrument_profiles.values()
        for family in profiles.keys()
    }


def _explicitly_requested_instrument_families(message: str) -> set[str]:
    return _mentioned_instrument_families(message)


def _mentioned_instrument_families(text: str) -> set[str]:
    normalized = text.lower()
    aliases = {
        "drums": ["drum", "drums", "bateria", "batería"],
        "bass": ["bass", "bajo"],
        "guitar": ["guitar", "guitarra"],
        "piano": ["piano", "keys", "keyboard", "teclado"],
    }
    return {
        family
        for family, words in aliases.items()
        if any(word in normalized for word in words)
    }


def _instrument_requests_summary(instrument_requests: dict[str, dict]) -> list[dict]:
    summaries: list[dict] = []
    for family, request in instrument_requests.items():
        intent = request.get("intent") if isinstance(request, dict) else {}
        note_pack = request.get("note_pack") if isinstance(request, dict) else None
        summaries.append(
            {
                "instrument_family": family,
                "reference_id": intent.get("reference_id", "") if isinstance(intent, dict) else "",
                "transfer_mode": intent.get("transfer_mode", "") if isinstance(intent, dict) else "",
                "section_name": intent.get("section_name") if isinstance(intent, dict) else None,
                "fidelity": intent.get("fidelity") if isinstance(intent, dict) else None,
                "note_pack_id": request.get("note_pack_id", "") if isinstance(request, dict) else "",
                "literal_application": bool(request.get("literal_application")) if isinstance(request, dict) else False,
                "literal_mode": request.get("literal_mode", "") if isinstance(request, dict) else "",
                "musical_memory_summary": request.get("musical_memory_summary", "") if isinstance(request, dict) else "",
                "note_count": len(note_pack.get("notes", [])) if isinstance(note_pack, dict) else 0,
                "bar_count": int(note_pack.get("bar_count", 0)) if isinstance(note_pack, dict) else 0,
            }
        )
    return summaries


def _literal_applications_summary(instrument_requests: dict[str, dict]) -> list[dict]:
    summaries: list[dict] = []
    for family, request in instrument_requests.items():
        if not isinstance(request, dict):
            continue
        intent = request.get("intent")
        if not isinstance(intent, dict) or intent.get("transfer_mode") != "literal":
            continue
        note_pack = request.get("note_pack")
        applied = bool(request.get("literal_application") and request.get("note_pack_id"))
        reason = ""
        if not applied:
            reason = f"literal {family} requested but no note pack is available"
        summaries.append(
            {
                "instrument_family": family,
                "note_pack_id": request.get("note_pack_id", ""),
                "note_count": len(note_pack.get("notes", [])) if isinstance(note_pack, dict) else 0,
                "bar_count": int(note_pack.get("bar_count", 0)) if isinstance(note_pack, dict) else 0,
                "applied": applied,
                "mode": request.get("literal_mode", ""),
                "reason": reason,
            }
        )
    return summaries
