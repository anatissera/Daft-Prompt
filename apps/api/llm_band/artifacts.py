"""Artifact storage boundary.

The current implementation stores generated files on local disk. Keeping that
behind this small adapter lets production swap in object storage later without
teaching API or composition code about storage paths.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactJob:
    job_id: str
    path: Path


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
