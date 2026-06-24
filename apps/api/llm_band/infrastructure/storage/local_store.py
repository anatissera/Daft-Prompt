"""Local filesystem artifact storage adapter."""

from __future__ import annotations

import uuid
from pathlib import Path

from llm_band.ports.artifact_store import ArtifactJob


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
        return f"{base_url.rstrip('/')}/artifacts/{job_id}/{filename}"


def _safe_segment(value: str) -> bool:
    return bool(value) and "/" not in value and "\\" not in value and ".." not in value
