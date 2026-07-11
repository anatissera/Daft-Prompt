"""General music Q&A grounded in a web search.

Lives in band_agent (not application/) because it calls the LLM directly —
the clean-architecture rule forbids application/ → infrastructure imports.
`chat_music` delegates here and only wraps the result in a ChatResponse.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from music_assistant.infrastructure.llm import make_llm

from . import search_web
from .style_research import fetch_style_excerpts

log = logging.getLogger(__name__)


class _WebAnswer(BaseModel):
    answer: str


def answer_from_websearch(message: str) -> str | None:
    """Return a grounded answer with sources, or None when the web gave us
    nothing to stand on. Never raises."""
    try:
        hits = search_web(message, decorate=False)
        if not hits:
            return None
        excerpts = fetch_style_excerpts(hits)
        context = {
            "question": message,
            "results": [{"title": h.get("title"), "site": h.get("site")} for h in hits[:6]],
            "excerpts": excerpts,
        }
        prompt = (
            "You answer music questions using ONLY the web evidence below. "
            "Reply in the user's language, in 1-4 sentences. If the evidence "
            "is thin or conflicting, say so explicitly instead of guessing. "
            "Do not invent facts, dates, credits or genres. Return ONLY the "
            "structured object via the tool — no prose outside it.\n\n"
            f"{json.dumps(context, ensure_ascii=False)}"
        )
        answer = ""
        try:
            llm = make_llm(role="director").with_structured_output(_WebAnswer)
            # The parse occasionally returns None on minimax-m3 (same flake
            # the skeleton retries around); a second attempt is cheap.
            for _ in range(2):
                result = llm.invoke(prompt)
                if isinstance(result, _WebAnswer) and result.answer.strip():
                    answer = result.answer.strip()
                    break
        except Exception:
            answer = ""
        if not answer:
            titles = "; ".join(h.get("title", "") for h in hits[:3])
            answer = (
                "No pude sintetizar una respuesta confiable, pero esto es lo "
                f"que encontré: {titles}"
            )
        sources = sorted({h.get("site", "") for h in hits[:4] if h.get("site")})
        if sources:
            answer += f"\n(fuentes: {', '.join(sources)})"
        return answer
    except Exception as exc:
        log.info("web answer failed: %s: %s", type(exc).__name__, exc)
        return None
