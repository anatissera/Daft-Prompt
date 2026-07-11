"""Per-run audit traces for the composition pipeline.

One directory per generation under ``apps/api/data/traces/<YYYY-MM-DD>/<run_id>/``.
Each pipeline node writes one JSON file into that directory. The traces are
plain JSON so they can be inspected with ``jq`` or ``less`` after the fact —
the goal is to answer questions like "why did the director pick a violin for a
rock-metal request" by looking at exactly what the director received (system
prompt, retrieved corpus examples, web-research card) and what it decided.

The tracer is always safe to call: any I/O error is swallowed so a broken
filesystem cannot take down a compose run.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_ROOT = APP_ROOT / "data" / "traces"


def _trace_root() -> Path:
    override = os.environ.get("MUSIC_ASSISTANT_TRACE_DIR")
    return Path(override) if override else DEFAULT_TRACE_ROOT


def _short_id() -> str:
    return uuid.uuid4().hex[:12]


def _to_jsonable(value: Any) -> Any:
    """Best-effort conversion of pydantic models, dataclasses, and tuples to
    plain JSON. Falls back to ``repr`` so the tracer never raises on an
    unfamiliar type."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return _to_jsonable(dump())
        except Exception:
            pass
    to_dict = getattr(value, "__dict__", None)
    if isinstance(to_dict, dict):
        return {k: _to_jsonable(v) for k, v in to_dict.items() if not k.startswith("_")}
    try:
        return repr(value)
    except Exception:
        return "<unrepr>"


@dataclass
class RunTrace:
    """Handle for one composition run. Holds a per-run directory and writes
    one JSON file per pipeline node. Instantiate via :func:`open_run`."""

    run_id: str
    directory: Path
    style: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def _write(self, filename: str, payload: dict[str, Any]) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / filename
            path.write_text(json.dumps(_to_jsonable(payload), indent=2, ensure_ascii=False))
        except Exception:
            # Tracing must never break composition.
            pass

    def write_director(
        self,
        *,
        prompt_messages: list[tuple[str, str]],
        corpus_examples: list[Any],
        research: Any,
        output: Any,
    ) -> None:
        self._write(
            "director.json",
            {
                "node": "director",
                "run_id": self.run_id,
                "style": self.style,
                "prompt_messages": [
                    {"role": role, "content": content} for role, content in prompt_messages
                ],
                "corpus_examples": corpus_examples,
                "web_research": research,
                "output": output,
                "written_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def write_meta(self, **extra: Any) -> None:
        self._write(
            "meta.json",
            {
                "run_id": self.run_id,
                "style": self.style,
                "started_at": self.started_at,
                "ended_at": datetime.now(timezone.utc).isoformat(),
                **extra,
            },
        )


def open_run(style: str) -> RunTrace:
    """Allocate a fresh run trace directory. The path is
    ``<trace_root>/<YYYY-MM-DD>/<run_id>/`` — grouped by day so the folder
    stays browsable as usage grows."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = _short_id()
    directory = _trace_root() / day / run_id
    return RunTrace(run_id=run_id, directory=directory, style=style)
