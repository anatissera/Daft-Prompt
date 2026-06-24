"""Compatibility entrypoint for `uvicorn llm_band.api:app`."""

from llm_band.interfaces.api import app

__all__ = ["app"]
