"""Normalize human song credits into a provider-neutral entity query."""

from __future__ import annotations

import re
import unicodedata

from music_assistant.ports.song_source_connector import ResolvedSongQuery


_FEAT_RE = re.compile(r"\b(?:feat\.?|ft\.?|featuring|con)\s+([^()\[\]]+)", re.IGNORECASE)
_PROD_RE = re.compile(r"\b(?:prod\.?|produced by)\s+([^()\[\]]+)", re.IGNORECASE)
_VERSION_RE = re.compile(
    r"\(([^)]*\b(?:remix|live|remaster(?:ed)?|acoustic|radio edit|album version|version)\b[^)]*)\)",
    re.IGNORECASE,
)
_CREDIT_PARENS_RE = re.compile(r"\((?:feat\.?|ft\.?|featuring|prod\.?).*?\)", re.IGNORECASE)
_PRIMARY_SPLIT_RE = re.compile(r"\s+(?:&|and|x|with|y)\s+", re.IGNORECASE)


def resolve_song_entity(query: str) -> ResolvedSongQuery:
    cleaned = _strip_song_question(normalize_display_text(query))
    title_text, artist_text = _split_title_artist(cleaned)

    version_match = _VERSION_RE.search(title_text)
    version = version_match.group(1).strip() if version_match else None
    remix_artist = None
    if version and "remix" in version.lower():
        remix_artist = re.sub(r"\bremix\b", "", version, flags=re.IGNORECASE).strip(" -") or None

    featured = _extract_people(title_text, _FEAT_RE) + _extract_people(artist_text, _FEAT_RE)
    producers = _extract_people(title_text, _PROD_RE) + _extract_people(artist_text, _PROD_RE)
    title = _CREDIT_PARENS_RE.sub("", title_text)
    if version_match:
        title = title.replace(version_match.group(0), "")
    title = _clean_part(title)

    primary_text = _FEAT_RE.split(artist_text, maxsplit=1)[0] if artist_text else ""
    primary_artists = _split_people(primary_text)
    artist = " & ".join(primary_artists) if primary_artists else None
    collaborators = primary_artists[1:]

    alternate_titles: list[str] = []
    accentless = strip_accents(title)
    if accentless.casefold() != title.casefold():
        alternate_titles.append(accentless)
    if "/" in title:
        alternate_titles.extend(_clean_part(part) for part in title.split("/") if _clean_part(part) != title)

    return ResolvedSongQuery(
        title=title,
        artist=artist,
        primary_artists=primary_artists,
        featured_artists=_dedupe(featured),
        collaborating_artists=_dedupe(collaborators),
        producers=_dedupe(producers),
        remix_artist=remix_artist,
        alternate_titles=_dedupe(alternate_titles),
        version=version,
    )


def query_variants(query: ResolvedSongQuery) -> list[ResolvedSongQuery]:
    variants = [query]
    titles = [*query.alternate_titles, strip_accents(query.title)]
    artists = [strip_accents(query.artist or "")]
    for title in titles:
        if title and title.casefold() != query.title.casefold():
            variants.append(query.model_copy(update={"title": title, "source_url": None}))
    for artist in artists:
        if artist and artist.casefold() != (query.artist or "").casefold():
            variants.append(query.model_copy(update={"artist": artist, "source_url": None}))
    unique: dict[tuple[str, str], ResolvedSongQuery] = {}
    for variant in variants:
        unique[(variant.title.casefold(), (variant.artist or "").casefold())] = variant
    return list(unique.values())


def normalize_display_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"}))
    return re.sub(r"\s+", " ", normalized).strip()


def strip_accents(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char))


def normalize_match_text(value: str) -> str:
    accentless = strip_accents(normalize_display_text(value)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", accentless).strip()


def token_similarity(left: str, right: str) -> float:
    left_tokens = set(normalize_match_text(left).split())
    right_tokens = set(normalize_match_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _split_title_artist(value: str) -> tuple[str, str]:
    by_parts = re.split(r"\s+(?:by|de)\s+", value, maxsplit=1, flags=re.IGNORECASE)
    if len(by_parts) == 2:
        return _clean_part(by_parts[0]), _clean_part(by_parts[1])
    dash = re.match(r"^(.+?)\s+-\s+(.+)$", value)
    if dash:
        return _clean_part(dash.group(2)), _clean_part(dash.group(1))
    return _clean_part(value), ""


def _strip_song_question(value: str) -> str:
    return re.sub(
        r"^\s*(?:what\s+(?:chords|key|instruments?)\s+(?:does|is|are)\s+|"
        r"qu[eé]\s+(?:acordes|tonalidad|instrumentos?)\s+(?:usa|tiene|es|hay\s+en)\s+)",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip(" ?")


def _extract_people(value: str, pattern: re.Pattern[str]) -> list[str]:
    return [person for match in pattern.finditer(value or "") for person in _split_people(match.group(1))]


def _split_people(value: str) -> list[str]:
    return [_clean_part(part) for part in _PRIMARY_SPLIT_RE.split(value or "") if _clean_part(part)]


def _clean_part(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" \t\r\n\"'-,"))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = normalize_match_text(value)
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result
