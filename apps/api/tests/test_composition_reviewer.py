from __future__ import annotations

from music_assistant.application.composition_reviewer import CompositionReviewer
from music_assistant.application.compose_song import ComposeSong
from music_assistant.domain.audio_profile import CompositionBrief
from music_assistant.domain.song_state import Header, Note, Part, RosterItem, Section, SongState


def _song(*, piano_heavy: bool = False) -> SongState:
    header = Header(
        genre="classic rock",
        key="C major",
        tempo_bpm=120,
        num_bars=4,
        sections=[Section(name="Verse", start_bar=0, end_bar=2), Section(name="Chorus", start_bar=2, end_bar=4)],
    )
    piano = RosterItem(id="piano", instrument="acoustic_piano", role="keys")
    guitar = RosterItem(id="guitar", instrument="electric_guitar_clean", role="rhythm guitar")
    bass = RosterItem(id="bass", instrument="electric_bass", role="bass")
    drums = RosterItem(id="drums", instrument="drum_kit", role="drums", is_drum=True)
    piano_notes = [Note(bar=bar, start_beat=0, pitch=60, dur=1) for bar in range(4)] * (3 if piano_heavy else 1)
    guitar_notes = [Note(bar=0, start_beat=0, pitch=64, dur=1)] if piano_heavy else [Note(bar=bar, start_beat=0, pitch=64, dur=1) for bar in range(4)]
    return SongState(
        request="compose a similar classic rock song",
        header=header,
        roster=[piano, guitar, bass, drums],
        parts={
            "piano": Part(instrument_id="piano", notes=piano_notes),
            "guitar": Part(instrument_id="guitar", notes=guitar_notes),
            "bass": Part(instrument_id="bass", notes=[Note(bar=0, start_beat=0, pitch=40, dur=1)]),
            "drums": Part(instrument_id="drums", notes=[Note(bar=0, start_beat=0, pitch=36, dur=0.25)]),
        },
    )


def _brief() -> CompositionBrief:
    return CompositionBrief(
        brief_id="brief_fixture",
        user_request="compose a very similar guitar-led classic rock song",
        fidelity_mode="very_similar",
        reference_instrumentation={
            "song_fixture": {
                "families": ["guitar", "bass", "drums"],
                "salience": {"guitar_led": True},
            }
        },
        style_guardrails={
            "expected_families": ["guitar", "bass", "drums"],
            "discouraged_families": ["piano_heavy_balance", "unsupported_synth"],
        },
    )


def test_reviewer_catches_piano_heavy_guitar_led_output():
    review = CompositionReviewer().review(_brief(), _song(piano_heavy=True))

    assert review.accepted is False
    assert any(issue.code == "piano_heavy_reference_mismatch" for issue in review.issues)
    assert any("piano" in request.lower() for request in review.targeted_revision_requests)


def test_compose_song_allows_one_bounded_targeted_review_revision():
    calls: list[str] = []
    good = _song(piano_heavy=False).model_copy(update={
        "roster": [item for item in _song(piano_heavy=False).roster if item.id != "piano"],
        "parts": {key: value for key, value in _song(piano_heavy=False).parts.items() if key != "piano"},
    })
    bad = _song(piano_heavy=True)

    def negotiator(prompt: str) -> SongState:
        calls.append(prompt)
        return good if "CompositionReviewer" in prompt else bad

    service = ComposeSong(
        llm_configured=lambda: True,
        negotiator=negotiator,
        event_streamer=lambda _prompt: iter(()),
        canned=lambda _style: bad,
        reviewer=CompositionReviewer(),
    )

    result, source = service.compose(_brief())

    assert source == "director"
    assert len(calls) == 2
    assert service.last_review is not None
    assert service.last_review.accepted is True
    assert result.errors == []

