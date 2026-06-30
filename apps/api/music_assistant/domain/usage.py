"""Per-request LLM token usage tracking.

Cross-cutting observability primitive: the application layer scopes a
`UsageTracker` to a request, the infrastructure layer feeds it raw usage
metadata from each LLM call. Lives in `domain` so both layers can depend
on it without breaking the layered import rules.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class UsageTracker:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def add(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        self.input_tokens += int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
        self.output_tokens += int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
        self.total_tokens += int(usage.get("total_tokens", 0) or 0)
        self.calls += 1


USAGE_TRACKER: ContextVar[Optional[UsageTracker]] = ContextVar("usage_tracker", default=None)
