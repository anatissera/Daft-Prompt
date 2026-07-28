"""Root logging configuration.

Uvicorn configures only its own loggers (``uvicorn``, ``uvicorn.access``), and
Python's root logger defaults to WARNING with no handler attached. That
combination silently swallowed every ``_log.info`` in the pipeline — including
the per-stage TIMING lines — so a compose that took 460s in production left no
trace of where the time went. Warnings still surfaced via ``logging.lastResort``,
which is why failures were visible but slowness was not.

Configuring the root logger here is what makes those lines reach the container's
stderr, and therefore Cloud Logging.
"""

from __future__ import annotations

import logging
import sys

_DEFAULT_LEVEL = logging.INFO

_handler: logging.Handler | None = None


def configure_logging(level: str | None = None) -> None:
    """Send root-logger records to stderr at ``level`` (default INFO).

    Idempotent in the way that matters: the handler is attached once, but the
    level is re-applied on every call so tests can turn the volume down again.
    """
    global _handler

    resolved = getattr(logging, (level or "").strip().upper(), _DEFAULT_LEVEL)
    if not isinstance(resolved, int):  # e.g. level="WARN0" resolving to a module attr
        resolved = _DEFAULT_LEVEL

    root = logging.getLogger()
    root.setLevel(resolved)

    if _handler is None:
        _handler = logging.StreamHandler(sys.stderr)
        _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(_handler)
