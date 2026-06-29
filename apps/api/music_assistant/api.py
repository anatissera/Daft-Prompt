"""Compatibility entrypoint for `uvicorn music_assistant.api:app`."""

from music_assistant.interfaces.api import app

__all__ = ["app"]
