"""Source-specific connectors for web-first song research."""

from __future__ import annotations

import html
import re
from urllib.parse import quote_plus

from music_assistant.domain.audio_profile import EvidenceClaim
from music_assistant.infrastructure.web_research.fetch import UrlLibPageFetcher
from music_assistant.ports.page_fetcher import PageFetcher
from music_assistant.ports.song_source_connector import (
    ConnectorFailure,
    ConnectorResult,
    FetchStatus,
    ResolvedSongQuery,
)


_TAG_RE = re.compile(r"<[^>]+>")
_KEY_FACT_RE = re.compile(r"<dt>\s*Key\s*</dt>\s*<dd>\s*([^<]+)\s*</dd>", re.IGNORECASE)
_TEMPO_FACT_RE = re.compile(r"<dt>\s*Tempo\s*</dt>\s*<dd>\s*([^<]+)\s*</dd>", re.IGNORECASE)
_METER_FACT_RE = re.compile(r"<dt>\s*Meter\s*</dt>\s*<dd>\s*([^<]+)\s*</dd>", re.IGNORECASE)
_SECTION_RE = re.compile(
    r"<section[^>]*data-section=[\"']([^\"']+)[\"'][^>]*>(.*?)</section>",
    re.IGNORECASE | re.DOTALL,
)
_PROGRESSION_RE = re.compile(
    r"<p[^>]*class=[\"']progression[\"'][^>]*>(.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)
_CIFRA_KEY_RE = re.compile(r"<div[^>]*class=[\"']tom[\"'][^>]*>\s*Tom:\s*([^<]+)</div>", re.IGNORECASE)
_CIFRA_KEY_LINK_RE = re.compile(r"title=[\"']alterar o tom da cifra[\"'][^>]*>\s*([^<]+)\s*</a>", re.IGNORECASE)
_PRE_RE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.IGNORECASE | re.DOTALL)
_BOLD_RE = re.compile(r"<b[^>]*>(.*?)</b>", re.IGNORECASE | re.DOTALL)
_SECTION_HEADING_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_CHORD_TOKEN_RE = re.compile(
    r"^[A-G](?:#|b)?[A-Za-z0-9()/#+-]*$"
)


class HookTheoryConnector:
    source_name = "HookTheory"

    def __init__(self, *, fetcher: PageFetcher | None = None) -> None:
        self.fetcher = fetcher or UrlLibPageFetcher()

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        url = query.source_url or _hooktheory_url(query)
        html_text, failure = _fetch_html(self.source_name, self.fetcher, query, url)
        if failure is not None:
            return failure

        claims: list[EvidenceClaim] = []
        key = _first_match(_KEY_FACT_RE, html_text)
        if key:
            claims.append(_claim("key", key, self.source_name, url, 0.72, f"Key: {key}"))
        tempo = _first_match(_TEMPO_FACT_RE, html_text)
        if tempo:
            claims.append(_claim("tempo", tempo, self.source_name, url, 0.76, f"Tempo: {tempo}"))
        meter = _first_match(_METER_FACT_RE, html_text)
        if meter:
            claims.append(_claim("meter", meter, self.source_name, url, 0.68, f"Meter: {meter}"))

        for section_name, section_html in _SECTION_RE.findall(html_text):
            original_section = section_name.strip().lower()
            normalized_section = _normalize_section_name(original_section)
            claims.append(
                _claim(
                    "section",
                    normalized_section,
                    self.source_name,
                    url,
                    0.65,
                    f"Section: {original_section}",
                    section_name=normalized_section,
                )
            )
            progression = _first_match(_PROGRESSION_RE, section_html)
            if progression:
                clean_progression = _visible_text(progression)
                claims.append(
                    _claim(
                        "chord_progression",
                        clean_progression,
                        self.source_name,
                        url,
                        0.7,
                        f"{normalized_section}: {clean_progression}",
                        section_name=normalized_section,
                    )
                )

        return _result_or_empty(self.source_name, query, claims, url, html_text)


class CifraClubConnector:
    source_name = "CifraClub"

    def __init__(self, *, fetcher: PageFetcher | None = None) -> None:
        self.fetcher = fetcher or UrlLibPageFetcher()

    def collect(self, query: ResolvedSongQuery) -> ConnectorResult:
        url = query.source_url or _cifraclub_url(query)
        html_text, failure = _fetch_html(self.source_name, self.fetcher, query, url)
        if failure is not None:
            return failure

        claims: list[EvidenceClaim] = []
        key = _first_match(_CIFRA_KEY_RE, html_text) or _first_match(_CIFRA_KEY_LINK_RE, html_text)
        if key:
            claims.append(_claim("key", key, self.source_name, url, 0.62, f"Tom: {key}"))

        pre_match = _PRE_RE.search(html_text)
        if pre_match:
            claims.extend(_claims_from_cifra_pre(pre_match.group(1), self.source_name, url))

        return _result_or_empty(self.source_name, query, claims, url, html_text)


