"""Build structured composition briefs from chat requests and profiles."""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel

from music_assistant.domain.audio_profile import (
    CompositionBrief,
    EvidenceClaim,
    ReferenceInstrumentProfile,
    ReferenceTransferIntent,
    SongKnowledgeProfile,
)


class BriefBuildResult(BaseModel):
    brief: CompositionBrief | None = None
    clarification: str | None = None


class BuildCompositionBrief:
    def execute(
        self,
        message: str,
        profiles: list[SongKnowledgeProfile],
        *,
        transfer_intent: ReferenceTransferIntent | None = None,
        instrument_profiles: dict[str, dict[str, ReferenceInstrumentProfile]] | None = None,
    ) -> BriefBuildResult:
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

        if transfer_intent is not None:
            _apply_transfer_intent(brief, profiles, transfer_intent, instrument_profiles or {}, normalized)
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


def _apply_transfer_intent(
    brief: CompositionBrief,
    profiles: list[SongKnowledgeProfile],
    intent: ReferenceTransferIntent,
    instrument_profiles: dict[str, dict[str, ReferenceInstrumentProfile]],
    normalized_message: str = "",
) -> None:
    profile_ids_by_reference = _profile_ids_by_reference(profiles, instrument_profiles)
    literal_mode = "literal_timeline" if _requests_full_song_timeline(normalized_message) else "literal_loop"
    for item in intent.items:
        reference_profile = (instrument_profiles.get(item.reference_id) or {}).get(item.instrument_family)
        profile_id = (
            reference_profile.source_profile_id
            if reference_profile is not None and reference_profile.source_profile_id
            else profile_ids_by_reference.get(item.reference_id)
            or (profiles[0].profile_id if profiles else item.reference_id)
        )
        dimension = f"instrument:{item.instrument_family}"
        brief.transfer_policy.setdefault(profile_id, [])
        if dimension not in brief.transfer_policy[profile_id]:
            brief.transfer_policy[profile_id].append(dimension)
        request: dict = {
            "intent": item.model_dump(mode="json"),
        }
        if reference_profile is None:
            brief.uncertainty_notes.append(
                f"Requested {item.instrument_family} from {item.reference_id}, but no instrument profile is available."
            )
        else:
            request["timbre"] = reference_profile.timbre.model_dump(mode="json")
            request["pattern"] = reference_profile.pattern.model_dump(mode="json")
            request["musical_memory_summary"] = reference_profile.musical_memory.summary
            request["literal_application"] = False
            request["literal_mode"] = literal_mode
            note_pack = _selected_note_pack(reference_profile, item.section_name)
            if item.transfer_mode == "literal" and note_pack is not None:
                request["literal_application"] = True
                request["note_pack_id"] = note_pack.pack_id
                request["note_pack"] = note_pack.model_dump(mode="json")
            elif item.transfer_mode == "literal":
                brief.uncertainty_notes.append(
                    f"Requested literal {item.instrument_family}, but no note pack is available."
                )
        brief.instrument_requests[item.instrument_family] = request


def _requests_full_song_timeline(normalized: str) -> bool:
    full_song_terms = [
        "toda la cancion",
        "toda la canción",
        "cancion entera",
        "canción entera",
        "full song",
        "entire song",
        "whole song",
    ]
    return any(term in normalized for term in full_song_terms)


def _selected_note_pack(profile: ReferenceInstrumentProfile, section_name: str | None = None):
    if section_name:
        normalized = section_name.strip().lower()
        for pack in profile.musical_memory.note_packs:
            if pack.section_name.strip().lower() == normalized:
                return pack
    if profile.musical_memory.note_packs:
        return profile.musical_memory.note_packs[0]
    return None


def _profile_ids_by_reference(
    profiles: list[SongKnowledgeProfile],
    instrument_profiles: dict[str, dict[str, ReferenceInstrumentProfile]],
) -> dict[str, str]:
    by_reference: dict[str, str] = {}
    for reference_id, by_instrument in instrument_profiles.items():
        for profile in by_instrument.values():
            if profile.source_profile_id:
                by_reference[reference_id] = profile.source_profile_id
                break
    if len(profiles) == 1 and not by_reference:
        by_reference[""] = profiles[0].profile_id
    return by_reference


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
