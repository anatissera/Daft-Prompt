"""Pure-function tests for progression skills."""

from __future__ import annotations

from llm_band.domain.song_state import Section
from llm_band.skills.progression import suggest_chord_progression, suggest_form


def test_progression_one_span_per_bar():
    prog = suggest_chord_progression("C major", "happy", 4)
    assert [s.bar for s in prog] == [0, 1, 2, 3]
    assert all(s.chord for s in prog)


def test_progression_starts_on_tonic_in_major():
    prog = suggest_chord_progression("C major", "happy", 4)
    assert prog[0].chord == "C"


def test_progression_starts_on_tonic_in_minor():
    prog = suggest_chord_progression("A minor", "melancholic", 4)
    assert prog[0].chord == "Am"


def test_progression_is_deterministic():
    a = suggest_chord_progression("F major", "mellow", 8)
    b = suggest_chord_progression("F major", "mellow", 8)
    assert [s.chord for s in a] == [s.chord for s in b]


def test_progression_unknown_mood_falls_back():
    prog = suggest_chord_progression("C major", "alien-mood", 4)
    assert len(prog) == 4 and prog[0].chord == "C"


def test_progression_aligns_to_sections():
    sections = [
        Section(name="verse", start_bar=0, end_bar=4),
        Section(name="chorus", start_bar=4, end_bar=8),
    ]
    prog = suggest_chord_progression("C major", "happy", 8, sections)
    # both sections restart the template, so bar 0 and bar 4 share the same chord
    assert prog[0].chord == prog[4].chord
    assert len(prog) == 8


def test_progression_zero_bars_is_empty():
    assert suggest_chord_progression("C major", "happy", 0) == []


def test_suggest_form_covers_all_bars_exactly():
    form = suggest_form("pop", 16)
    assert form[0].start_bar == 0
    assert form[-1].end_bar == 16
    for a, b in zip(form, form[1:]):
        assert a.end_bar == b.start_bar


def test_suggest_form_truncates_template_when_song_is_short():
    form = suggest_form("pop", 3)
    assert len(form) == 3
    assert form[-1].end_bar == 3


def test_suggest_form_unknown_genre_uses_default():
    form = suggest_form("klezmer-trap", 12)
    assert form and form[-1].end_bar == 12


def test_suggest_form_zero_bars_is_empty():
    assert suggest_form("pop", 0) == []
