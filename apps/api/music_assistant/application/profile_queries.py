"""Deterministic query tools over SongKnowledgeProfile."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from music_assistant.domain.audio_profile import EvidenceClaim, SongKnowledgeProfile


class ProfileQueryAnswer(BaseModel):
    answer: str
    evidence: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ProgressionSummary:
    text: str
    bars: tuple[str, ...]
    core: tuple[str, ...]
    repeat_count: int
    has_repeat: bool
    source_name: str


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
            section_names = _section_aliases(section_name)
            claims = [claim for claim in claims if (claim.section_name or "").lower() in section_names]
        if not claims:
            return ProfileQueryAnswer(
                answer="I do not have enough evidence for those chords yet.",
                evidence=[],
            )
        best = _best(claims)
        summary = _summarize_progression_claim(best)
        section = best.section_name or "progression"
        extended_note = _extended_repeat_note(summary, claims)
        if summary.has_repeat:
            answer = f"The {section} is probably {summary.text}{extended_note}, based on web evidence."
        elif len(summary.bars) > 1:
            answer = f"The {section} {summary.text}{extended_note}, based on web evidence."
        else:
            answer = f"The chords are probably {summary.text} in the {section}, based on web evidence."
        return ProfileQueryAnswer(
            answer=answer,
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
    wants_chords = any(token in normalized for token in ["chord", "progression", "harmony"])
    wants_key_bpm = any(token in normalized for token in ["tempo", "bpm", "key", "scale"])
    if wants_chords and wants_key_bpm:
        key_bpm = tools.key_bpm(profile)
        chords = tools.chords(profile, section_name=section)
        return ProfileQueryAnswer(
            answer=f"{key_bpm.answer} {chords.answer}",
            evidence=[*key_bpm.evidence, *chords.evidence],
        )
    if wants_chords:
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
    if wants_key_bpm:
        return tools.key_bpm(profile)
    return tools.unsupported(profile, question)


def _claims(profile: SongKnowledgeProfile, claim_type: str) -> list[EvidenceClaim]:
    return [claim for claim in profile.evidence_claims if claim.claim_type == claim_type]


def _best(claims: list[EvidenceClaim]) -> EvidenceClaim:
    return max(claims, key=lambda claim: claim.confidence)


def _section(profile: SongKnowledgeProfile, name: str):
    names = _section_aliases(name)
    return next((section for section in profile.sections if section.name.lower() in names), None)


def _mentioned_section(normalized_question: str) -> str | None:
    for name in ["intro", "verse", "pre-chorus", "chorus", "bridge", "solo", "outro"]:
        if name in normalized_question:
            return name
    return None


def _section_aliases(name: str) -> set[str]:
    normalized = name.lower()
    aliases = {
        "chorus": {"chorus", "refrain", "refrão", "refrao", "coro", "estribillo"},
        "verse": {"verse", "verso", "estrofa", "parte", "primeira parte", "segunda parte"},
        "pre-chorus": {"pre-chorus", "pre chorus", "pré-refrão", "pre refrao", "pre-estribillo"},
        "bridge": {"bridge", "ponte", "puente"},
        "intro": {"intro", "introdução", "introduccion"},
        "outro": {"outro", "final"},
        "solo": {"solo"},
    }
    return aliases.get(normalized, {normalized})


def _evidence_line(claim: EvidenceClaim) -> str:
    section = f":{claim.section_name}" if claim.section_name else ""
    value = _truncate(claim.value, 96)
    return f"{claim.claim_type}{section}:{value}:{claim.source_name}:{claim.confidence:.2f}"


def _summarize_progression_claim(claim: EvidenceClaim) -> ProgressionSummary:
    bars = tuple(_bar_segments(claim.value))
    repeat = _find_repeating_cell(bars)
    if repeat is None:
        shown = bars[:8]
        if len(bars) <= 1:
            text = bars[0] if bars else claim.value.strip()
        else:
            suffix = ", and continues beyond that" if len(bars) > len(shown) else ""
            text = f"starts {' | '.join(shown)}{suffix}"
        return ProgressionSummary(
            text=text,
            bars=bars,
            core=shown,
            repeat_count=1,
            has_repeat=False,
            source_name=claim.source_name,
        )

    cell, repeat_count, leftover = repeat
    cell_text = " | ".join(cell)
    if len(cell) == 1:
        text = f"a 1-bar vamp: {cell_text}, repeated {repeat_count} times"
    else:
        text = f"a repeated {len(cell)}-bar pattern: {cell_text}, repeated {repeat_count} times"
    if leftover:
        leftover_text = " | ".join(leftover[:4])
        if len(leftover) == 1:
            text += f", with an {leftover_text} turnaround"
        else:
            text += f", followed by {leftover_text}"
        if len(leftover) > 4:
            text += ", and more continuation material"
    return ProgressionSummary(
        text=text,
        bars=bars,
        core=cell,
        repeat_count=repeat_count,
        has_repeat=True,
        source_name=claim.source_name,
    )


def _bar_segments(value: str) -> list[str]:
    bars = [
        " ".join(segment.strip().split())
        for segment in value.split("|")
        if segment.strip()
    ]
    return bars or [" ".join(value.strip().split())]


def _find_repeating_cell(bars: tuple[str, ...]) -> tuple[tuple[str, ...], int, tuple[str, ...]] | None:
    for cell_size in [1, 2, 4, 8]:
        if len(bars) < cell_size * 2:
            continue
        cell = bars[:cell_size]
        repeat_count = 1
        cursor = cell_size
        while tuple(bars[cursor: cursor + cell_size]) == cell:
            repeat_count += 1
            cursor += cell_size
        covered = repeat_count * cell_size
        if repeat_count >= 2 and covered >= min(len(bars), cell_size * 2):
            return cell, repeat_count, bars[covered:]
    return None


def _extended_repeat_note(summary: ProgressionSummary, claims: list[EvidenceClaim]) -> str:
    if not summary.has_repeat:
        return ""
    for claim in claims:
        candidate = _summarize_progression_claim(claim)
        if (
            candidate.source_name == summary.source_name
            and candidate.core == summary.core
            and len(candidate.bars) > len(summary.bars)
        ):
            section = claim.section_name or "section"
            return f". {claim.source_name} also shows an extended {section} repeat using the same pattern"
    return ""


def _truncate(value: str, max_length: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"
