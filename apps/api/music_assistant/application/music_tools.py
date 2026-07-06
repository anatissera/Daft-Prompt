"""Explicit musical tools used by the conversational chat agent."""

from __future__ import annotations

from typing import Any

from music_assistant.application.answer_music_question import AnswerMusicQuestion
from music_assistant.application.composition_brief import BuildCompositionBrief
from music_assistant.application.compose_song import ComposeSong
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
    TabExcerptToolInput,
    TabExcerptToolOutput,
    ToolOutput,
    TrackIndexItem,
    InstrumentSummaryToolInput,
)
from music_assistant.application.profile_queries import ProfileQueryTools
from music_assistant.domain.audio_profile import ExplanationAnswer, ReferenceProfile
from music_assistant.domain.errors import OffTopicRequest
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
    ) -> None:
        self.reference_store = reference_store
        self.answer_music_question = answer_music_question
        self.song_researcher = song_researcher
        self.compose_song = compose_song
        self.songsterr_tab_store = songsterr_tab_store
        self.profile_queries = ProfileQueryTools()

    def research_song(self, payload: ResearchSongToolInput) -> ResearchSongToolOutput:
        if self.song_researcher is None:
            return ResearchSongToolOutput(
                answer="Song research is not configured.",
                error="song_researcher_missing",
                intent="clarify",
            )
        profile = self.song_researcher.research(payload.query)
        self.reference_store.save(profile)
        evidence_count = len(profile.knowledge.evidence_claims) if profile.knowledge else 0
        return ResearchSongToolOutput(
            reference_id=profile.reference_id,
            answer=profile.summary or "Research ready from source-backed evidence.",
            summary=profile.summary or "",
            evidence_count=evidence_count,
            evidence=_profile_evidence_summary(profile),
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
                    return CompositionToolOutput(
                        reference_id=profiles[0].reference_id,
                        answer=_compose_tool_answer(song, source),
                        song=song,
                        source=source,
                        intent="compose_from_reference",
                    )
            song, source = self.compose_song.compose(payload.composition_request)
        except OffTopicRequest as refusal:
            return CompositionToolOutput(answer=refusal.message, error="off_topic", intent="compose")
        return CompositionToolOutput(answer=_compose_tool_answer(song, source), song=song, source=source, intent="compose")

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


def _compose_tool_answer(song, source: str) -> str:
    return (
        f"Generated a {song.header.genre} sketch at {song.header.tempo_bpm} BPM in {song.header.key} "
        f"({len(song.roster)} instruments, source={source})."
    )
