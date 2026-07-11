"""Known-song evidence for the director, via Franco's source connectors.

When the style prompt references a SPECIFIC song ("hazme algo como Feel
Good Inc de Gorillaz"), we can do much better than blog prose: resolve the
song canonically on MusicBrainz, then scrape tab/chord sites (HookTheory,
CifraClub, LaCuerda) for its real key, tempo, meter and per-section chord
progressions — typed `EvidenceClaim`s with per-source confidence.

Generic genre prompts ("hazme un tango") fail MusicBrainz's conservative
match threshold and return None, costing one cheap API call. The digest is
injected into the skeleton prompt so the director grounds harmony/tempo in
the actual song instead of its prior.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from music_assistant.infrastructure.web_research.connectors import (
    CifraClubConnector,
    HookTheoryConnector,
    LaCuerdaConnector,
)
from music_assistant.infrastructure.web_research.entity_resolution import (
    resolve_song_entity,
)
from music_assistant.infrastructure.web_research.musicbrainz import (
    MusicBrainzConnector,
)

log = logging.getLogger(__name__)

# Claim types that actually inform composition; credits/lyrics don't.
_GENERATIVE_CLAIM_TYPES = {"tempo", "key", "meter", "chord_progression", "section"}
_MAX_CLAIMS = 20
_CONNECTOR_TIMEOUT_S = 10.0

# Franco's entity resolver understands "Title by Artist" / "Title - Artist".
# Our users write Spanish directives: "hazme algo como Feel Good Inc de
# Gorillaz". Strip the directive framing and also try the "<title> de
# <artist>" split. Wrong splits are harmless: MusicBrainz's conservative
# similarity gate rejects them and we return None.
_DIRECTIVE_RE = re.compile(
    r"^\s*(?:hazme|haceme|hac[eé]|quiero|dame|compon[eé]me?|gener[aá]me?|"
    r"make me|make|compose|write|play|toc[aá]me?)\b"
    r"(?:\s+(?:algo|una\s+canci[oó]n|un\s+tema|something|a\s+song|a\s+track))?"
    r"(?:\s+(?:como|parecid[oa]\s+a|tipo|estilo(?:\s+de)?|al\s+estilo\s+de|"
    r"like|similar\s+to|inspirad[oa]\s+en|inspired\s+by|based\s+on))?\s*",
    re.IGNORECASE,
)

# Question scaffolding: "which chords does <song> have?", "¿qué acordes
# tiene <song>?", "what key is <song> in?". Strip the interrogative head
# (up to the auxiliary/topic verb) and the dangling tail verb so the song
# reference survives entity resolution.
_QUESTION_HEAD_RE = re.compile(
    r"^\s*[¿]?\s*(?:which|what|who|how(?:\s+many)?|qu[eé]|cu[aá]l(?:es)?|"
    r"qui[eé]n(?:es)?)\b[^?]{0,40}?"
    r"\b(?:does|do|is|are|has|have|tiene[ns]?|usa[n]?|lleva[n]?|est[aá]n?\s+en|"
    r"son\s+de|es\s+de)\b\s*",
    re.IGNORECASE,
)
_QUESTION_TAIL_RE = re.compile(
    r"\s*\b(?:got|have|has|in|use[sd]?|written\s+in)\s*\??\s*$|\s*\?\s*$",
    re.IGNORECASE,
)


def _candidate_queries(style: str):
    from music_assistant.ports.song_source_connector import ResolvedSongQuery

    dequestioned = _QUESTION_TAIL_RE.sub("", _QUESTION_HEAD_RE.sub("", style)).strip()
    cleaned = _DIRECTIVE_RE.sub("", dequestioned or style).strip().strip('"“”')
    seen: set[tuple[str, str | None]] = set()
    out = []
    for raw in (cleaned, style.strip()):
        if not raw:
            continue
        q = resolve_song_entity(raw)
        variants = [q]
        # Spanish attribution: "<title> de <artist>" — split on the LAST
        # " de " so multi-"de" titles keep their head intact.
        if q.artist is None and " de " in raw.lower():
            idx = raw.lower().rfind(" de ")
            title, artist = raw[:idx].strip(), raw[idx + 4:].strip()
            if title and artist:
                variants.append(ResolvedSongQuery(title=title, artist=artist))
        for v in variants:
            key = (v.title.lower(), (v.artist or "").lower() or None)
            if key not in seen:
                seen.add(key)
                out.append(v)
    return out


def gather_song_evidence(style: str) -> dict[str, Any] | None:
    """Return a compact evidence digest for a specific referenced song, or
    None when the prompt doesn't resolve to one. Never raises."""
    try:
        import time

        mb_connector = MusicBrainzConnector()
        canonical = None
        for i, query in enumerate(_candidate_queries(style)[:3]):
            if not (query.title or "").strip():
                continue
            if i:
                # MusicBrainz enforces 1 request/second; back-to-back candidate
                # lookups get 503'd otherwise.
                time.sleep(1.1)
            mb = mb_connector.collect(query)
            if mb.fetch_status == "fetched":
                canonical = mb.query
                break
        if canonical is None:
            return None
        # Two fixups before scraping: (1) MusicBrainz canonical titles keep
        # trailing punctuation ("Feel Good Inc.") that breaks chord-site URL
        # slugs; (2) MusicBrainz sets source_url to ITS recording page, and
        # every connector honours `query.source_url or <own site URL>` — so
        # without clearing it they'd all scrape musicbrainz.org.
        canonical = canonical.model_copy(update={
            "title": canonical.title.rstrip(".!? ").strip(),
            "source_url": None,
        })

        claims: list[Any] = []
        connectors = [HookTheoryConnector(), CifraClubConnector(), LaCuerdaConnector()]
        # No `with` block: the executor's __exit__ would wait for stragglers,
        # defeating the timeout. Slow connectors finish in the background and
        # their results are simply discarded.
        pool = ThreadPoolExecutor(max_workers=len(connectors))
        futures = {pool.submit(c.collect, canonical): c.source_name for c in connectors}
        pool.shutdown(wait=False)
        try:
            for fut in as_completed(futures, timeout=_CONNECTOR_TIMEOUT_S):
                try:
                    result = fut.result()
                except Exception as exc:
                    log.info("song_evidence: %s failed: %s", futures[fut], exc)
                    continue
                claims.extend(
                    c for c in result.claims if c.claim_type in _GENERATIVE_CLAIM_TYPES
                )
        except TimeoutError:
            log.info("song_evidence: connector timeout — using partial claims")
        if not claims:
            return None

        # Highest-confidence first; one claim per (type, section, source)
        # so a chatty page can't flood the prompt.
        seen: set[tuple[str, str | None, str]] = set()
        digest_claims: list[dict[str, Any]] = []
        for c in sorted(claims, key=lambda c: -c.confidence):
            key = (c.claim_type, c.section_name, c.source_name)
            if key in seen:
                continue
            seen.add(key)
            digest_claims.append({
                "type": c.claim_type,
                "value": c.value,
                "section": c.section_name,
                "source": c.source_name,
                "confidence": round(c.confidence, 2),
            })
            if len(digest_claims) >= _MAX_CLAIMS:
                break

        log.info(
            "song_evidence: %s — %s: %d claims from %d sources",
            canonical.title, canonical.artist,
            len(digest_claims), len({c['source'] for c in digest_claims}),
        )
        return {
            "song": canonical.title,
            "artist": canonical.artist,
            "claims": digest_claims,
        }
    except Exception as exc:
        log.info("song_evidence: skipped (%s: %s)", type(exc).__name__, exc)
        return None
