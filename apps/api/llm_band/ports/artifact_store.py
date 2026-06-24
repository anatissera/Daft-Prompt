"""Artifact storage port."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ArtifactJob:
    job_id: str
    path: Path


class ArtifactStore(Protocol):
    def create_job(self) -> ArtifactJob:
        ...

    def path_for(self, job_id: str, filename: str) -> Path | None:
        ...

    def url_for(self, base_url: str, job_id: str, filename: str) -> str:
        ...
