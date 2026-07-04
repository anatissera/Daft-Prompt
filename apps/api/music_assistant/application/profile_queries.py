"""Deterministic query tools over SongKnowledgeProfile."""

from __future__ import annotations

from pydantic import BaseModel, Field

from music_assistant.domain.audio_profile import EvidenceClaim, SongKnowledgeProfile


class ProfileQueryAnswer(BaseModel):
    answer: str
    evidence: list[str] = Field(default_factory=list)


class ProfileQueryTools:
    def key_bpm(self, profile: SongKnowledgeProfile) -> ProfileQueryAnswer:
        tempo_claims = _claims(profile, "tempo")
        key_claims = _claims(profile, "key")
        pieces: list[str] = []
        evidence: list[str] = []
        if tempo_claims:
            best_tempo = _best(tempo_claims)
            pieces.append(f"tempo is likely {best_tempo.value}")
            evidence.append(_evidence_line(best_tempo))
        if key_claims:
            best_key = _best(key_claims)
            pieces.append(f"key is likely {best_key.value}")
            evidence.append(_evidence_line(best_key))
        if not pieces:
            return self.missing_data(profile)
        caveat = " from web evidence"
        if any(conflict.claim_type == "key" for conflict in profile.conflicts):
            caveat += ", with a preserved key conflict"
        return ProfileQueryAnswer(answer="The " + " and ".join(pieces) + caveat + ".", evidence=evidence)

    def chords(self, profile: SongKnowledgeProfile, section_name: str | None = None) -> ProfileQueryAnswer:
        claims = _claims(profile, "chord_progression")
        if section_name:
            claims = [claim for claim in claims if (claim.section_name or "").lower() == section_name.lower()]
        if not claims:
            return ProfileQueryAnswer(
                answer="I do not have enough evidence for those chords yet.",
                evidence=[],
            )
        best = _best(claims)
        section = f" in the {best.section_name}" if best.section_name else ""
        return ProfileQueryAnswer(
            answer=f"The chords are probably {best.value}{section}, based on web evidence.",
            evidence=[_evidence_line(claim) for claim in claims],
        )

    def sections(self, profile: SongKnowledgeProfile) -> ProfileQueryAnswer:
        if not profile.sections:
            return ProfileQueryAnswer(answer="I do not have section evidence for this song yet.", evidence=[])
        names = ", ".join(section.name for section in profile.sections)
        evidence = [f"section:{section.name}:claims={len(section.evidence_ids)}" for section in profile.sections]
        return ProfileQueryAnswer(answer=f"Known sections from evidence: {names}.", evidence=evidence)

    def lyrics_by_section(self, profile: SongKnowledgeProfile, section_name: str) -> ProfileQueryAnswer:
        section = _section(profile, section_name)
        if section is None or not section.lyric_claims:
            return ProfileQueryAnswer(
                answer=f"I do not have section-scoped lyric evidence for {section_name}.",
                evidence=[],
            )
        return ProfileQueryAnswer(
            answer=f"I have section-scoped lyric evidence for {section.name}, but not a full lyric dump.",
            evidence=[_evidence_line(claim) for claim in section.lyric_claims],
        )

    def metadata_credits(self, profile: SongKnowledgeProfile) -> ProfileQueryAnswer:
        identity = profile.identity
        rows = [identity.title]
        if identity.artist:
            rows.append(f"by {identity.artist}")
        if identity.album:
            rows.append(f"from {identity.album}")
        if identity.year:
            rows.append(str(identity.year))
        credit_claims = _claims(profile, "credit")
        if credit_claims:
            rows.append("credits include " + ", ".join(claim.value for claim in credit_claims[:4]))
        return ProfileQueryAnswer(
            answer=" ".join(rows) + ".",
            evidence=[_evidence_line(claim) for claim in credit_claims],
        )

    def instrumentation(self, profile: SongKnowledgeProfile) -> ProfileQueryAnswer:
        claims = [
            claim
            for claim in profile.evidence_claims
            if claim.claim_type in {"instrumentation", "groove", "timbre", "trait"}
        ]
        if not claims:
            return ProfileQueryAnswer(answer="I do not have instrumentation evidence for this song yet.", evidence=[])
        return ProfileQueryAnswer(
            answer="Instrumentation and trait evidence: " + "; ".join(claim.value for claim in claims[:5]) + ".",
            evidence=[_evidence_line(claim) for claim in claims],
        )

    def conflicts(self, profile: SongKnowledgeProfile) -> ProfileQueryAnswer:
        if not profile.conflicts:
            return ProfileQueryAnswer(answer="I do not have preserved source conflicts for this profile.", evidence=[])
        return ProfileQueryAnswer(
            answer=" ".join(conflict.description for conflict in profile.conflicts),
            evidence=[
                f"conflict:{conflict.claim_type}:{','.join(claim.claim_id for claim in conflict.claims)}"
                for conflict in profile.conflicts
            ],
        )

    def missing_data(self, profile: SongKnowledgeProfile) -> ProfileQueryAnswer:
        if not profile.missing_data:
            return ProfileQueryAnswer(answer="I do not see explicit missing-data notes for this profile.", evidence=[])
        return ProfileQueryAnswer(
            answer="Missing data: " + "; ".join(f"{item.field}: {item.reason}" for item in profile.missing_data) + ".",
            evidence=[f"missing:{item.field}:{item.needed_evidence}" for item in profile.missing_data],
        )

    def unsupported(self, profile: SongKnowledgeProfile, question: str) -> ProfileQueryAnswer:
        return ProfileQueryAnswer(
            answer=(
                "There is not enough evidence to answer that yet. "
                f"The profile cannot support this question without guessing: {question}"
            ),
            evidence=[],
        )


