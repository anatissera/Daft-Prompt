"""HTML parsers for public song-research pages."""

from __future__ import annotations

import html
import re

from music_assistant.ports.song_researcher import ResearchClaim, ResearchPage
from music_assistant.ports.web_search import SearchResult


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_BPM_RE = re.compile(r"\b(?:tempo|bpm)\b[^0-9]{0,20}(\d{2,3}(?:\.\d+)?)\s*(?:bpm)?", re.IGNORECASE)
_KEY_RE = re.compile(r"\bkey\b[^A-G]{0,20}([A-G](?:#|b|♯|♭)?\s*(?:major|minor|maj|min|m)?)", re.IGNORECASE)
_CHORD_LINE_RE = re.compile(r"\b([A-G](?:#|b)?(?:m|maj|min|dim|sus|add)?(?:\d{0,2})?(?:\s*[-|]\s*[A-G](?:#|b)?(?:m|maj|min|dim|sus|add)?(?:\d{0,2})?){2,})\b")


class GenericSongPageParser:
    def parse(self, result: SearchResult, html_text: str) -> ResearchPage:
        text = _visible_text(html_text)
        claims: list[ResearchClaim] = []
        for match in _BPM_RE.finditer(text):
            bpm = match.group(1)
            claims.append(ResearchClaim(type="tempo", value=f"{bpm} BPM", confidence=0.62, snippet=_snippet(text, match.start())))
        for match in _KEY_RE.finditer(text):
            claims.append(ResearchClaim(type="key", value=match.group(1).strip(), confidence=0.58, snippet=_snippet(text, match.start())))
        for match in _CHORD_LINE_RE.finditer(text):
            claims.append(ResearchClaim(type="chords", value=match.group(1).strip(), confidence=0.45, snippet=_snippet(text, match.start())))
        return ResearchPage(
            url=result.url,
            site=result.site or _site_from_url(result.url),
            title=result.title or _title(html_text),
            claims=claims[:20],
        )


def _visible_text(html_text: str) -> str:
    unescaped = html.unescape(html_text)
    without_scripts = re.sub(r"<(script|style).*?</\1>", " ", unescaped, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", without_scripts)).strip()


def _title(html_text: str) -> str:
    match = _TITLE_RE.search(html_text)
    return _visible_text(match.group(1)) if match else ""


def _snippet(text: str, start: int) -> str:
    return text[max(0, start - 70): start + 160].strip()


def _site_from_url(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else "unknown"
