"""LLM-decided reference transfer intent for composition requests."""

from __future__ import annotations

from pydantic import BaseModel

from music_assistant.domain.audio_profile import ReferenceInstrumentProfile, ReferenceTransferIntent
from music_assistant.ports.llm import ChatModel


class ReferenceTransferIntentResult(BaseModel):
    intent: ReferenceTransferIntent | None = None
    clarification: str | None = None


class BuildReferenceTransferIntent:
    def __init__(self, *, chat_model: ChatModel | None) -> None:
        self.chat_model = chat_model

    def execute(
        self,
        message: str,
        instrument_profiles: dict[str, dict[str, ReferenceInstrumentProfile]],
    ) -> ReferenceTransferIntentResult:
        if self.chat_model is None:
            return ReferenceTransferIntentResult(
                clarification=(
                    "I need the chat model to decide which reference instrument traits to transfer."
                )
            )
        structured = self.chat_model.with_structured_output(ReferenceTransferIntent)
        intent = structured.invoke(_messages(message, instrument_profiles))
        if intent.clarification:
            return ReferenceTransferIntentResult(intent=None, clarification=intent.clarification)
        return ReferenceTransferIntentResult(intent=intent)


def _messages(
    message: str,
    instrument_profiles: dict[str, dict[str, ReferenceInstrumentProfile]],
) -> list[dict[str, str]]:
    available = []
    for reference_id, profiles in instrument_profiles.items():
        entries = []
        for family, profile in sorted(profiles.items()):
            sections = sorted({pack.section_name for pack in profile.musical_memory.note_packs if pack.section_name})
            sections_text = f" sections={', '.join(sections[:6])}" if sections else ""
            note_pack_count = len(profile.musical_memory.note_packs)
            seed_count = len(profile.symbolic_seed)
            note_text = f" note_packs={note_pack_count} symbolic_seed={seed_count}"
            summary = profile.musical_memory.summary or profile.pattern.contour or profile.track_name
            entries.append(f"{family}{sections_text}{note_text}: {summary[:220]}")
        available.append(f"{reference_id}: " + (" | ".join(entries) if entries else "none"))
    return [
        {
            "role": "system",
            "content": (
                "You decide how a user wants to transfer reference song traits into a new composition. "
                "Return ReferenceTransferIntent only. Do not infer transfer mode from fixed keywords; "
                "interpret the full musical request, language, context, and available instruments. "
                "Use transfer_mode similar, literal, timbre_only, pattern_only, energy_only, "
                "avoid_copying, or clarify. Literal means the user wants the same instrument part, "
                "not just the same vibe, and should be selected when the request is for exact reuse. "
                "Only choose literal when a note pack or symbolic seed is available for that instrument; "
                "otherwise use clarify or a non-literal mode with explicit constraints. "
                "For full-song recreation requests, create one item for every available instrument family. "
                "Use literal for available instruments with note_packs or symbolic_seed, and similar or "
                "pattern_only for available instruments without symbolic notes. Do not introduce piano, "
                "keys, guitar, bass, or drums unless that family is listed in the available profiles or "
                "explicitly requested by the user. Do not put operational warnings such as 'piano will be "
                "approximated' in clarification; use clarification only when user input is required. "
                "If a specific section or motif is requested, set "
                "section_name to the matching available section; otherwise leave it null. Ask for "
                "clarification only when the request cannot be mapped to available reference instruments."
            ),
        },
        {
            "role": "system",
            "content": "Available reference instrument profiles:\n" + "\n".join(available),
        },
        {"role": "user", "content": message},
    ]
