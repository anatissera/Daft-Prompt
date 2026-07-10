import json
from pathlib import Path

from music_assistant.infrastructure.web_research.entity_resolution import resolve_song_entity


CASES = Path(__file__).parents[1] / "benchmarks" / "famous_song_lookup.json"


def test_famous_song_benchmark_has_required_size_and_edge_case_coverage():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    labels = {case["case"] for case in cases}

    assert 30 <= len(cases) <= 50
    assert {"straightforward", "accented", "ambiguous-title", "featured", "multiple-primary", "remix", "live", "non-english", "punctuation"}.issubset(labels)
    assert {"Get Lucky", "Smells Like Teen Spirit", "I Kissed a Girl", "Adiós", "SICKO MODE"}.issubset({case["title"] for case in cases})


def test_every_benchmark_query_resolves_a_title_and_expected_credit_shape():
    for case in json.loads(CASES.read_text(encoding="utf-8")):
        resolved = resolve_song_entity(case["query"])
        assert resolved.title
        assert resolved.primary_artists, case["query"]
        if case.get("featured"):
            assert resolved.featured_artists, case["query"]
        if case.get("version"):
            assert resolved.version, case["query"]
