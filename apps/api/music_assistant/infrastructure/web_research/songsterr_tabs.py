"""Songsterr full-tab loading and normalization.

This module is infrastructure-only and handles fetching/parsing Songsterr data.
Storage of heavy tab bundles lives behind the SongsterrTabStore port.
"""

from __future__ import annotations

from html import unescape
import json
import re
from typing import Any, Optional
from urllib.parse import quote_plus

from pydantic import BaseModel, Field

from music_assistant.infrastructure.web_research.fetch import CurlPageFetcher, FallbackPageFetcher, UrlLibPageFetcher
from music_assistant.ports.page_fetcher import PageFetcher
from music_assistant.ports.song_source_connector import ResolvedSongQuery


class TabEvent(BaseModel):
    measure_index: int
    beat_index: int
    duration: str = ""
    rest: bool = False
    string: Optional[float] = None
    fret: Optional[int] = None
    tie: bool = False
    ghost: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class TabMeasure(BaseModel):
    index: int
    marker: Optional[str] = None
    signature: Optional[tuple[int, int]] = None
    events: list[TabEvent] = Field(default_factory=list)


class InstrumentTabTrack(BaseModel):
    part_id: int
    name: str
    instrument: str
    instrument_family: str
    source_url: str = ""
    tuning: list[str] = Field(default_factory=list)
    difficulty: Optional[str] = None
    is_bass: bool = False
    is_drums: bool = False
    is_guitar: bool = False
    is_piano: bool = False
    measures: list[TabMeasure] = Field(default_factory=list)
    note_count: int = 0
    beat_count: int = 0


class SongsterrTabBundle(BaseModel):
    source_url: str
    song_id: int
    revision_id: int
    image: str
    title: str
    artist: Optional[str] = None
    tempo_bpm: Optional[float] = None
    tracks: list[InstrumentTabTrack] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def instrument_names(self) -> list[str]:
        names: list[str] = []
        for track in self.tracks:
            if track.instrument_family not in names:
                names.append(track.instrument_family)
        return names

    def tracks_for_instrument(self, instrument: str) -> list[InstrumentTabTrack]:
        normalized = _normalize_instrument(instrument)
        return [
            track
            for track in self.tracks
            if track.instrument_family == normalized
            or (normalized == "bass" and track.is_bass)
            or (normalized == "drums" and track.is_drums)
            or (normalized == "guitar" and track.is_guitar)
            or (normalized == "piano" and track.is_piano)
        ]


