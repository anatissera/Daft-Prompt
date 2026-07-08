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

2. For drums, set `is_drum=true` and pick a drum-ish `patch` from the list
   above (e.g. `synth_bass_1` is fine as a placeholder — drums route through
   GM channel 10 regardless of patch).

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

6. Drums typically use these GM pitches on `is_drum=true` tracks:
   36=kick, 38=snare, 42=closed hat, 46=open hat, 49=crash, 51=ride.

7. Give at least 4 distinct instruments in the roster (bass, drums, and two
   melodic/harmonic voices at minimum).
"""


def user_prompt(style: str, research: dict[str, Any], corpus: dict[str, Any]) -> str:
    """Wrap the user request with research + corpus context."""
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