def answer_from_profile(question: str, profile: SongKnowledgeProfile) -> ProfileQueryAnswer:
    tools = ProfileQueryTools()
    normalized = question.lower()
    section = _mentioned_section(normalized)
    if any(token in normalized for token in ["chord", "progression", "harmony"]):
        return tools.chords(profile, section_name=section)
    if any(token in normalized for token in ["lyric", "lyrics"]):
        return tools.lyrics_by_section(profile, section or "chorus")
    if any(token in normalized for token in ["credit", "writer", "producer", "album", "artist", "who sings"]):
        return tools.metadata_credits(profile)
    if any(token in normalized for token in ["instrument", "drum", "bass", "guitar", "synth", "groove"]):
        return tools.instrumentation(profile)
    if any(token in normalized for token in ["conflict", "disagree", "source"]):
        return tools.conflicts(profile)
    if any(token in normalized for token in ["missing", "unknown", "not have"]):
        return tools.missing_data(profile)
    if any(token in normalized for token in ["section", "form", "verse", "chorus", "bridge"]):
        return tools.sections(profile)
    if any(token in normalized for token in ["tempo", "bpm", "key", "scale"]):
        return tools.key_bpm(profile)
    return tools.unsupported(profile, question)


def _claims(profile: SongKnowledgeProfile, claim_type: str) -> list[EvidenceClaim]:
    return [claim for claim in profile.evidence_claims if claim.claim_type == claim_type]


def _best(claims: list[EvidenceClaim]) -> EvidenceClaim:
    return max(claims, key=lambda claim: claim.confidence)


def _section(profile: SongKnowledgeProfile, name: str):
    return next((section for section in profile.sections if section.name.lower() == name.lower()), None)


def _mentioned_section(normalized_question: str) -> str | None:
    for name in ["intro", "verse", "pre-chorus", "chorus", "bridge", "solo", "outro"]:
        if name in normalized_question:
            return name
    return None


def _evidence_line(claim: EvidenceClaim) -> str:
    section = f":{claim.section_name}" if claim.section_name else ""
    return f"{claim.claim_type}{section}:{claim.value}:{claim.source_name}:{claim.confidence:.2f}"