class SongsterrTabLoader:
    def __init__(
        self,
        *,
        fetcher: PageFetcher | None = None,
        cdn_bases: tuple[str, ...] = (
            "https://dqsljvtekg760.cloudfront.net",
            "https://d3d3l6a6rcgkaf.cloudfront.net",
        ),
    ) -> None:
        self.fetcher = fetcher or FallbackPageFetcher(
            primary=UrlLibPageFetcher(timeout_seconds=4.0),
            fallback=CurlPageFetcher(timeout_seconds=4.0),
            retry_when="HTTP Error",
        )
        self.cdn_bases = cdn_bases

    def load(self, query: ResolvedSongQuery) -> Optional[SongsterrTabBundle]:
        bundles: list[SongsterrTabBundle] = []
        seen_urls: set[str] = set()
        for instrument in [None, "guitar", "bass", "drum", "piano"]:
            for url in self._candidate_tab_urls(query, instrument=instrument):
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                bundle = self.load_from_tab_url(url, query)
                if bundle is not None and bundle.tracks:
                    bundles.append(bundle)
                    break
        return _merge_bundles(bundles)

    def load_from_tab_url(self, url: str, query: ResolvedSongQuery) -> Optional[SongsterrTabBundle]:
        try:
            html_text = self.fetcher.fetch(url)
        except RuntimeError:
            return None
        state = _state_from_html(html_text)
        current = state.get("meta", {}).get("current", {})
        if not all(current.get(key) for key in ["songId", "revisionId", "image"]):
            return None

        song_id = int(current["songId"])
        revision_id = int(current["revisionId"])
        image = str(current["image"])
        tracks_meta = [track for track in current.get("tracks", []) if isinstance(track.get("partId"), int)]
        warnings: list[str] = []
        tracks: list[InstrumentTabTrack] = []
        for meta in tracks_meta:
            payload = self._fetch_track_payload(song_id, revision_id, image, int(meta["partId"]), warnings)
            if payload is None:
                continue
            tracks.append(_track_from_payload(meta, payload, source_url=url))

        tempo = _tempo_from_state(current)
        return SongsterrTabBundle(
            source_url=url,
            song_id=song_id,
            revision_id=revision_id,
            image=image,
            title=str(current.get("title") or query.title),
            artist=current.get("artist") or query.artist,
            tempo_bpm=tempo,
            tracks=tracks,
            warnings=warnings,
        )

    def _fetch_track_payload(
        self,
        song_id: int,
        revision_id: int,
        image: str,
        part_id: int,
        warnings: list[str],
    ) -> Optional[dict[str, Any]]:
        last_error = ""
        for base in self.cdn_bases:
            url = f"{base}/{song_id}/{revision_id}/{image}/{part_id}.json"
            try:
                return json.loads(self.fetcher.fetch(url))
            except (RuntimeError, KeyError, json.JSONDecodeError) as exc:
                last_error = str(exc)
        warnings.append(f"Could not fetch Songsterr part {part_id}: {last_error}")
        return None

    def _candidate_tab_urls(self, query: ResolvedSongQuery, *, instrument: str | None = None) -> list[str]:
        query_text = " ".join(part for part in [query.title, query.artist] if part).strip()
        encoded = quote_plus(query_text)
        suffix = f"&inst={instrument}" if instrument else ""
        search_urls = [f"https://www.songsterr.com/?pattern={encoded}{suffix}"]
        candidates: list[tuple[int, str]] = []
        for search_url in search_urls:
            try:
                html_text = self.fetcher.fetch(search_url)
            except (RuntimeError, KeyError):
                continue
            for href, label in _songsterr_result_links(html_text):
                candidates.append((_score_result(href, label, query), href))
        ordered: list[str] = []
        for _, href in sorted(candidates, key=lambda item: item[0], reverse=True):
            if href not in ordered:
                ordered.append(href)
        return ordered


def _state_from_html(html_text: str) -> dict[str, Any]:
    match = re.search(r'<script[^>]+id=["\']state["\'][^>]*>(.*?)</script>', html_text, re.DOTALL | re.IGNORECASE)
    if not match:
        return {}
    try:
        return json.loads(unescape(match.group(1)))
    except json.JSONDecodeError:
        return {}


def _tempo_from_state(current: dict[str, Any]) -> Optional[float]:
    tempo = current.get("tempo")
    if isinstance(tempo, dict) and tempo.get("bpm") is not None:
        return float(tempo["bpm"])
    if current.get("bpm") is not None:
        return float(current["bpm"])
    return None


def _songsterr_result_links(html_text: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for href, body in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html_text, flags=re.IGNORECASE | re.DOTALL):
        clean_href = unescape(href)
        if not clean_href.startswith("/a/wsa/"):
            continue
        label = _visible_text(body)
        if not label:
            continue
        links.append((f"https://www.songsterr.com{clean_href}", label))
    return links


def _score_result(href: str, label: str, query: ResolvedSongQuery) -> int:
    haystack = f"{href} {label}".lower()
    score = 0
    for token in _search_tokens(query.title):
        if token in haystack:
            score += 3
    for token in _search_tokens(query.artist or ""):
        if token in haystack:
            score += 2
    if "-tab-" in href:
        score += 2
    if any(marker in href for marker in ["-bass-tab-", "-drum-tab-", "-guitar-tab-"]):
        score += 1
    return score


def _search_tokens(value: str) -> list[str]:
    return [token for token in re.sub(r"[^a-z0-9]+", " ", value.lower()).split() if len(token) > 1]


def _visible_text(html_text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(html_text))).strip()


def _merge_bundles(bundles: list[SongsterrTabBundle]) -> Optional[SongsterrTabBundle]:
    if not bundles:
        return None
    first = bundles[0]
    tracks: list[InstrumentTabTrack] = []
    seen: set[tuple[str, int, str]] = set()
    warnings: list[str] = []
    for bundle in bundles:
        warnings.extend(bundle.warnings)
        for track in bundle.tracks:
            key = (track.instrument_family, track.part_id, track.name)
            if key in seen:
                continue
            seen.add(key)
            tracks.append(track)
    return first.model_copy(update={"tracks": tracks, "warnings": warnings})


