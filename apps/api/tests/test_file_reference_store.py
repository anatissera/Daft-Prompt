"""Tests for the filesystem-backed reference store.

The key property is that a profile written by one store instance is readable by
a fresh instance pointed at the same directory — that is what survives a process
restart in production.
"""

from __future__ import annotations

import pytest

from music_assistant.domain.audio_profile import ReferenceProfile, ReferenceSource
from music_assistant.infrastructure.storage.file_reference_store import FileReferenceStore


def _profile(reference_id: str = "ref_abc123") -> ReferenceProfile:
    return ReferenceProfile(
        reference_id=reference_id,
        source=ReferenceSource(
            reference_id=reference_id, kind="upload", label="song.wav", uri="/tmp/song.wav", authorized=True
        ),
        summary="a slow blues in F minor",
    )


def test_saves_and_reads_back_a_profile(tmp_path):
    store = FileReferenceStore(tmp_path)
    store.save(_profile())

    got = store.get("ref_abc123")

    assert got is not None
    assert got.reference_id == "ref_abc123"
    assert got.summary == "a slow blues in F minor"


def test_a_fresh_store_reads_what_a_previous_one_wrote(tmp_path):
    """This is the whole point: persistence across process restarts."""
    FileReferenceStore(tmp_path).save(_profile())

    reborn = FileReferenceStore(tmp_path)

    assert reborn.get("ref_abc123") is not None


def test_missing_reference_returns_none(tmp_path):
    store = FileReferenceStore(tmp_path)

    assert store.get("ref_does_not_exist") is None


def test_get_rejects_path_traversal(tmp_path):
    store = FileReferenceStore(tmp_path)

    assert store.get("../secret") is None
    assert store.get("a/b") is None


def test_save_rejects_unsafe_id(tmp_path):
    store = FileReferenceStore(tmp_path)

    with pytest.raises(ValueError):
        store.save(_profile("../escape"))


def test_a_corrupt_file_reads_as_missing(tmp_path):
    store = FileReferenceStore(tmp_path)
    (tmp_path / "ref_corrupt.json").write_text("{not valid json", encoding="utf-8")

    assert store.get("ref_corrupt") is None


def test_overwriting_a_profile_keeps_the_latest(tmp_path):
    store = FileReferenceStore(tmp_path)
    store.save(_profile())
    updated = _profile()
    updated.summary = "actually a bossa nova"
    store.save(updated)

    assert store.get("ref_abc123").summary == "actually a bossa nova"


def test_creates_the_directory_if_absent(tmp_path):
    target = tmp_path / "nested" / "refs"
    store = FileReferenceStore(target)
    store.save(_profile())

    assert target.is_dir()
    assert store.get("ref_abc123") is not None
