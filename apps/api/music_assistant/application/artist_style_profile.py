"""Build compact artist/band style profiles from source-backed song evidence."""

from __future__ import annotations

import hashlib
import re
from collections import Counter

from pydantic import BaseModel, Field

from music_assistant.domain.audio_profile import (
    ArtistStyleProfile,
    EvidenceClaim,
    PlayablePart,
    ReferenceProfile,
    RepresentativeSong,
    SongKnowledgeProfile,
    ToneProfile,
)
from music_assistant.ports.artist_catalog import ArtistCatalog, ArtistSongCandidate
from music_assistant.ports.song_researcher import SongResearcher


class ArtistStyleProfileRequest(BaseModel):
    artist_name: str = Field(min_length=1)
    mentioned_songs: list[str] = Field(default_factory=list)
    max_songs: int = Field(default=4, ge=1, le=8)


class ArtistStyleProfileResult(BaseModel):
    profile: ArtistStyleProfile
    references: list[ReferenceProfile] = Field(default_factory=list)


class BuildArtistStyleProfile:
    def __init__(
        self,
        *,
        song_researcher: SongResearcher,
        artist_catalog: ArtistCatalog | None = None,
    ) -> None:
        self.song_researcher = song_researcher
        self.artist_catalog = artist_catalog

    def execute(self, request: ArtistStyleProfileRequest | str) -> ArtistStyleProfileResult:
        parsed = request if isinstance(request, ArtistStyleProfileRequest) else ArtistStyleProfileRequest(artist_name=request)
        artist_name = parsed.artist_name.strip()
        candidates = _candidate_songs(artist_name, parsed.mentioned_songs, parsed.max_songs, self.artist_catalog)
        references = [_research_candidate(self.song_researcher, candidate) for candidate in candidates]
        knowledge_profiles = [reference.knowledge for reference in references if reference.knowledge is not None]
        profile = _style_profile_from_knowledge(artist_name, candidates, knowledge_profiles)
        return ArtistStyleProfileResult(profile=profile, references=references)


