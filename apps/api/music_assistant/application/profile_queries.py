"""Deterministic query tools over SongKnowledgeProfile."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re

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
            claims = [claim for claim in claims if _section_matches(section_name, claim.section_name)]
        if not claims:
            return ProfileQueryAnswer(
                answer="I do not have enough evidence for those chords yet.",
                evidence=[],
            )
        grouped_answer = _grouped_section_chord_answer(claims, section_name)
        if grouped_answer is not None:
            return ProfileQueryAnswer(
                answer=grouped_answer,
                evidence=[_evidence_line(claim) for claim in claims],
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
        songsterr_sections = _songsterr_index_sections(profile)
        if songsterr_sections:
            evidence = [f"songsterr:sections:{len(songsterr_sections)}"]
            section_evidence = [
                f"section:{section.name}:claims={len(section.evidence_ids)}"
                for section in profile.sections
            ]
            partial = ""
            if profile.sections:
                partial_names = ", ".join(section.name for section in profile.sections)
                partial = f" CifraClub/LaCuerda-style section evidence is partial: {partial_names}."
            return ProfileQueryAnswer(
                answer=f"Songsterr tab sections: {', '.join(songsterr_sections)}.{partial}",
                evidence=[*evidence, *section_evidence],
            )
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

    def instrumentation(self, profile: SongKnowledgeProfile, instrument: str | None = None) -> ProfileQueryAnswer:
        claims = [
            claim
            for claim in profile.evidence_claims
            if claim.claim_type in {"instrumentation", "groove", "timbre", "trait", "tab"}
        ]
        if instrument:
            instrument = _normalize_instrument_query(instrument)
            claims = [claim for claim in claims if instrument in (claim.value + " " + claim.snippet).lower()]
            if not claims:
                return ProfileQueryAnswer(
                    answer=f"I do not have {instrument}-specific evidence for this song yet.",
                    evidence=[],
                )
        if not claims:
            return ProfileQueryAnswer(answer="I do not have instrumentation evidence for this song yet.", evidence=[])
        return ProfileQueryAnswer(
            answer="Instrumentation and trait evidence: " + "; ".join(claim.value for claim in claims[:5]) + ".",
            evidence=[_evidence_line(claim) for claim in claims],
        )

    def groove(self, profile: SongKnowledgeProfile) -> ProfileQueryAnswer:
        """Feel/swing/density from deep-listening groove claims."""
        claims = _claims(profile, "groove")
        if not claims:
            # Web evidence sometimes describes the groove inside instrumentation
            # claims — better that than "no evidence".
            fallback = [
                claim
                for claim in _claims(profile, "instrumentation")
                if "groove" in claim.value.lower() or "rhythm" in claim.value.lower()
            ]
            if fallback:
                return ProfileQueryAnswer(
                    answer="Groove evidence: " + "; ".join(claim.value for claim in fallback[:3]) + ".",
                    evidence=[_evidence_line(claim) for claim in fallback],
                )
            return ProfileQueryAnswer(answer="I do not have groove evidence for this song yet.", evidence=[])
        best = _best(claims)
        others = [claim for claim in claims if claim is not best][:2]
        answer = f"The groove is likely {best.value}"
        if others:
            answer += "; also " + "; ".join(claim.value for claim in others)
        answer += " — from audio listening evidence (approximate)."
        return ProfileQueryAnswer(answer=answer, evidence=[_evidence_line(claim) for claim in claims])

    def timbre(self, profile: SongKnowledgeProfile, stem: str | None = None) -> ProfileQueryAnswer:
        """Sound/brightness/noisiness from deep-listening timbre claims. The
        mix-level claim leads unless a specific stem was asked for."""
        claims = _claims(profile, "timbre")
        if stem:
            stem = _normalize_instrument_query(stem)
            claims = [claim for claim in claims if stem in claim.value.lower()]
            if not claims:
                return ProfileQueryAnswer(
                    answer=f"I do not have {stem}-specific timbre evidence for this song yet.",
                    evidence=[],
                )
        if not claims:
            return ProfileQueryAnswer(answer="I do not have timbre evidence for this song yet.", evidence=[])
        ordered = sorted(claims, key=lambda c: (not c.value.startswith("mix:"), -c.confidence))
        answer = (
            "It likely sounds like this: "
            + "; ".join(claim.value for claim in ordered[:3])
            + " — spectral estimates, not ground truth."
        )
        return ProfileQueryAnswer(answer=answer, evidence=[_evidence_line(claim) for claim in ordered])

    def dynamics_and_arrangement(self, profile: SongKnowledgeProfile) -> ProfileQueryAnswer:
        """Builds/drops and stem entry/exit events from the bar-aligned curves."""
        events = [
            claim
            for claim in _claims(profile, "audio_estimate")
            if "builds through bars" in claim.value or "drops at bar" in claim.value
        ]
        changes = [
            claim
            for claim in _claims(profile, "instrumentation")
            if any(marker in claim.value for marker in ("enters", "drops out", "pushes high"))
        ]
        if not events and not changes:
            return ProfileQueryAnswer(
                answer="I do not have dynamics or arrangement evidence for this song yet.",
                evidence=[],
            )
        fragments = [claim.value for claim in changes[:3] + events[:3]]
        return ProfileQueryAnswer(
            answer="Arrangement and dynamics evidence: " + "; ".join(fragments) + " — bar-aligned estimates.",
            evidence=[_evidence_line(claim) for claim in changes + events],
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

    def evidence_summary(self, profile: SongKnowledgeProfile) -> ProfileQueryAnswer:
        claims = sorted(profile.evidence_claims, key=lambda claim: claim.confidence, reverse=True)
        if not claims:
            return ProfileQueryAnswer(answer="This research profile does not contain source-backed claims yet.")
        selected = claims[:5]
        sources = list(dict.fromkeys(claim.source_name for claim in selected if claim.source_name))
        source_text = ", ".join(sources) if sources else "the collected sources"
        findings = "; ".join(f"{claim.claim_type}: {claim.value}" for claim in selected)
        return ProfileQueryAnswer(
            answer=f"The strongest findings from {source_text} are: {findings}.",
            evidence=[_evidence_line(claim) for claim in selected],
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
    if any(token in normalized for token in ["evidence", "what did you find", "findings", "research result"]):
        return tools.evidence_summary(profile)
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
    if any(token in normalized for token in ["timbre", "bright", "dark", "warm", "tone", "sound", "noisy"]):
        return tools.timbre(profile, stem=_mentioned_instrument(normalized))
    if any(token in normalized for token in ["swing", "swung", "groove", "syncopat", "shuffle", "feel"]):
        return tools.groove(profile)
    if any(token in normalized for token in ["build", "drop", "louder", "quieter", "dynamic", "arrangement", "loudness"]):
        return tools.dynamics_and_arrangement(profile)
    if any(token in normalized for token in ["instrument", "drum", "bass", "guitar", "synth", "piano"]):
        return tools.instrumentation(profile, instrument=_mentioned_instrument(normalized))
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


def _songsterr_index_sections(profile: SongKnowledgeProfile) -> list[str]:
    index = profile.metadata.get("songsterr_tab_index") if isinstance(profile.metadata, dict) else None
    if not isinstance(index, dict) or not index.get("loaded"):
        return []
    sections = index.get("sections")
    if not isinstance(sections, list):
        return []
    return [str(section) for section in sections if str(section).strip()]


def _best(claims: list[EvidenceClaim]) -> EvidenceClaim:
    return max(claims, key=lambda claim: claim.confidence)


def _section(profile: SongKnowledgeProfile, name: str):
    return next((section for section in profile.sections if _section_matches(name, section.name)), None)


def _mentioned_section(normalized_question: str) -> str | None:
    exact = re.search(r"\b(chorus|verse|pre-chorus|bridge|intro|interlude|solo|outro)\s+(\d+)\b", normalized_question)
    if exact:
        return f"{exact.group(1)} {exact.group(2)}"
    for name in ["intro", "verse", "pre-chorus", "chorus", "bridge", "solo", "outro"]:
        if name in normalized_question:
            return name
    return None


def _mentioned_instrument(normalized_question: str) -> str | None:
    for instrument in ["drums", "drum", "bass", "guitar", "piano", "keyboard", "keys", "synth", "vocal", "voice"]:
        if instrument in normalized_question:
            return _normalize_instrument_query(instrument)
    return None


def _normalize_instrument_query(value: str) -> str:
    aliases = {
        "drum": "drums",
        "keyboard": "keys",
        "voice": "vocal",
        "vocals": "vocal",
    }
    return aliases.get(value.strip().lower(), value.strip().lower())


def _section_aliases(name: str) -> set[str]:
    normalized = _normalize_section_label(name)
    aliases = {
        "chorus": {"chorus", "refrain", "refrao", "coro", "estribillo"},
        "verse": {"verse", "verso", "estrofa", "parte", "primeira parte", "segunda parte", "terceira parte"},
        "pre-chorus": {"pre-chorus", "pre chorus", "pre refrao", "pre-estribillo"},
        "bridge": {"bridge", "ponte", "puente"},
        "intro": {"intro", "introducao", "introduccion", "dedilhado intro"},
        "interlude": {"interlude", "interludio", "dedilhado interludio"},
        "outro": {"outro", "final"},
        "solo": {"solo"},
    }
    return aliases.get(normalized, {normalized})


def _section_matches(requested: str, candidate: str | None) -> bool:
    if not candidate:
        return False
    requested_label = _normalize_section_label(requested)
    candidate_label = _normalize_section_label(candidate)
    if _is_numbered_section(requested_label):
        return requested_label == candidate_label
    requested_groups = _section_aliases(requested_label)
    return candidate_label in requested_groups or _section_group(candidate_label) in requested_groups


def _normalize_section_label(value: str) -> str:
    normalized = (
        value.strip().lower()
        .replace("ã", "a")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    return re.sub(r"\s+", " ", normalized.replace("-", " ")).strip()


def _is_numbered_section(value: str) -> bool:
    return bool(re.search(r"\b\d+\b", value))


def _section_group(value: str) -> str:
    normalized = _normalize_section_label(value)
    normalized = re.sub(r"\s+\d+$", "", normalized)
    for group, aliases in {
        "chorus": {"chorus", "refrain", "refrao", "coro", "estribillo"},
        "verse": {"verse", "verso", "estrofa", "parte", "primeira parte", "segunda parte", "terceira parte"},
        "pre-chorus": {"pre chorus", "pre refrao", "pre estribillo"},
        "intro": {"intro", "dedilhado intro"},
        "interlude": {"interlude", "interludio", "dedilhado interludio"},
        "bridge": {"bridge", "ponte", "puente"},
        "outro": {"outro", "final"},
        "solo": {"solo"},
    }.items():
        if normalized in aliases:
            return group
    return normalized


def _grouped_section_chord_answer(claims: list[EvidenceClaim], section_name: str | None) -> str | None:
    if not section_name or _is_numbered_section(section_name):
        return None
    by_section: dict[str, list[EvidenceClaim]] = defaultdict(list)
    for claim in claims:
        by_section[claim.section_name or "progression"].append(claim)
    if len(by_section) <= 1:
        return None

    best_by_section = {
        section: _best(section_claims)
        for section, section_claims in by_section.items()
    }
    summaries = {
        section: _summarize_progression_claim(claim)
        for section, claim in best_by_section.items()
    }
    ordered_sections = sorted(summaries, key=_section_sort_key)
    first_section = ordered_sections[0]
    first_summary = summaries[first_section]
    if all(summary.core == first_summary.core and summary.bars == first_summary.bars for summary in summaries.values()):
        sections = _join_labels(ordered_sections)
        return (
            f"{sections} use the same main progression: "
            f"{_progression_answer_fragment(first_summary)}, based on web evidence."
        )

    extension = _extension_relationship(summaries, ordered_sections)
    if extension is not None:
        base, extended = extension
        extended_tail = _extension_tail(summaries[base].bars, summaries[extended].bars)
        return (
            f"{extended} starts like {base}, then extends with {' | '.join(extended_tail[:4])}, "
            "based on web evidence."
        )

    pieces = [
        f"{section.capitalize()}: {_progression_answer_fragment(summaries[section])}"
        for section in ordered_sections
    ]
    return " ".join(pieces) + " Based on web evidence."


def _progression_answer_fragment(summary: ProgressionSummary) -> str:
    if summary.has_repeat:
        return summary.text
    if len(summary.bars) > 1:
        return " | ".join(summary.bars[:8])
    return summary.text


def _join_labels(labels: list[str]) -> str:
    formatted = [label for label in labels]
    if len(formatted) == 2:
        return f"{formatted[0]} and {formatted[1]}"
    return ", ".join(formatted[:-1]) + f", and {formatted[-1]}"


def _section_sort_key(section: str) -> tuple[str, int, str]:
    match = re.search(r"^(.*?)(?:\s+(\d+))?$", section)
    if not match:
        return section, 0, section
    return match.group(1), int(match.group(2) or 0), section


def _extension_relationship(
    summaries: dict[str, ProgressionSummary],
    ordered_sections: list[str],
) -> tuple[str, str] | None:
    for base in ordered_sections:
        for extended in ordered_sections:
            if base == extended:
                continue
            base_bars = summaries[base].bars
            extended_bars = summaries[extended].bars
            if len(extended_bars) > len(base_bars) and extended_bars[: len(base_bars)] == base_bars:
                return base, extended
    return None


def _extension_tail(base_bars: tuple[str, ...], extended_bars: tuple[str, ...]) -> tuple[str, ...]:
    return extended_bars[len(base_bars):]


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
