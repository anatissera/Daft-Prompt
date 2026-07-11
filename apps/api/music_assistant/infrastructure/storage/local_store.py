"""Local filesystem artifact storage adapter."""

from __future__ import annotations

import uuid
from pathlib import Path

from music_assistant.ports.artifact_store import ArtifactJob


class LocalArtifactStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create_job(self) -> ArtifactJob:
        job_id = uuid.uuid4().hex[:12]
        path = self.root / job_id
        path.mkdir(parents=True, exist_ok=True)
        return ArtifactJob(job_id=job_id, path=path)

    def path_for(self, job_id: str, filename: str) -> Path | None:
        if not _safe_segment(job_id) or not _safe_segment(filename):
            return None
        path = self.root / job_id / filename
        try:
            path.relative_to(self.root)
        except ValueError:
            return None
        return path

    def url_for(self, base_url: str, job_id: str, filename: str) -> str:
        # Relative URL, ignoring the backend-visible base. The backend only
        # ever sees requests from the Next server-side proxy, so an absolute
        # base would be "http://localhost:8000/…" — which breaks for any
        # browser NOT on this machine (e.g. Tailscale access). Relative URLs
        # resolve against the frontend origin and a Next rewrite proxies
        # /artifacts/* to the backend.
        del base_url
        return f"/artifacts/{job_id}/{filename}"


def _safe_segment(value: str) -> bool:
    return bool(value) and "/" not in value and "\\" not in value and ".." not in value
