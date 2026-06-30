"""Clean-architecture tests for HTTP/SSE and artifact boundaries."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

from music_assistant.domain.song_state import Header, RosterItem
from music_assistant.infrastructure.storage.local_store import LocalArtifactStore
from music_assistant.interfaces.api_models import AgentPassEvent, DirectorEvent, sse_data


def test_sse_data_serializes_one_data_event_with_aliases():
    event = AgentPassEvent(
        round=1,
        instrument_id="bass",
        notes_summary="accepted the drums request",
        new_requests=[],
        resolved_requests=[],
    )

    encoded = sse_data(event)

    assert encoded.startswith("data: ")
    assert encoded.endswith("\n\n")
    payload = json.loads(encoded.removeprefix("data: ").strip())
    assert payload["type"] == "agent_pass"
    assert payload["instrument_id"] == "bass"


def test_director_event_contract_matches_existing_stream_payload():
    event = DirectorEvent(
        source="canned",
        header=Header(genre="demo", key="C major", tempo_bpm=120, num_bars=4),
        roster=[RosterItem(id="bass", instrument="electric_bass")],
    )

    payload = event.model_dump(mode="json")

    assert payload["type"] == "director"
    assert payload["source"] == "canned"
    assert payload["roster"][0]["id"] == "bass"


def test_local_artifact_store_keeps_paths_and_urls_outside_api_logic(tmp_path):
    store = LocalArtifactStore(tmp_path)
    job = store.create_job()
    (job.path / "song.mid").write_bytes(b"MThd")

    assert job.path.parent == tmp_path
    assert store.url_for("http://testserver", job.job_id, "song.mid").endswith(
        f"/artifacts/{job.job_id}/song.mid"
    )
    assert store.path_for(job.job_id, "song.mid") == job.path / "song.mid"


def test_local_artifact_store_rejects_traversal(tmp_path):
    store = LocalArtifactStore(tmp_path)
    job = store.create_job()

    assert store.path_for(job.job_id, "../song.mid") is None
    assert store.path_for("../bad", "song.mid") is None


def test_legacy_root_architecture_modules_are_removed():
    assert importlib.util.find_spec("music_assistant.schema") is None
    assert importlib.util.find_spec("music_assistant.api_models") is None
    assert importlib.util.find_spec("music_assistant.artifacts") is None
    assert importlib.util.find_spec("music_assistant.composition") is None
    assert importlib.util.find_spec("music_assistant.rendering") is None
    assert importlib.util.find_spec("music_assistant.reference_analysis") is None


def test_clean_architecture_dependency_direction():
    root = Path(__file__).resolve().parents[1] / "music_assistant"
    rules = {
        "domain": ("music_assistant.infrastructure", "music_assistant.interfaces", "music_assistant.application"),
        "application": ("music_assistant.infrastructure", "music_assistant.interfaces", "fastapi"),
        "infrastructure": ("music_assistant.interfaces", "fastapi"),
    }
    violations = []
    for layer, forbidden_prefixes in rules.items():
        for path in (root / layer).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if any(name == p or name.startswith(f"{p}.") for p in forbidden_prefixes):
                        violations.append((str(path.relative_to(root)), name))

    assert violations == []