def _track_from_payload(meta: dict[str, Any], payload: dict[str, Any], *, source_url: str) -> InstrumentTabTrack:
    instrument = str(meta.get("instrument") or payload.get("instrument") or "")
    name = str(meta.get("name") or payload.get("name") or "Track")
    is_bass = bool(meta.get("isBassGuitar"))
    is_drums = bool(meta.get("isDrums")) or int(payload.get("instrumentId") or 0) == 1024
    is_guitar = bool(meta.get("isGuitar"))
    is_piano = bool(meta.get("isPiano")) or "piano" in f"{instrument} {name}".lower() or "keyboard" in f"{instrument} {name}".lower()
    family = _track_family(instrument, name, is_bass=is_bass, is_drums=is_drums, is_guitar=is_guitar, is_piano=is_piano)
    measures = [
        _measure_from_payload(index, measure, expose_string_fret=family in {"bass", "guitar"})
        for index, measure in enumerate(payload.get("measures") or [])
    ]
    note_count = sum(1 for measure in measures for event in measure.events if not event.rest)
    beat_count = sum(len(voice.get("beats") or []) for measure in payload.get("measures") or [] for voice in measure.get("voices") or [])
    return InstrumentTabTrack(
        part_id=int(meta["partId"]),
        name=name,
        instrument=instrument,
        instrument_family=family,
        source_url=source_url,
        tuning=[str(item) for item in meta.get("tuning") or payload.get("tuning") or []],
        difficulty=str(meta["difficulty"]) if meta.get("difficulty") is not None else None,
        is_bass=is_bass,
        is_drums=is_drums,
        is_guitar=is_guitar,
        is_piano=is_piano,
        measures=measures,
        note_count=note_count,
        beat_count=beat_count,
    )


def _measure_from_payload(index: int, measure: dict[str, Any], *, expose_string_fret: bool = True) -> TabMeasure:
    signature = measure.get("signature")
    marker = measure.get("marker", {}).get("text") if isinstance(measure.get("marker"), dict) else None
    events: list[TabEvent] = []
    for voice in measure.get("voices") or []:
        for beat_index, beat in enumerate(voice.get("beats") or []):
            duration = _duration_label(beat.get("duration"), beat.get("type"))
            notes = beat.get("notes") or []
            if not notes:
                events.append(TabEvent(measure_index=index, beat_index=beat_index, duration=duration, rest=bool(beat.get("rest")), raw={}))
            for note in notes:
                events.append(
                    TabEvent(
                        measure_index=index,
                        beat_index=beat_index,
                        duration=duration,
                        rest=bool(note.get("rest") or beat.get("rest")),
                        string=note.get("string") if expose_string_fret else None,
                        fret=note.get("fret") if expose_string_fret else None,
                        tie=bool(note.get("tie")),
                        ghost=bool(note.get("ghost")),
                        raw=note,
                    )
                )
    return TabMeasure(
        index=index,
        marker=str(marker) if marker else None,
        signature=tuple(signature) if isinstance(signature, list) and len(signature) == 2 else None,  # type: ignore[arg-type]
        events=events,
    )


def _duration_label(duration: Any, beat_type: Any) -> str:
    if isinstance(duration, list) and len(duration) == 2:
        return f"{duration[0]}/{duration[1]}"
    if beat_type:
        return f"1/{beat_type}"
    return ""


def _track_family(
    instrument: str,
    name: str,
    *,
    is_bass: bool,
    is_drums: bool,
    is_guitar: bool,
    is_piano: bool,
) -> str:
    text = f"{instrument} {name}".lower()
    if is_bass or "bass" in text:
        return "bass"
    if is_drums or "drum" in text:
        return "drums"
    if is_piano or "piano" in text or "keyboard" in text or "keys" in text:
        return "piano"
    if is_guitar or "guitar" in text:
        return "guitar"
    if "vocal" in text or "voice" in text:
        return "vocal"
    return "other"


def _normalize_instrument(instrument: str) -> str:
    value = instrument.strip().lower()
    aliases = {
        "drum": "drums",
        "keyboard": "piano",
        "keys": "piano",
        "synth": "piano",
        "vocals": "vocal",
    }
    return aliases.get(value, value)
