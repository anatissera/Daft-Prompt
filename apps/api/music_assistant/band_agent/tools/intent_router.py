"""LLM fallback router for chat intents.

The regex router in `application.chat_music` handles the unambiguous cases
(explicit compose verbs, edit verbs over a previous song, question shape +
music-topic keyword) for free and deterministically. Everything that used to
fall through to the "default: compose" branch — e.g. "quién es Freddy
Mercury?" — lands here instead, where a small LLM call decides.

Lives in band_agent (not application/) because it calls the LLM directly —
the clean-architecture rule forbids application/ → infrastructure imports.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from music_assistant.infrastructure.llm import make_llm

log = logging.getLogger(__name__)


class _RoutedIntent(BaseModel):
    intent: Literal["compose", "song_question", "edit_song", "clarify"]


_PROMPT = """You route a user message inside a music-composition studio app.
Pick exactly ONE intent:

- compose: the user wants a NEW piece of music. Bare genre/style/mood
  descriptions count ("rock", "algo tranguilo con guitarras", "like Daft
  Punk"). When in doubt between compose and clarify, prefer compose.
- song_question: the user asks ANY question about music — artists, bands,
  people ("quién es Freddy Mercury"), songs, genres, chords, history,
  theory. Questions get answered, never orchestrated.
- edit_song: the user wants to MODIFY the song they already generated
  (change/replace/remove instruments, tempo, pitch…). {edit_hint}
- clarify: the message is empty of musical content and not a question
  ("hola", "gracias", "asdf").

Return ONLY the structured object via the tool — no prose outside it.

User message: {message!r}"""


def route_intent(message: str, *, has_previous: bool) -> str | None:
    """Classify an ambiguous chat message. Returns None when the LLM is
    unavailable or keeps failing — callers fall back to their old default.
    Never raises."""
    edit_hint = (
        "There IS a previous song in this session."
        if has_previous
        else "There is NO previous song — do not pick edit_song."
    )
    try:
        llm = make_llm(role="director").with_structured_output(_RoutedIntent)
        prompt = _PROMPT.format(edit_hint=edit_hint, message=message)
        for _ in range(2):
            result = llm.invoke(prompt)
            if isinstance(result, _RoutedIntent):
                intent = result.intent
                if intent == "edit_song" and not has_previous:
                    intent = "compose"
                log.info("llm intent router: %r -> %s", message[:60], intent)
                return intent
    except Exception as exc:
        log.info("llm intent router unavailable: %s: %s", type(exc).__name__, exc)
    return None
