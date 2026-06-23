"""API architecture tests: keep HTTP/SSE thin and artifact rendering isolated."""

from __future__ import annotations

import json

from llm_band.api_models import AgentPassEvent, DirectorEvent, sse_data
from llm_band.artifacts import LocalArtifactStore
from llm_band.schema import Header, RosterItem


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
