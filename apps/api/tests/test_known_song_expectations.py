"""Metadata-only known-song expectations for smoke-test interpretation.

These tests intentionally do not store, download, or analyze commercial audio.
They only document accepted interpretation families for manual/local smoke runs.
"""

from __future__ import annotations


KNOWN_SONG_EXPECTATIONS = {
    "blinding_lights": {
        "accepted_tempo_bpm": [86, 171],
        "accepted_key_families": ["F minor", "F dorian"],
        "notes": "86 BPM is half-time for the commonly listed ~171 BPM tempo.",
    },
    "every_breath_you_take": {
        "accepted_tempo_bpm": [117],
        "accepted_key_families": ["Db major", "C# major", "A major tuned"],
        "notes": "Known metadata varies by source and tuning; key should be treated as ambiguous.",
    },
}


def _tempo_matches_family(detected_bpm: float, accepted_bpm: list[int], tolerance: float = 0.04) -> bool:
    return any(abs(detected_bpm - bpm) / bpm <= tolerance for bpm in accepted_bpm)


def _key_matches_family(detected_key: str, accepted_families: list[str]) -> bool:
    normalized = detected_key.lower()
    return any(family.lower() in normalized for family in accepted_families)


def test_blinding_lights_accepts_half_time_or_double_time_tempo_family():
    expectation = KNOWN_SONG_EXPECTATIONS["blinding_lights"]

    assert _tempo_matches_family(86.0, expectation["accepted_tempo_bpm"])
    assert _tempo_matches_family(171.0, expectation["accepted_tempo_bpm"])
    assert not _tempo_matches_family(120.0, expectation["accepted_tempo_bpm"])


def test_known_song_key_expectations_allow_ambiguous_metadata_families():
    expectation = KNOWN_SONG_EXPECTATIONS["every_breath_you_take"]

    assert _key_matches_family("C# major", expectation["accepted_key_families"])
    assert _key_matches_family("Db major", expectation["accepted_key_families"])
    assert not _key_matches_family("F minor", expectation["accepted_key_families"])
