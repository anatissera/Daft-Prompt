"""`BandSpec` — the planner's structured-output schema.

Kept intentionally close to `SongState` so `compose_band` is a straight-line
materialisation. Two differences:

  - Roster items carry a `patch` literal from the closed vocabulary in
    `domain.patch` (so the planner cannot invent a program number). The
    numeric `midi_program` / `synth_preset` are derived at compose-band time.
  - A per-instrument `notes` list is inlined on each roster entry — the
    planner emits one flat structure instead of a separate `parts` dict.
    `compose_band` splits it back out.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from music_assistant.domain.patch import Patch


class SectionPlan(BaseModel):
    """Defaults on every field: MiniMax M3 sometimes emits partial section slots
    (e.g. `{"$text": "medium"}` — the energy value hoisted to the parent). We
    don't want a chatty planner blowing up the entire skeleton over an aux
    field. Sections are cosmetic downstream anyway."""

    name: str = "section"
    start_bar: int = Field(default=0, ge=0)
    end_bar: int = Field(default=0, ge=0)
    energy: Literal["low", "medium", "high"] = "medium"


class ChordSpanPlan(BaseModel):
    bar: int = Field(default=0, ge=0)
    chord: str = "C"


class NotePlan(BaseModel):
    """One note or rest. Field bounds intentionally loose so a chatty LLM can't
    fail a whole fill on one out-of-range value. `compose_band` clamps `dur`
    to a minimum audible length so a 0-duration note becomes a short click
    rather than silently dropping the fill via a 64-validation-error cascade
    (seen with MiniMax M3, which loves emitting dur:0)."""

    bar: int = Field(default=0, ge=0)
    start_beat: float = Field(default=0.0, ge=0.0)
    pitch: Optional[int] = Field(default=None, ge=0, le=127)
    dur: float = Field(default=1.0, ge=0.0)
    velocity: int = Field(default=96, ge=1, le=127)


class InstrumentPlan(BaseModel):
    """Legacy one-shot schema: instrument declaration + inlined notes.

    Still used by `compose_band` when we merge a `BandSkeleton` with per-
    instrument `InstrumentFill`s (see `BandSpec.from_skeleton_and_fills`).
    """

    id: str
    instrument: str
    patch: Patch
    role: str = ""
    is_drum: bool = False
    playing_style: str = ""
    onset_grid: str = ""
    max_notes_per_bar: int = 0
    notes: list[NotePlan] = Field(default_factory=list)


class BandSpec(BaseModel):
    """Fully-specified plan (skeleton + notes)."""

    genre: str
    rhythmic_feel: str = ""
    arrangement_plan: str = ""
    key: str = "C major"
    tempo_bpm: float = Field(default=120.0, gt=20.0, lt=300.0)
    time_signature_numerator: int = Field(default=4, ge=1, le=12)
    time_signature_denominator: int = Field(default=4, ge=1, le=16)
    num_bars: int = Field(default=16, ge=4, le=128)
    sections: list[SectionPlan] = Field(default_factory=list)
    chord_progression: list[ChordSpanPlan] = Field(default_factory=list)
    instruments: list[InstrumentPlan] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Split schemas: skeleton + per-instrument fills. Used by the parallel plan
# pipeline. Each is intentionally small so structured-output stays reliable
# on the local llama-server (which flakes on very large JSON outputs).
# --------------------------------------------------------------------------


class IntentDecision(BaseModel):
    """Small classifier output that steers the pipeline router.

    `replicate` means the user is asking to reproduce a specific existing
    song they name explicitly (title and/or artist). `compose` means
    everything else — genre/style descriptions, mood requests, ambiguous
    "in the style of X" phrasing, or bare directives.
    """

    intent: Literal["replicate", "compose"]
    target: Optional[str] = None  # "<artist> <title>" search query when replicate


class InstrumentDecl(BaseModel):
    """One instrument in the roster, no notes."""

    id: str
    instrument: str
    patch: Patch
    role: str = ""
    is_drum: bool = False
    playing_style: str = ""
    # The instrument's one-bar rhythmic cell as a 16th-note grid: one char
    # per 16th ("x" = onset, "." = rest; 16 chars for 4/4). This is DATA,
    # not prose — genre rhythms like dembow or habanera are exact onset
    # grids, and prose descriptions kept getting lost between the director
    # and the (smaller) fill models. A deterministic validator snaps or
    # drops fill notes that land off this grid. Empty = free phrasing
    # (director grants it to leads/melodies).
    onset_grid: str = ""
    # Hard density budget per bar; 0 = unlimited. Deterministically
    # enforced after fills — "sparse" as a number instead of an adjective.
    max_notes_per_bar: int = Field(default=0, ge=0, le=64)


class BandSkeleton(BaseModel):
    """Header + roster + harmonic plan, WITHOUT per-instrument notes.

    Emitted by the first (skeleton) LLM call. Small enough that the local
    llama-server returns it quickly and reliably even for structured output.

    Field order is deliberate: `style_summary` → `canonical_instruments` →
    `rhythmic_feel` come BEFORE `instruments`, so a structured-output LLM
    (which generates JSON in schema order) commits to a style analysis and
    an idiomatic instrument palette before it writes the roster. This
    autoregressive conditioning is what keeps a dubstep request from getting
    a jazz combo — the roster must be drawn from the already-emitted
    canonical list.
    """

    genre: str
    # 2-4 sentences naming the style/artist's signature sound, grounded in
    # the research excerpts when present: subgenre, era, production hallmarks.
    style_summary: str = ""
    # The 5-10 instruments that are IDIOMATIC for this style — the closed
    # palette the roster below must be drawn from.
    canonical_instruments: list[str] = Field(default_factory=list)
    # Director's commitment to the concrete rhythmic idiom of the requested
    # style: kick/snare placement, subdivision, bass articulation, harmony
    # phrasing, any signature feel (half-time, swung, 4-on-the-floor,
    # syncopated, laid-back). Downstream fill calls read this so every
    # instrument agent composes notes that fit the same groove instead of
    # each one defaulting to generic pop quarter-notes.
    rhythmic_feel: str = ""
    key: str = "C major"
    tempo_bpm: float = Field(default=120.0, gt=20.0, lt=300.0)
    time_signature_numerator: int = Field(default=4, ge=1, le=12)
    time_signature_denominator: int = Field(default=4, ge=1, le=16)
    num_bars: int = Field(default=16, ge=4, le=128)
    sections: list[SectionPlan] = Field(default_factory=list)
    chord_progression: list[ChordSpanPlan] = Field(default_factory=list)
    instruments: list[InstrumentDecl] = Field(default_factory=list)
    # Emitted AFTER the roster (field order = generation order) so it can
    # reference the actual instrument ids: which octave range each voice
    # owns, which rhythmic slot it occupies, and how many voices may be
    # busy at once. Every fill call reads this — it is the glue that stops
    # parallel-composed instruments from stepping on each other.
    arrangement_plan: str = ""


class InstrumentFill(BaseModel):
    """One instrument's notes, emitted by a per-instrument LLM call."""

    id: str
    notes: list[NotePlan] = Field(default_factory=list)


