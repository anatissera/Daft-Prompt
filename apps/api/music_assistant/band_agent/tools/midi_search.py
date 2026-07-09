"""Search + download MIDI files from Bitmidi.

Bitmidi's search page is a bare HTML directory: `bitmidi.com/search?q=<query>`
returns a list of anchors that link to song pages, and each song page has a
direct `.mid` download link. Both scrapers use only the standard library so
no new deps are required.

Legal note: Bitmidi hosts user-contributed transcriptions of copyrighted
songs. Fine for local experimentation and prototyping; NOT safe to embed in
a distributed product without licensing. Callers should surface this to the
user (the router prompt makes that plain).
"""

from __future__ import annotations

import html
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen


_BASE = "https://bitmidi.com"
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# The search page emits <a class="..." href="/some-song-mid">Some Song</a>
# pointing to each song's page. The trailing "-mid" is Bitmidi's convention
# for song pages.
_RESULT_ANCHOR = re.compile(
    r'<a[^>]+href="(/[^"]+-mid)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
# Each song page has one download link like /uploads/foobar.mid — we grab
# the first occurrence.
_DOWNLOAD_LINK = re.compile(r'href="([^"]+\.mid)"', re.IGNORECASE)


@dataclass
class MidiHit:
    title: str
    song_url: str  # bitmidi song page (has metadata + download link)


def search_midi_online(query: str, *, limit: int = 5) -> list[MidiHit]:
    """Return up to `limit` Bitmidi search hits for `query`.

    Empty list on network error or rate limit — callers should degrade
    gracefully (e.g. fall back to standard composition).
    """
    q = (query or "").strip()
    if not q:
        return []
    url = f"{_BASE}/search?q={quote_plus(q)}"
    page = _fetch_text(url)
    if page is None:
        return []
    hits: list[MidiHit] = []
    seen: set[str] = set()
    for href, inner in _RESULT_ANCHOR.findall(page):
        song_url = urljoin(_BASE, href)
        if song_url in seen:
            continue
        seen.add(song_url)
        title = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        if not title:
            continue
        hits.append(MidiHit(title=title, song_url=song_url))
        if len(hits) >= limit:
            break
    return hits


def download_midi(hit: MidiHit, *, dest_dir: str | Path | None = None) -> Path | None:
    """Fetch the .mid pointed at by `hit`. Returns the local path (in a
    temp dir by default) or None if download failed / no link on the page."""
    page = _fetch_text(hit.song_url)
    if page is None:
        return None
    m = _DOWNLOAD_LINK.search(page)
    if not m:
        return None
    mid_url = urljoin(_BASE, m.group(1))
    data = _fetch_bytes(mid_url)
    if data is None:
        return None
    root = Path(dest_dir) if dest_dir else Path(tempfile.gettempdir()) / "band_agent_midis"
    root.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9-_]+", "_", hit.title.lower()).strip("_")[:60] or "song"
    path = root / f"{safe}.mid"
    path.write_bytes(data)
    return path


def _fetch_text(url: str, *, timeout: float = 10.0) -> str | None:
    data = _fetch_bytes(url, timeout=timeout)
    if data is None:
        return None
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return None


def _fetch_bytes(url: str, *, timeout: float = 15.0) -> bytes | None:
    req = Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.read(20_000_000)  # cap: no MIDI is 20MB
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None
