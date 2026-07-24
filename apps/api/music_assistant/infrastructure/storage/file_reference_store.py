"""Filesystem-backed reference-profile store.

Persists each ``ReferenceProfile`` as one JSON file so analysed references
survive process restarts and are visible across instances — unlike the
in-memory store, whose dict is lost whenever the container recycles. On Cloud
Run the directory is a mounted GCS bucket, so a reference stays available even
after the service scales to zero.

The profile is a Pydantic model, so serialization is just ``model_dump_json`` /
``model_validate_json`` — no schema mapping, no database.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from music_assistant.domain.audio_profile import ReferenceProfile


def _safe_id(reference_id: str) -> bool:
    return bool(reference_id) and "/" not in reference_id and "\\" not in reference_id and ".." not in reference_id


class FileReferenceStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, reference_id: str) -> Optional[Path]:
        if not _safe_id(reference_id):
            return None
        return self.root / f"{reference_id}.json"

    def save(self, profile: ReferenceProfile) -> None:
        path = self._path_for(profile.reference_id)
        if path is None:
            raise ValueError(f"unsafe reference_id: {profile.reference_id!r}")
        # Write to a temp file in the same directory, then atomically replace,
        # so a reader never observes a half-written profile. On GCS FUSE the
        # rename is a copy+delete, still safe for our write-once profiles.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.root, delete=False, suffix=".tmp"
        ) as handle:
            handle.write(profile.model_dump_json())
            tmp = Path(handle.name)
        tmp.replace(path)

    def get(self, reference_id: str) -> Optional[ReferenceProfile]:
        path = self._path_for(reference_id)
        if path is None or not path.exists():
            return None
        try:
            return ReferenceProfile.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            # A corrupt or partially written file behaves as "not found" rather
            # than taking down the request; the caller surfaces a clean 404.
            return None
