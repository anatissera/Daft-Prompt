"""MusicBrainz recording metadata fallback with conservative entity matching."""

from __future__ import annotations

import json
from urllib.parse import quote_plus

from music_assistant.domain.audio_profile import EvidenceClaim
from music_assistant.infrastructure.web_research.entity_resolution import normalize_match_text, token_similarity
from music_assistant.infrastructure.web_research.fetch import UrlLibPageFetcher
from music_assistant.ports.page_fetcher import PageFetcher
from music_assistant.ports.song_source_connector import ConnectorFailure, ConnectorResult, ResolvedSongQuery


class MusicBrainzConnector:
    source_name = "MusicBrainz"

    def __init__(self, *, fetcher: PageFetcher | None = None) -> None:
        self.fetcher = fetcher or UrlLibPageFetcher(timeout_seconds=6.0)

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        terms = [f'recording:"{query.title}"']
        if query.artist:
            terms.append(f'artist:"{query.artist}"')
        url = "https://musicbrainz.org/ws/2/recording/?fmt=json&limit=8&query=" + quote_plus(" AND ".join(terms))
        payload = None
        last_error: RuntimeError | json.JSONDecodeError | None = None
        for _attempt in range(2):
            try:
                payload = json.loads(self.fetcher.fetch(url))
                break
            except (RuntimeError, json.JSONDecodeError) as exc:
                last_error = exc
        if payload is None:
            return ConnectorResult(
                source_name=self.source_name,
                query=query,
                fetch_status="error",
                failures=[ConnectorFailure(source_name=self.source_name, url=url, status="error", reason=str(last_error))],
            )
        candidates = [_candidate(recording, query) for recording in payload.get("recordings", [])]
        accepted = [candidate for candidate in candidates if candidate is not None]
        if not accepted:
            return ConnectorResult(
                source_name=self.source_name,
                query=query.model_copy(update={"candidate_matches": _candidate_labels(payload)}),
                fetch_status="empty",
                failures=[ConnectorFailure(
                    source_name=self.source_name,
                    url=url,
                    status="empty",
                    reason="No MusicBrainz recording met the title/artist match threshold.",
                )],
            )
        score, recording, artists, featured = max(accepted, key=lambda item: item[0])
        artists = _unique(artists)
        featured = _unique([
            *featured,
            *(artist for expected in query.featured_artists for artist in artists if token_similarity(expected, artist) >= 0.6),
        ])
        recording_id = str(recording.get("id") or "")
        source_url = f"https://musicbrainz.org/recording/{recording_id}" if recording_id else url
        releases = recording.get("releases") or []
        album = str(releases[0].get("title")) if releases and releases[0].get("title") else query.album
        first_date = str(recording.get("first-release-date") or "")
        year = int(first_date[:4]) if first_date[:4].isdigit() else query.year
        primary = [artist for artist in artists if artist not in featured] or artists
        canonical = query.model_copy(update={
            "title": str(recording.get("title") or query.title),
            "artist": " & ".join(primary) if primary else query.artist,
            "primary_artists": primary,
            "featured_artists": featured or query.featured_artists,
            "collaborating_artists": primary[1:],
            "album": album,
            "year": year,
            "candidate_matches": _candidate_labels(payload),
            "source_url": source_url,
        })
        claims = [
            _claim("recording", "metadata", f"MusicBrainz recording: {canonical.title}", source_url, 0.9, f"Matched recording at {score:.2f}"),
            _claim("artists", "credit", "Recording artists: " + ", ".join(artists), source_url, 0.9, "MusicBrainz artist credit"),
        ]
        if featured:
            claims.append(_claim("featured", "credit", "Featured artists: " + ", ".join(featured), source_url, 0.88, "MusicBrainz featured credit"))
        if album:
            claims.append(_claim("album", "metadata", f"Release: {album}", source_url, 0.75, "MusicBrainz release"))
        if year:
            claims.append(_claim("year", "metadata", f"First released: {year}", source_url, 0.75, "MusicBrainz first release date"))
        return ConnectorResult(source_name=self.source_name, query=canonical, fetch_status="fetched", claims=claims)


def _candidate(recording: dict, query: ResolvedSongQuery):
    title_score = token_similarity(query.title, str(recording.get("title") or ""))
    credits = recording.get("artist-credit") or []
    artists = [str(item.get("name") or item.get("artist", {}).get("name") or "") for item in credits]
    artist_score = 1.0
    if query.artist:
        artist_score = max((token_similarity(query.artist, artist) for artist in artists), default=0.0)
    provider_score = float(recording.get("score") or 0) / 100.0
    total = title_score * 0.6 + artist_score * 0.3 + provider_score * 0.1
    if title_score < 0.6 or (query.artist and artist_score < 0.5):
        return None
    # MusicBrainz places the join phrase on the preceding primary credit.
    featured = []
    for index, item in enumerate(credits[:-1]):
        if any(marker in str(item.get("joinphrase") or "").lower() for marker in ["feat", "ft."]):
            featured.append(artists[index + 1])
    return total, recording, artists, featured


def _candidate_labels(payload: dict) -> list[str]:
    labels = []
    for recording in (payload.get("recordings") or [])[:5]:
        artists = [str(item.get("name") or "") for item in recording.get("artist-credit") or []]
        labels.append(f"{recording.get('title', '')} — {', '.join(artists)}".strip())
    return labels


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _claim(claim_id: str, claim_type: str, value: str, source_url: str, confidence: float, snippet: str) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=f"musicbrainz_{claim_id}",
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value,
        normalized_value=normalize_match_text(value),
        source_name="MusicBrainz",
        source_url=source_url,
        extraction_method="api",
        confidence=confidence,
        snippet=snippet,
    )
