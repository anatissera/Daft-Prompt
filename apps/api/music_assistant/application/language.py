"""Small language helpers for deterministic conversational fallbacks."""

from __future__ import annotations

import re


_SPANISH_MARKERS = re.compile(
    r"\b(?:qué|que|cuál|cual|cómo|como|dónde|donde|por qué|porque|"
    r"acorde|acordes|progresión|progresion|armonía|armonia|tonalidad|"
    r"estructura|sección|seccion|estrofa|coro|ritmo|batería|bateria|"
    r"bajo|guitarra|piano|analiza|compon[eé]|hac[eé]|gener[aá])\b",
    re.IGNORECASE,
)


def is_spanish(text: str) -> bool:
    """Return whether a conversational turn is more likely Spanish than English.

    This is deliberately conservative: a false negative merely keeps the
    established English fallback, while a false positive makes an otherwise
    English turn unexpectedly switch language.
    """

    return bool(_SPANISH_MARKERS.search(text) or re.search(r"[áéíóúñ¿¡]", text, re.IGNORECASE))
