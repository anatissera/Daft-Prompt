"""Progression and form skills used by the director.

`suggest_chord_progression` resolves Roman-numeral templates from `_tables` into
concrete chord symbols in the requested key and distributes them over `num_bars`
following the section map. `suggest_form` returns a Section list scaled to fit
`num_bars` for a given genre family.

Both are intentionally deterministic — pick by `(mood, mode)` hash so the same
request returns the same progression across runs, which keeps demos and tests
reproducible.
"""

from __future__ import annotations

from functools import lru_cache

from ..domain.song_state import ChordSpan, Section
from ..music.theory import _split_key
from . import _tables


@lru_cache(maxsize=256)
def _roman_to_symbol(roman: str, key: str) -> str:
    from music21 import roman as m21roman, key as m21key

    tonic, mode = _split_key(key)
    try:
        rn = m21roman.RomanNumeral(roman, m21key.Key(tonic, mode))
    except Exception:
        return roman
    root = rn.root().name.replace("-", "b")
    if rn.isDiminishedTriad():
        suffix = "dim"
    elif rn.isAugmentedTriad():
        suffix = "aug"
    elif rn.isMinorTriad():
        suffix = "m"
    else:
        suffix = ""
    return root + suffix


def _pick_template(mood: str, mode: str) -> list[str]:
    table = _tables.PROGRESSIONS_MAJOR if mode == "major" else _tables.PROGRESSIONS_MINOR
    options = table.get(mood.lower().strip(), table["default"])
    return options[hash((mood, mode)) % len(options)]


def suggest_chord_progression(
    key: str,
    mood: str,
    num_bars: int,
    sections: list[Section] | None = None,
) -> list[ChordSpan]:
    """Return one ChordSpan per bar, cycling a mood-appropriate template.

    When `sections` is provided, each section restarts the template so chord
    changes align with section boundaries. Otherwise the template tiles the
    whole song. Unknown moods fall back to a sensible default per mode.
    """
    if num_bars <= 0:
        return []
    _, mode = _split_key(key)
    template = _pick_template(mood, mode)
    symbols = [_roman_to_symbol(r, key) for r in template]
    spans: list[ChordSpan] = []
    spans_by_bar: dict[int, str] = {}

    def fill(start: int, end: int) -> None:
        for offset, bar in enumerate(range(start, end)):
            spans_by_bar[bar] = symbols[offset % len(symbols)]

    if sections:
        for s in sections:
            start = max(0, min(s.start_bar, num_bars))
            end = max(start, min(s.end_bar, num_bars))
            fill(start, end)
        for bar in range(num_bars):
            spans_by_bar.setdefault(bar, symbols[bar % len(symbols)])
    else:
        fill(0, num_bars)

    for bar in range(num_bars):
        spans.append(ChordSpan(bar=bar, chord=spans_by_bar[bar]))
    return spans


def suggest_form(genre: str, num_bars: int) -> list[Section]:
    """Return a list of Sections covering `num_bars` for `genre`.

    Picks a template by family (pop/rock/electronic/ballad → exact match,
    anything else → default), then distributes section lengths evenly with any
    leftover bars going to the last section so the form fills the song exactly.
    """
    if num_bars <= 0:
        return []
    family = genre.lower().strip()
    template = _tables.FORM_TEMPLATES.get(family)
    if template is None:
        for key, tmpl in _tables.FORM_TEMPLATES.items():
            if key in family:
                template = tmpl
                break
    if template is None:
        template = _tables.FORM_TEMPLATES["default"]

    n = min(len(template), num_bars)
    template = template[:n]
    base = num_bars // n
    leftover = num_bars - base * n
    sections: list[Section] = []
    cursor = 0
    for i, name in enumerate(template):
        length = base + (leftover if i == n - 1 else 0)
        end = cursor + length
        sections.append(Section(name=name, start_bar=cursor, end_bar=end))
        cursor = end
    return sections


__all__ = ["suggest_chord_progression", "suggest_form"]
