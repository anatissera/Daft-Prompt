"""Tests for the curated genre idiom library and its prompt injection."""

from __future__ import annotations

import pytest

from music_assistant.music.genre_idioms import IDIOMS, lookup
from music_assistant.band_agent.prompts import skeleton_user_prompt


def test_exact_genre_match_returns_all_roles():
    funk = lookup("funk")
    assert funk is not None
    assert "bass" in funk and "drums" in funk
    assert "ghost" in funk["bass"].lower()


def test_lookup_is_case_insensitive():
    assert lookup("FUNK") == lookup("funk")
    assert lookup("  Funk  ") == lookup("funk")


def test_alias_resolves_to_canonical_genre():
    assert lookup("hard rock") == IDIOMS["rock"]
    assert lookup("rnb") == IDIOMS["soul"]
    assert lookup("bossa") == IDIOMS["bossa nova"]


def test_substring_scan_finds_the_genre_inside_a_longer_prompt():
    assert lookup("80s funk") == IDIOMS["funk"]
    assert lookup("slow jazz ballad") is not None


def test_longer_genre_key_wins_on_a_substring_tie():
    # "bossa nova" must beat a bare "nova" — verified by it resolving to the
    # bossa entry rather than anything else that might substring-match.
    assert lookup("smooth bossa nova groove") == IDIOMS["bossa nova"]


def test_unknown_genre_returns_none():
    assert lookup("polka") is None
    assert lookup("") is None
    assert lookup(None) is None


def test_skeleton_prompt_includes_idioms_for_a_known_genre():
    prompt = skeleton_user_prompt("compose a funk track", {"results": []}, {}, genre="funk")
    assert "GENRE PLAYING IDIOMS" in prompt
    assert "ghost" in prompt.lower()


def test_skeleton_prompt_omits_idioms_for_an_unknown_genre():
    prompt = skeleton_user_prompt("compose a polka", {"results": []}, {}, genre="polka")
    assert "GENRE PLAYING IDIOMS" not in prompt


def test_skeleton_prompt_falls_back_to_style_when_no_genre_passed():
    # No explicit genre → the style string itself is scanned for a known genre.
    prompt = skeleton_user_prompt("a disco banger", {"results": []}, {})
    assert "GENRE PLAYING IDIOMS" in prompt
