from music_assistant.application.compose_song import ComposeSong
from music_assistant.canned import canned_song
from music_assistant.domain.song_state import Header, Part


def test_revision_boundary_accepts_only_target_part_and_preserves_song_identity():
    original = canned_song("rock")
    target_id = next(iter(original.parts))
    peer_id = next(part_id for part_id in original.parts if part_id != target_id)
    revised_target = original.parts[target_id].model_copy(update={"notes_summary": "targeted revision"})

    def destructive_reviser(song, _instruction, _instrument_id):
        return song.model_copy(
            update={
                "request": "replacement song",
                "header": Header(genre="unrelated", key="C major", tempo_bpm=60, num_bars=1),
                "roster": song.roster[:1],
                "parts": {target_id: revised_target},
                "negotiation_requests": [],
                "errors": ["unrelated mutation"],
            }
        )

    service = ComposeSong(
        llm_configured=lambda: True,
        negotiator=lambda _prompt: original,
        event_streamer=lambda _prompt: iter(()),
        canned=canned_song,
        instrument_reviser=destructive_reviser,
    )

    revised, _source = service.revise_instrument(original, "change one part", target_id)

    assert revised.header == original.header
    assert revised.request == original.request
    assert revised.roster == original.roster
    assert revised.negotiation_requests == original.negotiation_requests
    assert revised.errors == original.errors
    assert revised.parts[peer_id] == original.parts[peer_id]
    assert revised.parts[target_id].notes_summary == "targeted revision"
