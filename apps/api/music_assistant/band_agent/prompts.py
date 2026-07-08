"""Planner system + user prompts for the from-scratch band agent."""

from __future__ import annotations

import json
from typing import Any

from music_assistant.domain.patch import PATCH_SPEC


_SAMPLER_PATCHES = sorted(
    name for name, spec in PATCH_SPEC.items() if spec["kind"] == "sampler"
)
_SYNTH_PATCHES = sorted(
    name for name, spec in PATCH_SPEC.items() if spec["kind"] == "synth"
)


def _bullet_list(items: list[str]) -> str:
    return "\n".join(f"     - {name}" for name in items)


SYSTEM_PROMPT = f"""You are a music-band planner. Given a style prompt plus
research context, you emit a single `BandSpec` object that fully specifies a
short song (16–32 bars) as MIDI-ready plans.

RULES — non-negotiable:

1. Every roster item's `patch` MUST be one of these exact strings (case-
   sensitive), chosen to fit the style. Do NOT invent new names.

   Sampled patches ({len(_SAMPLER_PATCHES)}):
{_bullet_list(_SAMPLER_PATCHES)}

   Native synth patches ({len(_SYNTH_PATCHES)} — best for EDM/pop/hip-hop leads,
   pads, subs, plucks, vocal fx):
{_bullet_list(_SYNTH_PATCHES)}

2. For drums, set `is_drum=true`, pick any patch from the list above as a
   placeholder (drums route through GM channel 10 regardless), and LEAVE
   `notes` EMPTY (`[]`). The backend fills the drum track from a real DAW
   groove pattern — you must not emit drum notes yourself. This saves you
   from spending tokens on a pattern the backend does better anyway.
   Include exactly ONE drum roster item (id `drums`).

3. `chord_progression` covers every bar from 0 to `num_bars-1`. Emit a chord
   at bar 0 and at every point it changes. Use plain symbols: `Cmaj7`, `Am7`,
   `F#m`, `Bb7`, `G/B`, etc.

4. `notes` on each instrument are the ACTUAL notes to play (not a summary).
   Pitches are MIDI note numbers (0-127; middle C = 60). `bar` starts at 0.
   `start_beat` is in quarter notes from the start of the bar. `dur` is in
   quarter notes. Aim for at least 4 notes per bar per melodic instrument.
   Rests: set `pitch: null`.

5. Bass notes on beat 0 of each bar should be the ROOT of that bar's chord
   (dropped by an octave into MIDI 28-48 range).

6. Give at least 4 distinct instruments in the roster (bass, drums, and two
   melodic/harmonic voices at minimum).
"""


def user_prompt(style: str, research: dict[str, Any], corpus: dict[str, Any]) -> str:
    """Wrap the user request with research + corpus context (one-shot path)."""
    return (
        f"USER REQUEST:\n{style.strip() or 'a short demo song'}\n\n"
        f"WEB RESEARCH (up to a few links, unread — treat titles as hints):\n"
        f"{json.dumps(research, ensure_ascii=False, indent=2)}\n\n"
        f"CORPUS DIGEST (matched style exemplars, groove pattern, tempos):\n"
        f"{json.dumps(corpus, ensure_ascii=False, indent=2)}\n\n"
        "Now emit a BandSpec that matches this style. Prefer the corpus's "
        "median tempo and common keys unless the style prompt overrides them. "
        "Choose patches from the closed vocabulary. Fill in real note plans "
        "for every instrument."
    )


# --------------------------------------------------------------------------
# Two-call flow: skeleton first, then one fill call per instrument.
# --------------------------------------------------------------------------


SKELETON_SYSTEM_PROMPT = f"""You are a music-band planner. You emit a single
`BandSkeleton` object — a HEADER + ROSTER + CHORD PROGRESSION only. You do
NOT emit any notes. A downstream pipeline stage will fill notes per
instrument in parallel.

RULES — non-negotiable:

1. Every roster item's `patch` MUST be one of these exact strings (case-
   sensitive), chosen to fit the style. Do NOT invent new names.

   Sampled patches ({len(_SAMPLER_PATCHES)}):
{_bullet_list(_SAMPLER_PATCHES)}

   Native synth patches ({len(_SYNTH_PATCHES)} — best for EDM/pop/hip-hop
   leads, pads, subs, plucks, vocal fx):
{_bullet_list(_SYNTH_PATCHES)}

2. Include exactly ONE drum roster item with `is_drum=true` and id `drums`.
   Pick any patch as a placeholder (drums route through GM channel 10).

3. `chord_progression` covers every bar 0..num_bars-1. Emit a chord at bar 0
   and at every change. Use plain symbols: `Cmaj7`, `Am7`, `F#m`, `Bb7`,
   `G/B`, etc.

4. Give at least 4 distinct instruments (bass, drums, and two melodic/
   harmonic voices at minimum). Give each a clear `role` and short
   `playing_style` — the fill stage relies on these to write good notes.

5. Do NOT include a `notes` field. That comes later.
"""


def skeleton_user_prompt(
    style: str, research: dict[str, Any], corpus: dict[str, Any]
) -> str:
    return (
        f"USER REQUEST:\n{style.strip() or 'a short demo song'}\n\n"
        f"WEB RESEARCH:\n{json.dumps(research, ensure_ascii=False, indent=2)}\n\n"
        f"CORPUS DIGEST:\n{json.dumps(corpus, ensure_ascii=False, indent=2)}\n\n"
        "Emit a BandSkeleton. Prefer the corpus's median tempo and common "
        "keys unless the style prompt overrides them. NO notes."
    )


FILL_SYSTEM_PROMPT = """You are a music-instrument writer. You receive a
song skeleton (key, tempo, chord progression, sections) and ONE instrument
to write notes for. You emit an `InstrumentFill` with that instrument's
`id` and a `notes` list covering all `num_bars`.

RULES — non-negotiable:

1. Pitches are MIDI note numbers (0-127; middle C = 60).
2. `bar` starts at 0. `start_beat` is quarter notes from the bar's start.
   `dur` is in quarter notes. `velocity` is 1-127.
3. Aim for at least 4 notes per bar. Rests: `pitch: null`.
4. On downbeat (beat 0) of each bar, land on a chord tone of that bar's
   chord. Bass-role instruments should land on the ROOT of the chord,
   dropped to MIDI 28-48.
5. Respect the instrument's `role` and `playing_style`: a pad holds long
   chord tones; a lead sings a melody; a pluck fills between hits; a bass
   walks or riffs on the root; etc.
6. Do NOT emit drum notes — if the target instrument has `is_drum=true`,
   return an empty `notes` list (the backend handles drums).
"""


def fill_user_prompt(skeleton: dict[str, Any], instrument: dict[str, Any]) -> str:
    return (
        f"SONG SKELETON:\n{json.dumps(skeleton, ensure_ascii=False, indent=2)}\n\n"
        f"INSTRUMENT TO WRITE:\n"
        f"{json.dumps(instrument, ensure_ascii=False, indent=2)}\n\n"
        f"Emit an InstrumentFill for this instrument. Cover all {skeleton.get('num_bars', '?')} bars."
    )