def spec_from_skeleton(
    skeleton: BandSkeleton,
    fills: dict[str, list[NotePlan]],
) -> BandSpec:
    """Merge a skeleton + per-instrument fills into a full `BandSpec`.

    Missing fills default to an empty note list — that keeps `compose_band`
    working when a fill call failed (its instrument plays no notes; the rest
    of the song is intact). Drums always get an empty list on the LLM side
    because they're synthesised deterministically downstream.
    """
    return BandSpec(
        genre=skeleton.genre,
        rhythmic_feel=skeleton.rhythmic_feel,
        arrangement_plan=skeleton.arrangement_plan,
        key=skeleton.key,
        tempo_bpm=skeleton.tempo_bpm,
        time_signature_numerator=skeleton.time_signature_numerator,
        time_signature_denominator=skeleton.time_signature_denominator,
        num_bars=skeleton.num_bars,
        sections=skeleton.sections,
        chord_progression=skeleton.chord_progression,
        instruments=[
            InstrumentPlan(
                id=decl.id,
                instrument=decl.instrument,
                patch=decl.patch,
                role=decl.role,
                is_drum=decl.is_drum,
                playing_style=decl.playing_style,
                onset_grid=decl.onset_grid,
                max_notes_per_bar=decl.max_notes_per_bar,
                notes=fills.get(decl.id, []),
            )
            for decl in skeleton.instruments
        ],
    )
