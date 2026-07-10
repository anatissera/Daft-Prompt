from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from pathlib import Path

from music_assistant.infrastructure.web_research.entity_resolution import normalize_match_text, token_similarity
from music_assistant.infrastructure.web_research.entity_resolution import resolve_song_entity
from music_assistant.infrastructure.web_research.musicbrainz import MusicBrainzConnector
from music_assistant.interfaces.api import _song_researcher


CASES = Path(__file__).with_name("famous_song_lookup.json")


def main() -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    researcher = _song_researcher()
    primary = MusicBrainzConnector()
    rows = []
    provider_usage: Counter[str] = Counter()
    for case in cases:
        started = time.perf_counter()
        primary_result = primary.collect(resolve_song_entity(case["query"]))
        fallback_used = not bool(primary_result.claims)
        if fallback_used:
            profile = researcher.research(case["query"])
            knowledge = profile.knowledge
            identity = knowledge.identity if knowledge else resolve_song_entity(case["query"])
            claims = knowledge.evidence_claims if knowledge else []
        else:
            identity = primary_result.query
            claims = primary_result.claims
        latency = time.perf_counter() - started
        providers = sorted({claim.source_name for claim in claims})
        provider_usage.update(providers)
        actual_artists = [
            *identity.primary_artists,
            *identity.featured_artists,
            *identity.collaborating_artists,
        ]
        title_ok = token_similarity(case["title"], identity.title) >= 0.6
        artist_ok = all(_matches_any(expected, actual_artists) for expected in case.get("artists", []))
        featured_ok = all(_matches_any(expected, identity.featured_artists) for expected in case.get("featured", []))
        usable = any(
            claim.claim_type in {"metadata", "credit", "tempo", "key", "chord_progression", "tab", "instrumentation"}
            and "Generic tab available" not in claim.value
            for claim in claims
        )
        identified = title_ok and artist_ok
        rows.append({
            "query": case["query"],
            "case": case["case"],
            "identified": identified,
            "artist_ok": artist_ok,
            "featured_ok": featured_ok if case.get("featured") else None,
            "usable_evidence": usable,
            "latency_seconds": round(latency, 3),
            "providers": providers,
            "fallback_used": fallback_used,
            "false_match": bool(claims) and not identified,
            "resolved_title": identity.title,
            "resolved_artists": actual_artists,
        })
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    featured_rows = [row for row in rows if row["featured_ok"] is not None]
    summary = {
        "tracks": len(rows),
        "successful_identification_rate": _rate(row["identified"] for row in rows),
        "correct_artist_resolution_rate": _rate(row["artist_ok"] for row in rows),
        "featured_artist_resolution_rate": _rate(row["featured_ok"] for row in featured_rows),
        "usable_evidence_rate": _rate(row["usable_evidence"] for row in rows),
        "average_latency_seconds": round(statistics.mean(row["latency_seconds"] for row in rows), 3),
        "provider_usage": dict(provider_usage),
        "fallback_frequency": _rate(row["fallback_used"] for row in rows),
        "false_match_rate": _rate(row["false_match"] for row in rows),
    }
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _matches_any(expected: str, actual: list[str]) -> bool:
    return any(
        normalize_match_text(expected) == normalize_match_text(candidate)
        or token_similarity(expected, candidate) >= 0.6
        for candidate in actual
    )


def _rate(values) -> float:
    values = list(values)
    return round(sum(bool(value) for value in values) / max(1, len(values)), 3)


if __name__ == "__main__":
    main()
