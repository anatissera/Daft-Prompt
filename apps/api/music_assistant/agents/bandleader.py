"""Bandleader review for band-like composition passes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..domain.song_state import SongState


class BandleaderRevisionRequest(BaseModel):
    instrument_id: str = Field(description="existing roster id to revise")
    instruction: str = Field(description="concise instruction for that player")
    reason: str = Field(default="", description="short musical reason")


class BandleaderReviewOutput(BaseModel):
    revision_requests: list[BandleaderRevisionRequest] = Field(default_factory=list)


def run_bandleader_review(song: SongState, llm) -> BandleaderReviewOutput:
    """Ask a producer/bandleader whether a guitar should rehearse one more pass.

    The reviewer cannot create parts or change state directly. It only names an
    existing instrument id and an instruction; the normal instrument revision
    agent performs any actual rewrite.
    """
    structured = llm.with_structured_output(BandleaderReviewOutput)
    roster = "\n".join(
        f"- {item.id}: {item.instrument}, role={item.role}, style={item.playing_style}"
        for item in song.roster
    )
    summaries = "\n".join(
        f"- {part_id}: {part.notes_summary or '(no summary)'}"
        for part_id, part in song.parts.items()
    )
    messages = [
        (
            "system",
            (
                "You are the band's producer after a first rehearsal take. Review only for "
                "band-arrangement issues. Request at most one revision, and only if a guitar "
                "part is likely weak: rhythm guitar should use riffs/power chords/palm muting, "
                "lead guitar should use short motifs/fills and leave space. Do not request "
                "new instruments. Do not revise drums or bass unless the user explicitly asked."
            ),
        ),
        (
            "human",
            (
                f"Song: {song.header.genre}, {song.header.key}, {song.header.tempo_bpm} BPM.\n"
                f"Roster:\n{roster}\n\nPart summaries:\n{summaries}"
            ),
        ),
    ]
    return structured.invoke(messages)
