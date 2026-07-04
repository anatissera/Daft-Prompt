"""Build structured composition briefs from chat requests and profiles."""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel

from music_assistant.domain.audio_profile import CompositionBrief, EvidenceClaim, SongKnowledgeProfile


class BriefBuildResult(BaseModel):
    brief: CompositionBrief | None = None
    clarification: str | None = None


class BuildCompositionBrief:
    def execute(self, message: str, profiles: list[SongKnowledgeProfile]) -> BriefBuildResult:
        cleaned = message.strip()
        normalized = cleaned.lower()
        if _ambiguous_multi_reference(normalized, profiles):
            return BriefBuildResult(
                clarification=(
                    "Which traits should I transfer from each reference: drums, harmony, form, energy, or timbre?"
                )
            )
        tempo_conflict = _requested_tempo_conflict(normalized, profiles)
        if tempo_conflict:
            return BriefBuildResult(clarification=tempo_conflict)

        brief = CompositionBrief(
            brief_id=_brief_id(cleaned, profiles),
            user_request=cleaned,
            references_used=[profile.profile_id for profile in profiles],
            global_constraints=_global_constraints(normalized),
        )
        if not profiles:
            return BriefBuildResult(brief=brief)

        requested = _requested_dimensions(normalized)
        if not requested:
            requested = ["rhythmic_guidance", "form_guidance", "energy"]

        for profile in profiles:
            dimensions = _dimensions_for_profile(profile, normalized, requested)
            if not dimensions:
                continue
            brief.transfer_policy[profile.profile_id] = dimensions
            if "rhythmic_guidance" in dimensions:
                grooves = _claim_values(profile, {"groove", "instrumentation"}, words={"drum", "groove", "kick", "hat"})
                if _has_low_confidence_requested_trait(profile, {"groove", "instrumentation"}):
                    brief.uncertainty_notes.append(f"Requested drum/groove traits from {profile.identity.title} have low confidence.")
                if grooves:
                    brief.rhythmic_guidance[profile.profile_id] = grooves
                else:
                    brief.uncertainty_notes.append(f"Requested drum/groove traits from {profile.identity.title}, but no drum evidence is available.")
            if "harmonic_guidance" in dimensions:
                harmony = _claim_values(profile, {"chord_progression", "key"})
                if harmony:
                    brief.harmonic_guidance[profile.profile_id] = harmony
                else:
                    brief.uncertainty_notes.append(f"Requested harmony from {profile.identity.title}, but no harmony evidence is available.")
            if "form_guidance" in dimensions:
                brief.form_guidance[profile.profile_id] = [section.name for section in profile.sections]
            if "timbre_traits" in dimensions:
                brief.timbre_traits[profile.profile_id] = _claim_values(profile, {"timbre", "trait", "instrumentation"})

        return BriefBuildResult(brief=brief)


def _brief_id(message: str, profiles: list[SongKnowledgeProfile]) -> str:
    raw = message + "|" + "|".join(profile.profile_id for profile in profiles)
    return "brief_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _global_constraints(normalized: str) -> dict[str, str]:
    constraints: dict[str, str] = {}
    for genre in ["cumbia", "blues", "disco", "funk", "rock", "pop", "trap", "reggaeton"]:
        if genre in normalized:
            constraints["genre"] = genre
            break
    for mood in ["dark", "darker", "happy", "sad", "chill", "aggressive"]:
        if mood in normalized:
            constraints["mood"] = "dark" if mood == "darker" else mood
            break
    tempo = re.search(r"(\d{2,3})\s*bpm", normalized)
    if tempo:
        constraints["tempo_bpm"] = tempo.group(1)
    return constraints


def _requested_dimensions(normalized: str) -> list[str]:
    dimensions: list[str] = []
    if any(word in normalized for word in ["drum", "groove", "rhythm", "beat"]):
        dimensions.append("rhythmic_guidance")
    if "tempo" in normalized or "bpm" in normalized:
        dimensions.append("tempo")
    if any(word in normalized for word in ["harmony", "chord", "progression", "key"]):
        dimensions.append("harmonic_guidance")
    if any(word in normalized for word in ["form", "section", "structure", "energy"]):
        dimensions.append("form_guidance")
    if any(word in normalized for word in ["synth", "texture", "timbre", "sound"]):
        dimensions.append("timbre_traits")
    return dimensions


def _dimensions_for_profile(
    profile: SongKnowledgeProfile,
    normalized: str,
    requested: list[str],
) -> list[str]:
    title = profile.identity.title.lower()
    if len(requested) == 1:
        return requested
    if title and title in normalized:
        before_title = normalized.split(title, 1)[0]
        segment = re.split(r"\band\b|,|;", before_title)[-1]
        local = _requested_dimensions(segment[-80:])
        return local or requested
    return requested if len(requested) == 1 or len(profile.evidence_claims) > 0 else []


def _ambiguous_multi_reference(normalized: str, profiles: list[SongKnowledgeProfile]) -> bool:
    if len(profiles) < 2:
        return False
    if _requested_dimensions(normalized):
        return False
    return any(profile.conflicts for profile in profiles) or "like these" in normalized or "like both" in normalized


def _requested_tempo_conflict(normalized: str, profiles: list[SongKnowledgeProfile]) -> str | None:
    if len(profiles) < 2 or ("tempo" not in normalized and "bpm" not in normalized):
        return None
    tempos: list[tuple[str, float]] = []
    for profile in profiles:
        for claim in profile.evidence_claims:
            if claim.claim_type != "tempo":
                continue
            match = re.search(r"(\d+(?:\.\d+)?)", claim.value)
            if match:
                tempos.append((profile.identity.title, float(match.group(1))))
            break
    if len(tempos) >= 2 and max(value for _, value in tempos) - min(value for _, value in tempos) > 8:
        labels = ", ".join(f"{title}={tempo:g} BPM" for title, tempo in tempos)
        return f"The requested tempo conflicts across references ({labels}). Which tempo should I use?"
    return None


def _has_low_confidence_requested_trait(profile: SongKnowledgeProfile, claim_types: set[str]) -> bool:
    claims = [claim for claim in profile.evidence_claims if claim.claim_type in claim_types]
    return bool(claims) and max(claim.confidence for claim in claims) < 0.5


def _claim_values(
    profile: SongKnowledgeProfile,
    claim_types: set[str],
    *,
    words: set[str] | None = None,
) -> list[str]:
    values: list[str] = []
    for claim in profile.evidence_claims:
        if claim.claim_type not in claim_types:
            continue
        if claim.confidence < 0.5:
            continue
        if words and not any(word in claim.value.lower() for word in words):
            continue
        values.append(claim.value)
    return values
