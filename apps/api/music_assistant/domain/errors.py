"""Domain-level control-flow signals shared across layers."""

from __future__ import annotations


class OffTopicRequest(Exception):
    """Raised when the director judges a request to be outside the assistant's
    scope (not a music-composition task). Carries a user-facing refusal message
    so callers can surface it without composing anything."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
