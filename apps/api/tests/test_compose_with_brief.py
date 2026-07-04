from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from music_assistant.application.compose_song import ComposeSong, prompt_from_composition_brief
from music_assistant.canned import canned_song
from music_assistant.domain.audio_profile import CompositionBrief


def test_prompt_from_composition_brief_contains_structured_transfer_fields():
    brief = CompositionBrief(
        brief_id="brief_demo",
        user_request="make it darker",
        global_constraints={"genre": "funk", "tempo_bpm": 112},
        references_used=["song_drums"],
        transfer_policy={"song_drums": ["rhythmic_guidance"]},
        rhythmic_guidance={"song_drums": ["four-on-the-floor funk drums"]},
        forbidden_traits=["do not copy melody"],
        uncertainty_notes=["harmony missing"],
    )

    prompt = prompt_from_composition_brief(brief)

    assert "CompositionBrief" in prompt
    assert "global_constraints" in prompt
    assert "song_drums" in prompt
    assert "four-on-the-floor funk drums" in prompt
    assert "do not copy melody" in prompt


def test_compose_song_accepts_brief_without_breaking_text_prompt():
    calls: list[str] = []

    def negotiator(style: str):
        calls.append(style)
        return canned_song(style)

    compose = ComposeSong(
        llm_configured=lambda: True,
        negotiator=negotiator,
        event_streamer=lambda style: iter(()),
        canned=canned_song,
    )
    brief = CompositionBrief(
        brief_id="brief_demo",
        user_request="use the reference drums",
        references_used=["song_ref"],
        transfer_policy={"song_ref": ["rhythmic_guidance"]},
    )

    song, source = compose.compose(brief)
    text_song, text_source = compose.compose("compose a slow blues")

    assert source == "director"
    assert text_source == "director"
    assert "CompositionBrief" in calls[0]
    assert calls[1] == "compose a slow blues"
    assert song.request == calls[0]
    assert text_song.request == "compose a slow blues"


def test_compose_stream_accepts_brief():
    calls: list[str] = []

    def streamer(style: str) -> Iterator[tuple[dict[str, Any], Any]]:
        calls.append(style)
        song = canned_song(style)
        yield {"type": "director"}, song

    compose = ComposeSong(
        llm_configured=lambda: True,
        negotiator=canned_song,
        event_streamer=streamer,
        canned=canned_song,
    )
    brief = CompositionBrief(brief_id="brief_stream", user_request="compose from brief")

    events = list(compose.stream(brief))

    assert "CompositionBrief" in calls[0]
    assert events[-1][2] == "director"
