"""Tests for the band-agent corpus digest, focused on the Groove/Lakh split.

The Groove index (small, shipped in the image) and the Lakh index (1.6 GB,
bucket-only) are independent. A Groove-only deployment must still get a drum
groove — the digest can't short-circuit on missing Lakh exemplars.
"""

from __future__ import annotations

from music_assistant.band_agent.tools import corpus as corpus_mod
from music_assistant.corpus.retrieve import GroovePattern


def _groove() -> GroovePattern:
    return GroovePattern(
        style="funk", bpm=100.0, type="beat", num_bars=2,
        pattern_by_channel={"36": "x...", "38": "..x."},
    )


def test_groove_survives_when_there_are_no_lakh_exemplars(monkeypatch):
    monkeypatch.setattr(corpus_mod, "retrieve_style_examples", lambda *a, **k: [])
    monkeypatch.setattr(corpus_mod, "retrieve_groove", lambda *a, **k: _groove())

    digest = corpus_mod.retrieve_corpus("funk")

    assert digest["examples"] == []
    assert digest["groove"] is not None
    assert digest["groove"]["style"] == "funk"
    assert digest["groove"]["pattern_by_channel"]  # drives drum synthesis
    # No exemplars means no real tempo prior — must not fabricate one.
    assert digest["median_tempo"] is None


def test_empty_digest_when_neither_corpus_matches(monkeypatch):
    monkeypatch.setattr(corpus_mod, "retrieve_style_examples", lambda *a, **k: [])
    monkeypatch.setattr(corpus_mod, "retrieve_groove", lambda *a, **k: None)

    digest = corpus_mod.retrieve_corpus("polka")

    assert digest["examples"] == []
    assert digest["groove"] is None


def test_blank_query_returns_empty(monkeypatch):
    # Guard rail: a blank query never touches the corpora.
    called = {"style": False, "groove": False}
    monkeypatch.setattr(corpus_mod, "retrieve_style_examples",
                        lambda *a, **k: called.__setitem__("style", True) or [])
    monkeypatch.setattr(corpus_mod, "retrieve_groove",
                        lambda *a, **k: called.__setitem__("groove", True) or None)

    digest = corpus_mod.retrieve_corpus("   ")

    assert digest["groove"] is None
    assert called == {"style": False, "groove": False}