def _fetch_html(
    source_name: str,
    fetcher: PageFetcher,
    query: ResolvedSongQuery,
    url: str,
) -> tuple[str, None] | tuple[str, ConnectorResult]:
    try:
        return fetcher.fetch(url), None
    except RuntimeError as exc:
        return "", ConnectorResult(
            source_name=source_name,
            query=query,
            fetch_status="blocked" if "403" in str(exc) else "error",
            failures=[
                ConnectorFailure(
                    source_name=source_name,
                    url=url,
                    status="blocked" if "403" in str(exc) else "error",
                    reason=str(exc),
                )
            ],
        )


def _result_or_empty(
    source_name: str,
    query: ResolvedSongQuery,
    claims: list[EvidenceClaim],
    url: str,
    html_text: str,
) -> ConnectorResult:
    if claims:
        return ConnectorResult(source_name=source_name, query=query, fetch_status="fetched", claims=claims)
    status: FetchStatus = "js_rendered" if "<script" in html_text and "id=\"root\"" in html_text else "empty"
    return ConnectorResult(
        source_name=source_name,
        query=query,
        fetch_status=status,
        failures=[
            ConnectorFailure(
                source_name=source_name,
                url=url,
                status=status,
                reason="No structured claims found in fetched page.",
            )
        ],
    )


def _claims_from_cifra_pre(pre_html: str, source_name: str, url: str) -> list[EvidenceClaim]:
    text = html.unescape(pre_html)
    claims: list[EvidenceClaim] = []
    section = "unknown"
    chord_lines: list[str] = []
    for raw_line in text.splitlines():
        line = _visible_text(raw_line)
        if not line:
            continue
        heading = _SECTION_HEADING_RE.match(line)
        if heading:
            if chord_lines:
                claims.append(_section_chords_claim(section, chord_lines, source_name, url))
            original_section = heading.group(1).strip().lower()
            section = _normalize_section_name(original_section)
            claims.append(
                _claim("section", section, source_name, url, 0.58, f"Section: {original_section}", section_name=section)
            )
            chord_lines = []
            continue
        tokens = [_visible_text(token) for token in _BOLD_RE.findall(raw_line)]
        if not tokens:
            tokens = line.split()
        if tokens and all(_CHORD_TOKEN_RE.match(token) for token in tokens):
            chord_lines.append(" ".join(tokens))
    if chord_lines:
        claims.append(_section_chords_claim(section, chord_lines, source_name, url))
    return claims


def _section_chords_claim(section: str, chord_lines: list[str], source_name: str, url: str) -> EvidenceClaim:
    progression = " | ".join(chord_lines)
    return _claim(
        "chord_progression",
        progression,
        source_name,
        url,
        0.64,
        f"{section}: {progression}",
        section_name=section,
    )


def _claim(
    claim_type: str,
    value: str,
    source_name: str,
    url: str,
    confidence: float,
    snippet: str,
    *,
    section_name: str | None = None,
) -> EvidenceClaim:
    claim_id = _claim_id(source_name, claim_type, value, section_name)
    return EvidenceClaim(
        claim_id=claim_id,
        claim_type=claim_type,  # type: ignore[arg-type]
        value=value.strip(),
        normalized_value=value.strip(),
        section_name=section_name,
        source_name=source_name,
        source_url=url,
        extraction_method="site_parser",
        confidence=confidence,
        snippet=snippet[:280],
    )


def _claim_id(source_name: str, claim_type: str, value: str, section_name: str | None) -> str:
    raw = f"{source_name}:{claim_type}:{section_name or ''}:{value}".lower()
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")[:96]


def _first_match(pattern: re.Pattern[str], html_text: str) -> str:
    match = pattern.search(html_text)
    return _visible_text(match.group(1)) if match else ""


def _visible_text(html_text: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(html_text))).strip()


def _normalize_section_name(section: str) -> str:
    normalized = (
        section.strip().lower()
        .replace("ã", "a")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    aliases = {
        "refrao": "chorus",
        "refrain": "chorus",
        "coro": "chorus",
        "estribillo": "chorus",
        "primeira parte": "verse",
        "segunda parte": "verse",
        "parte": "verse",
        "verso": "verse",
        "estrofa": "verse",
        "ponte": "bridge",
        "puente": "bridge",
        "pre refrao": "pre-chorus",
        "pre-refrain": "pre-chorus",
        "pre estribillo": "pre-chorus",
        "introducao": "intro",
        "introduccion": "intro",
        "final": "outro",
    }
    return aliases.get(normalized, normalized)


def _hooktheory_url(query: ResolvedSongQuery) -> str:
    artist = quote_plus((query.artist or "").lower().replace(" ", "-"))
    title = quote_plus(query.title.lower().replace(" ", "-"))
    suffix = f"{artist}/{title}" if artist else title
    return f"https://www.hooktheory.com/theorytab/view/{suffix}"


def _cifraclub_url(query: ResolvedSongQuery) -> str:
    artist = quote_plus((query.artist or "").lower().replace(" ", "-"))
    title = quote_plus(query.title.lower().replace(" ", "-"))
    suffix = f"{artist}/{title}" if artist else title
    return f"https://www.cifraclub.com.br/{suffix}/"
