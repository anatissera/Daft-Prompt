"""Compact, provider-agnostic constraints for reference-guided composition."""

from __future__ import annotations

import re
from typing import Any

from music_assistant.domain.audio_profile import FidelityMode, SongKnowledgeProfile


_FAMILY_ALIASES = {
    "drums": ("drum", "drums", "drum kit", "drum_kit", "percussion", "batería", "bateria"),
    "bass": ("bass", "electric_bass", "bass guitar", "bajo"),
    "guitar": ("guitar", "electric_guitar", "acoustic_guitar", "guitarra"),
    "piano": ("piano", "keyboard", "keys", "rhodes", "teclado"),
    "synth": ("synth", "synthesizer", "pad", "supersaw"),
}


def infer_fidelity_mode(message: str, *, has_reference: bool) -> FidelityMode:
    normalized = message.lower()
    if re.search(r"\b(exact(?:ly)?|verbatim|recreate|reproduction|same song|as close as possible)\b", normalized):
        return "exact_or_as_close_as_possible"
    if re.search(r"\b(very similar|high fidelity|closely|close to|lo m[aá]s parecido)\b", normalized):
        return "very_similar"
    return "similar" if has_reference else "similar"


def build_reference_instrumentation(profiles: list[SongKnowledgeProfile]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for profile in profiles:
        counts: dict[str, int] = {}
        evidence: dict[str, list[str]] = {}
        index = profile.metadata.get("songsterr_tab_index") if isinstance(profile.metadata, dict) else None
        tracks = index.get("tracks", []) if isinstance(index, dict) else []
        for track in tracks if isinstance(tracks, list) else []:
            if not isinstance(track, dict):
                continue
            family = normalize_family(str(track.get("instrument") or track.get("name") or ""))
            if family is None:
                continue
            counts[family] = counts.get(family, 0) + 1
            evidence.setdefault(family, []).append(str(track.get("name") or track.get("instrument") or family))
        for claim in profile.evidence_claims:
            if claim.claim_type not in {"instrumentation", "tab", "tone", "trait"}:
                continue
            text = f"{claim.value} {claim.snippet}".lower()
            for family in _FAMILY_ALIASES:
                if any(alias in text for alias in _FAMILY_ALIASES[family]):
                    counts.setdefault(family, 0)
                    evidence.setdefault(family, []).append(claim.value[:140])

        families = sorted(counts)
        guitar_led = "guitar" in families and counts.get("guitar", 0) >= max(
            counts.get("piano", 0), counts.get("synth", 0), 1
        )
        result[profile.profile_id] = {
            "title": profile.identity.title,
            "artist": profile.identity.artist,
            "families": families,
            "family_counts": counts,
            "evidence": {family: values[:3] for family, values in evidence.items()},
            "salience": {
                "guitar_led": guitar_led,
                "piano_support": "piano" in families and counts.get("piano", 0) <= 1,
                "synth_supported": "synth" in families,
            },
        }
    return result


def build_style_guardrails(message: str, profiles: list[SongKnowledgeProfile]) -> dict[str, Any]:
    normalized = message.lower()
    source = build_reference_instrumentation(profiles)
    source_families = sorted({family for item in source.values() for family in item.get("families", [])})
    explicit = sorted(explicit_instrument_families(message))
    expected: list[str] = []
    discouraged: list[str] = []
    priorities: list[str] = []
    genre_hints: list[str] = []

    if source_families:
        expected.extend(source_families)
        if "guitar" in source_families and "piano" not in explicit and "synth" not in explicit:
            discouraged.extend(["unsupported_synth", "piano_heavy_balance"])
        priorities.append("preserve reference family salience and source-backed roles")

    if re.search(r"\b(classic rock|baroque pop|rock|grunge|punk|garage|blues|folk)\b", normalized):
        genre_hints.append("roots_or_guitar_band")
        expected.extend(["drums", "bass", "guitar"])
        if not explicit:
            discouraged.append("synth_default")
        priorities.append("guitar riff/comping, bass pulse, and live drum articulation")
    if re.search(r"\b(funk|disco)\b", normalized):
        genre_hints.append("syncopated_dance_band")
        expected.extend(["drums", "bass"])
        priorities.append("syncopated drums and bass with short guitar or keys accents")
    if re.search(r"\b(french house|house|electronic|edm|synthwave)\b", normalized):
        genre_hints.append("electronic_dance")
        expected.extend(["drums", "bass", "synth"])
        priorities.append("four-on-the-floor drums, filtered harmony, and controlled synth texture")

    return {
        "mode": "non_binding_quality_guardrails",
        "expected_families": sorted(set(expected)),
        "discouraged_families": sorted(set(discouraged)),
        "explicit_exceptions": explicit,
        "rhythmic_priorities": list(dict.fromkeys(priorities)),
        "genre_hints": genre_hints,
        "source_families": source_families,
        "creative_note": "Use these to catch obvious mismatches; keep the LLM responsible for idiomatic variation.",
    }


def explicit_instrument_families(message: str) -> set[str]:
    normalized = message.lower()
    return {
        family
        for family, aliases in _FAMILY_ALIASES.items()
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases)
    }


def normalize_family(value: str) -> str | None:
    normalized = value.strip().lower().replace("-", "_")
    for family, aliases in _FAMILY_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return family
    return None
