"""Tests for the state schema and reducers."""

from llm_band.state import merge_summaries


def test_merge_summaries_right_wins_on_conflict():
    left = {"drums": "old summary", "bass": "bass summary"}
    right = {"drums": "new summary", "epiano": "epiano summary"}
    result = merge_summaries(left, right)
    assert result["drums"] == "new summary"
    assert result["bass"] == "bass summary"
    assert result["epiano"] == "epiano summary"


def test_merge_summaries_empty_inputs():
    assert merge_summaries({}, {}) == {}
    assert merge_summaries({"a": "x"}, {}) == {"a": "x"}
    assert merge_summaries({}, {"b": "y"}) == {"b": "y"}
