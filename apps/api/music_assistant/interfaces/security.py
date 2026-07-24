"""HTTP access control for the API boundary.

Two independent gates, both off by default so local development and the test
suite need no setup:

* a shared secret on the routes that spend LLM quota;
* an explicit CORS origin allowlist.

Deliberately minimal — there are no user accounts to authenticate, only a
deployed frontend to distinguish from the open internet.
"""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Header, HTTPException

from music_assistant.config import get_settings

API_KEY_HEADER = "X-API-Key"


def _csv(raw: Optional[str]) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Reject callers that don't present the shared secret.

    A no-op while ``API_KEY`` is unset. Guards composition and chat only: those
    burn provider quota, and they are reached through the frontend's server-side
    proxy, which can hold a secret the browser never sees. Audio analysis is
    uploaded straight from the browser — it cannot carry a secret, so it leans
    on the CORS allowlist and the upload size cap instead.
    """
    expected = getattr(get_settings(), "api_key", None)
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def cors_options() -> dict:
    """Kwargs for ``CORSMiddleware``.

    Falls back to the permissive default when nothing is configured. The regex
    exists because preview deployments get a fresh generated hostname each time,
    so they can't be listed one by one.
    """
    settings = get_settings()
    origins = _csv(getattr(settings, "cors_allow_origins", None))
    regex = getattr(settings, "cors_allow_origin_regex", None) or None

    if not origins and not regex:
        return {"allow_origins": ["*"]}

    options: dict = {"allow_origins": origins}
    if regex:
        options["allow_origin_regex"] = regex
    return options