def _candidate_songs(
    artist_name: str,
    mentioned_songs: list[str],
    limit: int,
    catalog: ArtistCatalog | None,
) -> list[ArtistSongCandidate]:
    candidates: list[ArtistSongCandidate] = [
        ArtistSongCandidate(
            title=title.strip(),
            artist=artist_name,
            reason="mentioned by user",
            tab_likely=True,
            confidence=0.78,
        )
        for title in mentioned_songs
        if title.strip()
    ]
    if catalog is not None:
        candidates.extend(catalog.representative_songs(artist_name, limit=limit * 2))
    unique: list[ArtistSongCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = f"{candidate.artist}:{candidate.title}".casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    unique.sort(key=lambda item: (not item.tab_likely, item.popularity_rank or 999, -item.confidence))
    return unique[:limit]


def _research_candidate(song_researcher: SongResearcher, candidate: ArtistSongCandidate) -> ReferenceProfile:
    return song_researcher.research(f"{candidate.title} by {candidate.artist}")


def _style_profile_from_knowledge(
    artist_name: str,
    candidates: list[ArtistSongCandidate],
    profiles: list[SongKnowledgeProfile],
) -> ArtistStyleProfile:
    candidate_by_title = {candidate.title.casefold(): candidate for candidate in candidates}
    representative_songs = [
        RepresentativeSong(
            title=profile.identity.title,
            artist=profile.identity.artist or artist_name,
            profile_id=profile.profile_id,
            reason=_representative_reason(profile, candidate_by_title),
            source_claim_ids=[claim.claim_id for claim in profile.evidence_claims[:6]],
            tab_available=_has_tab_evidence(profile),
            confidence=_profile_confidence(profile),
        )
        for profile in profiles
    ]
    source_claims = _source_claims(profiles)
    genre_tags = _top_strings(_genres_from_profiles(profiles), limit=6)
    progressions = _top_strings(_claim_values(profiles, {"chord_progression"}), limit=8)
    keys = _top_strings(_claim_values(profiles, {"key"}), limit=8)
    meters = _top_strings(_claim_values(profiles, {"meter"}), limit=4)
    instruments = _top_strings(_instrument_names(profiles), limit=10)
    tone_profiles = _tone_profiles(profiles)
    confidence = _artist_confidence(representative_songs, source_claims)
    return ArtistStyleProfile(
        profile_id=_artist_profile_id(artist_name),
        artist_name=artist_name,
        aliases=_artist_aliases(profiles),
        representative_songs=representative_songs,
        source_profile_ids=[profile.profile_id for profile in profiles],
        genre_tags=genre_tags,
        tempo_range_bpm=_tempo_range(profiles),
        common_meters=meters,
        common_keys=keys,
        common_progressions=progressions,
        typical_instruments=instruments,
        drum_traits=_role_traits(profiles, "drum"),
        bass_traits=_role_traits(profiles, "bass"),
        guitar_traits=_role_traits(profiles, "guitar"),
        keys_traits=_role_traits(profiles, "piano") + _role_traits(profiles, "keys"),
        synth_traits=_role_traits(profiles, "synth"),
        melody_hook_traits=_claim_values(profiles, {"trait"}, words={"melody", "hook", "vocal", "lead"})[:8],
        production_tone_traits=_production_traits(profiles),
        section_form_traits=_section_traits(profiles),
        tone_profiles=tone_profiles,
        source_claims=source_claims,
        confidence=confidence,
        confidence_summary=_confidence_summary(profiles, confidence),
        uncertainty_notes=_uncertainty_notes(candidates, profiles),
    )


def _representative_reason(
    profile: SongKnowledgeProfile,
    candidate_by_title: dict[str, ArtistSongCandidate],
) -> str:
    candidate = candidate_by_title.get(profile.identity.title.casefold())
    if candidate is None:
        return "source-backed song evidence"
    parts = [candidate.reason or "representative candidate"]
    if candidate.tab_likely or _has_tab_evidence(profile):
        parts.append("tab-backed")
    if candidate.popularity_rank is not None:
        parts.append(f"rank {candidate.popularity_rank}")
    return ", ".join(parts)


def _has_tab_evidence(profile: SongKnowledgeProfile) -> bool:
    return bool(profile.playable_parts) or any(claim.claim_type == "tab" for claim in profile.evidence_claims)


def _profile_confidence(profile: SongKnowledgeProfile) -> float:
    values = [claim.confidence for claim in profile.evidence_claims]
    if profile.playable_parts:
        values.extend(part.confidence for part in profile.playable_parts)
    if not values:
        return 0.25
    return round(min(0.95, sum(values) / len(values) + (0.05 if _has_tab_evidence(profile) else 0.0)), 2)


def _source_claims(profiles: list[SongKnowledgeProfile]) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    for profile in profiles:
        for claim in profile.evidence_claims:
            if claim.claim_type in {
                "tempo",
                "key",
                "meter",
                "chord_progression",
                "instrumentation",
                "groove",
                "trait",
                "timbre",
                "tone",
                "tab",
                "metadata",
            }:
                claims.append(claim)
    claims.sort(key=lambda claim: claim.confidence, reverse=True)
    return claims[:32]


def _genres_from_profiles(profiles: list[SongKnowledgeProfile]) -> list[str]:
    values: list[str] = []
    for profile in profiles:
        metadata = profile.metadata or {}
        for key in ["genre", "genres", "style", "styles"]:
            value = metadata.get(key)
            if isinstance(value, str):
                values.extend(_split_tags(value))
            elif isinstance(value, list):
                values.extend(str(item) for item in value if str(item).strip())
        values.extend(_claim_values([profile], {"metadata", "trait"}, words={"genre", "style"}))
    return values


def _split_tags(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,/;]", value) if part.strip()]


def _claim_values(
    profiles: list[SongKnowledgeProfile],
    claim_types: set[str],
    *,
    words: set[str] | None = None,
) -> list[str]:
    values: list[str] = []
    for profile in profiles:
        for claim in profile.evidence_claims:
            if claim.claim_type not in claim_types:
                continue
            haystack = f"{claim.value} {claim.snippet} {' '.join(claim.notes)}".lower()
            if words is not None and not any(word in haystack for word in words):
                continue
            values.append(claim.normalized_value or claim.value)
    return values


def _instrument_names(profiles: list[SongKnowledgeProfile]) -> list[str]:
    names: list[str] = []
    for profile in profiles:
        names.extend(part.instrument_family for part in profile.playable_parts if part.instrument_family)
        names.extend(trait.instrument for trait in profile.traits)
        for claim in profile.evidence_claims:
            if claim.claim_type not in {"instrumentation", "tab"}:
                continue
            for instrument in ["drums", "bass", "guitar", "piano", "keys", "synth", "vocals"]:
                if instrument in claim.value.lower():
                    names.append(instrument)
    return names


def _tone_profiles(profiles: list[SongKnowledgeProfile]) -> list[ToneProfile]:
    seen: set[str] = set()
    tones: list[ToneProfile] = []
    for profile in profiles:
        for tone in profile.tone_profiles:
            if tone.tone_id in seen:
                continue
            seen.add(tone.tone_id)
            tones.append(tone)
    return tones[:12]


def _role_traits(profiles: list[SongKnowledgeProfile], role: str) -> list[str]:
    values: list[str] = []
    for profile in profiles:
        for trait in profile.traits:
            if role in f"{trait.instrument} {trait.role}".lower():
                values.extend(f"{key}: {value}" for key, value in trait.traits.items())
        values.extend(_claim_values([profile], {"instrumentation", "groove", "trait", "tab"}, words={role}))
    return _top_strings(values, limit=8)


def _production_traits(profiles: list[SongKnowledgeProfile]) -> list[str]:
    values = _claim_values(profiles, {"timbre", "tone", "trait", "metadata"}, words={"sound", "tone", "synth", "amp", "production", "mix"})
    for tone in _tone_profiles(profiles):
        if tone.description:
            values.append(tone.description)
        if tone.patch_family:
            values.append(tone.patch_family)
    return _top_strings(values, limit=10)


def _section_traits(profiles: list[SongKnowledgeProfile]) -> list[str]:
    values: list[str] = []
    for profile in profiles:
        if profile.sections:
            values.append(" -> ".join(section.name for section in profile.sections[:8]))
        energetic = [section.name for section in profile.sections if section.energy is not None and section.energy >= 0.7]
        if energetic:
            values.append("higher energy sections: " + ", ".join(energetic[:4]))
    return _top_strings(values, limit=8)


def _tempo_range(profiles: list[SongKnowledgeProfile]) -> tuple[float | None, float | None]:
    tempos: list[float] = []
    for value in _claim_values(profiles, {"tempo"}):
        match = re.search(r"(\d+(?:\.\d+)?)", value)
        if match:
            tempos.append(float(match.group(1)))
    if not tempos:
        return (None, None)
    return (min(tempos), max(tempos))


def _top_strings(values: list[str], *, limit: int) -> list[str]:
    cleaned = [re.sub(r"\s+", " ", value).strip() for value in values if str(value).strip()]
    counts = Counter(cleaned)
    return [value for value, _ in counts.most_common(limit)]


def _artist_aliases(profiles: list[SongKnowledgeProfile]) -> list[str]:
    aliases: list[str] = []
    for profile in profiles:
        for name in [profile.identity.artist, *profile.identity.primary_artists]:
            if name and name not in aliases:
                aliases.append(name)
    return aliases[:8]


def _artist_confidence(representatives: list[RepresentativeSong], claims: list[EvidenceClaim]) -> float:
    if not representatives and not claims:
        return 0.2
    values = [song.confidence for song in representatives] + [claim.confidence for claim in claims[:12]]
    if not values:
        return 0.3
    evidence_bonus = 0.08 if any(song.tab_available for song in representatives) else 0.0
    return round(min(0.95, sum(values) / len(values) + evidence_bonus), 2)


def _confidence_summary(profiles: list[SongKnowledgeProfile], confidence: float) -> dict[str, str]:
    return {
        "overall": _confidence_word(confidence),
        "representative_songs": str(len(profiles)),
        "tab_backed_songs": str(sum(1 for profile in profiles if _has_tab_evidence(profile))),
    }


def _confidence_word(confidence: float) -> str:
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _uncertainty_notes(candidates: list[ArtistSongCandidate], profiles: list[SongKnowledgeProfile]) -> list[str]:
    notes: list[str] = []
    if not candidates:
        notes.append("No representative song candidates were available; profile uses low-confidence priors only.")
    if len(profiles) < max(1, min(3, len(candidates))):
        notes.append("Some representative song evidence could not be fetched.")
    if profiles and not any(_has_tab_evidence(profile) for profile in profiles):
        notes.append("No Songsterr/tab-backed representative song evidence was found.")
    return notes


def _artist_profile_id(artist_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", artist_name.lower()).strip("_")
    if slug:
        return f"artist_{slug}"
    digest = hashlib.sha1(artist_name.encode("utf-8")).hexdigest()[:12]
    return f"artist_{digest}"
