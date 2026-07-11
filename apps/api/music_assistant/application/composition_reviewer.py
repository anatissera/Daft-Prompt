"""Final quality review for generated compositions.

This is deliberately separate from the negotiation arbiter. The arbiter closes
pending inter-agent requests; this reviewer checks the finished song against
the user's brief and source evidence before it is returned.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from music_assistant.domain.audio_profile import CompositionBrief
from music_assistant.domain.song_state import RosterItem, Section, SongState


Severity = Literal["high", "medium", "low"]


class CompositionIssue(BaseModel):
    code: str
    severity: Severity
    message: str
    target: str | None = None


class CompositionReview(BaseModel):
    accepted: bool
    issues: list[CompositionIssue] = Field(default_factory=list)
    targeted_revision_requests: list[str] = Field(default_factory=list)
    user_warnings: list[str] = Field(default_factory=list)


class CompositionReviewer:
    def review(self, brief: CompositionBrief, song: SongState) -> CompositionReview:
        issues: list[CompositionIssue] = []
        required = self._required_families(brief)
        present = self._present_families(song)

        for family in sorted(required - present):
            issues.append(CompositionIssue(
                code="missing_required_instrument",
                severity="high",
                message=f"The composition is missing the requested {family} part.",
                target=family,
            ))

        guardrails = brief.style_guardrails
        discouraged = set(guardrails.get("discouraged_families", []))
        explicit = set(guardrails.get("explicit_exceptions", []))
        if "unsupported_synth" in discouraged and "synth" in present and "synth" not in explicit:
            issues.append(CompositionIssue(
                code="unsupported_synth",
                severity="high",
                message="A synth layer is present even though the reference/style evidence does not support it.",
                target="synth",
            ))

        source_salience = self._source_salience(brief)
        if source_salience.get("guitar_led"):
            guitar_notes = self._note_count(song, "guitar")
            piano_notes = self._note_count(song, "piano")
            if guitar_notes == 0:
                issues.append(CompositionIssue(
                    code="guitar_led_reference_missing_guitar",
                    severity="high",
                    message="The reference is guitar-led but the generated song has no playable guitar material.",
                    target="guitar",
                ))
            elif piano_notes > guitar_notes:
                issues.append(CompositionIssue(
                    code="piano_heavy_reference_mismatch",
                    severity="high",
                    message="The generated piano material outweighs the guitar material for a guitar-led reference.",
                    target="piano",
                ))

        if "piano_heavy_balance" in discouraged and self._note_count(song, "piano") > self._note_count(song, "guitar"):
            issues.append(CompositionIssue(
                code="piano_heavy_guardrail",
                severity="high",
                message="Piano dominates an arrangement whose guardrails call for a different instrumental center.",
                target="piano",
            ))

        if brief.fidelity_mode in {"very_similar", "exact_or_as_close_as_possible"}:
            reference_families = self._reference_families(brief)
            for family in sorted(reference_families - present):
                issues.append(CompositionIssue(
                    code="fidelity_family_missing",
                    severity="high",
                    message=f"High-fidelity mode did not retain the source-backed {family} family.",
                    target=family,
                ))

        self._check_form(song, issues)
        self._check_repeated_leads(song, issues)
        self._check_preserved_parts(brief, song, present, issues)

        high = [issue for issue in issues if issue.severity == "high"]
        targeted = [self._revision_request(issue) for issue in high]
        warnings = [issue.message for issue in issues if issue.severity != "high"]
        return CompositionReview(
            accepted=not issues,
            issues=issues,
            targeted_revision_requests=list(dict.fromkeys(targeted)),
            user_warnings=warnings,
        )

    @staticmethod
    def _required_families(brief: CompositionBrief) -> set[str]:
        families = set(brief.instrument_requests)
        families.update(
            str(family)
            for family in brief.style_guardrails.get("expected_families", [])
            if family in {"drums", "bass", "guitar", "piano", "synth"}
        )
        if brief.fidelity_mode in {"very_similar", "exact_or_as_close_as_possible"}:
            families.update(CompositionReviewer._reference_families(brief))
        return families

    @staticmethod
    def _reference_families(brief: CompositionBrief) -> set[str]:
        return {
            str(family)
            for item in brief.reference_instrumentation.values()
            if isinstance(item, dict)
            for family in item.get("families", [])
            if family in {"drums", "bass", "guitar", "piano", "synth"}
        }

    @staticmethod
    def _source_salience(brief: CompositionBrief) -> dict[str, bool]:
        salience: dict[str, bool] = {}
        for item in brief.reference_instrumentation.values():
            if not isinstance(item, dict):
                continue
            value = item.get("salience")
            if isinstance(value, dict):
                for key, enabled in value.items():
                    if enabled:
                        salience[key] = True
        return salience

    @staticmethod
    def _present_families(song: SongState) -> set[str]:
        return {
            family
            for family in {"drums", "bass", "guitar", "piano", "synth"}
            if any(CompositionReviewer._item_matches(item, family) for item in song.roster)
        }

    @staticmethod
    def _item_matches(item: RosterItem, family: str) -> bool:
        text = f"{item.id} {item.instrument} {item.role}".lower()
        aliases = {
            "drums": ("drum", "percussion"),
            "bass": ("bass", "bajo"),
            "guitar": ("guitar", "guitarra"),
            "piano": ("piano", "keyboard", "keys", "rhodes"),
            "synth": ("synth", "pad", "supersaw"),
        }
        return (family == "drums" and item.is_drum) or any(alias in text for alias in aliases[family])

    @staticmethod
    def _note_count(song: SongState, family: str) -> int:
        return sum(
            len(song.parts.get(item.id).notes)
            for item in song.roster
            if CompositionReviewer._item_matches(item, family) and song.parts.get(item.id) is not None
        )

    @staticmethod
    def _check_form(song: SongState, issues: list[CompositionIssue]) -> None:
        sections = sorted(song.header.sections, key=lambda section: section.start_bar)
        if not sections:
            issues.append(CompositionIssue(
                code="missing_form",
                severity="medium",
                message="The generated song has no named section form to guide arrangement changes.",
            ))
            return
        cursor = 0
        for section in sections:
            if section.start_bar != cursor or section.end_bar <= section.start_bar:
                issues.append(CompositionIssue(
                    code="incoherent_form",
                    severity="medium",
                    message="The generated section form contains a gap, overlap, or empty section.",
                ))
                return
            cursor = section.end_bar
        if cursor != song.header.num_bars:
            issues.append(CompositionIssue(
                code="incomplete_form",
                severity="medium",
                message="The generated section form does not cover the full timeline.",
            ))

    @staticmethod
    def _check_repeated_leads(song: SongState, issues: list[CompositionIssue]) -> None:
        for item in song.roster:
            if not CompositionReviewer._item_matches(item, "guitar") or "lead" not in f"{item.id} {item.role} {item.playing_style}".lower():
                continue
            part = song.parts.get(item.id)
            if part is None or len(part.notes) < 8:
                continue
            signatures: dict[tuple[tuple[float, int | None, float], ...], int] = {}
            for bar in range(song.header.num_bars):
                signature = tuple(
                    (round(note.start_beat, 3), note.pitch, round(note.dur, 3))
                    for note in part.notes
                    if note.bar == bar
                )
                if signature:
                    signatures[signature] = signatures.get(signature, 0) + 1
            if signatures and max(signatures.values()) >= max(3, song.header.num_bars // 2):
                issues.append(CompositionIssue(
                    code="lead_one_bar_loop",
                    severity="medium",
                    message=f"The {item.instrument} lead repeats one phrase across too many bars; add section-aware variation.",
                    target=item.id,
                ))

    @staticmethod
    def _check_preserved_parts(
        brief: CompositionBrief,
        song: SongState,
        present: set[str],
        issues: list[CompositionIssue],
    ) -> None:
        for part in brief.playable_parts_to_preserve:
            family = part.instrument_family
            if family and (family not in present or CompositionReviewer._note_count(song, family) == 0):
                issues.append(CompositionIssue(
                    code="preserved_playable_part_missing",
                    severity="high",
                    message=f"The requested source-backed {family} playable part was not preserved in the result.",
                    target=family,
                ))

    @staticmethod
    def _revision_request(issue: CompositionIssue) -> str:
        if issue.target:
            return f"Fix {issue.code} for {issue.target}: {issue.message}"
        return f"Fix {issue.code}: {issue.message}"

