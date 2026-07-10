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
`BandSkeleton` object — a style analysis + HEADER + ROSTER + CHORD
PROGRESSION only. You do NOT emit any notes. A downstream pipeline stage
will fill notes per instrument in parallel.

You fill the fields IN ORDER, and each field constrains the next:

1. `style_summary` — 2-4 sentences identifying the requested style or
   artist's signature sound. When STYLE RESEARCH EXCERPTS are provided,
   ground this in what they actually say (subgenre, era, production
   hallmarks, named gear/synths). If the user names an artist, identify
   the artist's genre and describe THEIR sound, not a generic one.

2. `canonical_instruments` — the 5-10 instruments that are IDIOMATIC for
   this exact style. Think about what you would actually hear on a
   reference track. Electronic styles (dubstep, trap, EDM, house, future
   bass) are built from synthesized sources: sub bass, wobble/growl bass,
   supersaw or pluck leads, pads, chopped vocal fx, electronic drum
   machines — NOT acoustic pianos, organs, orchestral strings, or
   hand percussion. Acoustic styles (jazz, folk, rock) get real
   instruments. Never pad this list with instruments that merely
   "could work" — only what DEFINES the style.

3. `rhythmic_feel` — 3-6 sentences committing to the CONCRETE groove of
   this style. This is the ensemble-level groove skeleton every fill call
   will read. Be specific per role: kick/snare placement, hat subdivision,
   bass articulation, harmony phrasing, and any signature feel (half-time,
   swung, 4-on-the-floor, laid-back, syncopated, on-top). Example of the
   detail expected: 'Dubstep half-time: kick on 1 and 3.5, snare on 3, hats
   in 16ths with accents on every -a; sub bass sustained across each bar
   with an octave-drop pickup on bar 4; supersaw stabs on the 2-and-3-and
   of every bar, never on downbeats; drop hits on bar 5 and 13.' Do NOT
   default to generic pop quarter-notes. A weak rhythmic_feel makes every
   downstream instrument sound like a chorale regardless of the roster.

4. The ROSTER (`instruments`) MUST be drawn from your own
   `canonical_instruments` list — every roster item's `instrument` name
   must correspond to one of the canonical entries. If you are tempted to
   add something outside that list, the list was wrong: fix the list, not
   the roster.

RULES — non-negotiable:

5. Every roster item's `patch` MUST be one of these exact strings (case-
   sensitive), chosen to fit the style. Do NOT invent new names.

   Sampled patches ({len(_SAMPLER_PATCHES)}):
{_bullet_list(_SAMPLER_PATCHES)}

   Native synth patches ({len(_SYNTH_PATCHES)} — best for EDM/pop/hip-hop
   leads, pads, subs, plucks, vocal fx):
{_bullet_list(_SYNTH_PATCHES)}

6. Include exactly ONE drum roster item with `is_drum=true` and id `drums`.
   Pick any patch as a placeholder (drums route through GM channel 10).

7. `chord_progression` covers every bar 0..num_bars-1. Emit a chord at bar 0
   and at every change. Use plain symbols: `Cmaj7`, `Am7`, `F#m`, `Bb7`,
   `G/B`, etc.

8. Give at least 4 distinct instruments (bass, drums, and two melodic/
   harmonic voices at minimum). Give each a clear `role` and short
   `playing_style` — the fill stage relies on these to write good notes.

9. Do NOT include a `notes` field. That comes later.

10. The CORPUS DIGEST's `common_roles` come from a coarse genre-tagged MIDI
    corpus and are only a WEAK prior. When they conflict with the style you
    identified in `style_summary` (e.g. corpus says piano/guitar but the
    style is dubstep), trust your style analysis and the research excerpts,
    not the corpus roles.
"""


def skeleton_user_prompt(
    style: str,
    research: dict[str, Any],
    corpus: dict[str, Any],
    excerpts: list[dict[str, Any]] | None = None,
) -> str:
    excerpt_block = ""
    if excerpts:
        excerpt_block = (
            f"STYLE RESEARCH EXCERPTS (real page text about this style/artist — "
            f"ground `style_summary` and `canonical_instruments` in these):\n"
            f"{json.dumps(excerpts, ensure_ascii=False, indent=2)}\n\n"
        )
    return (
        f"USER REQUEST:\n{style.strip() or 'a short demo song'}\n\n"
        f"{excerpt_block}"
        f"WEB RESEARCH (titles only):\n{json.dumps(research, ensure_ascii=False, indent=2)}\n\n"
        f"CORPUS DIGEST (weak prior — see rule 10):\n{json.dumps(corpus, ensure_ascii=False, indent=2)}\n\n"
        "Emit a BandSkeleton. Prefer the corpus's median tempo and common "
        "keys unless the style prompt or research overrides them. NO notes."
    )


INTENT_SYSTEM_PROMPT = """You classify a music-generation request into one of
two intents.

- `replicate` — the user names a SPECIFIC existing song they want you to
  reproduce (title, or title + artist, or an unambiguous artist reference).
  Set `target` to a compact search string like "artist song title".
  Examples: "replicate marshmello alone", "copiame billie eilish bad guy",
  "cover paint it black", "tocame dont stop believing", "hazme viva la vida
  de coldplay".

- `compose` — everything else: genre/style descriptions, mood, feels,
  vague "in the style of X" phrasing, or blank/short directives. Set
  `target` to null.
  Examples: "make a dark metal song", "una cancion como marshmello",
  "tipo trap", "lofi 90 bpm", "hazme algo triste", "rock 4 bars".

Be strict: if the user says "like X" / "como X" / "tipo X" / "en el estilo
de X", that is COMPOSE, not replicate. Only classify as replicate when the
user is unambiguously naming a specific song / artist to reproduce.
"""


def intent_user_prompt(prompt: str) -> str:
    return f"USER PROMPT:\n{prompt.strip() or '(empty)'}\n\nClassify."


FILL_SYSTEM_PROMPT = """You are a music-instrument writer. You receive a song
skeleton (key, tempo, chord progression, sections, ensemble rhythmic_feel)
and ONE instrument to write notes for, plus a BAR RANGE for THIS call. You
emit an `InstrumentFill` with that instrument's `id` and a `notes` list
covering ONLY the requested bar range — the rest of the song will be
composed in separate calls, so trust the range.

RULES — non-negotiable:

1. Pitches are MIDI note numbers (0-127; middle C = 60).
2. `bar` starts at 0. `start_beat` is quarter notes from the bar's start.
   `dur` is in quarter notes. `velocity` is 1-127.
3. FOLLOW the ensemble rhythmic_feel literally. If it says half-time with
   snare on 3 and kick on 1 and 3.5, sub bass sustained in 8ths, supersaw
   stabs on offbeats — your notes MUST reflect that. Rhythmic density and
   note placement flow from the rhythmic_feel, not from a generic 4-notes-
   per-bar default. Genres like dubstep, trap, drum-and-bass need 8-16
   notes/bar on lead/bass parts; ballads may need 1-2/bar. Let the feel
   dictate.
4. On the downbeat of each bar, land on a chord tone of that bar's chord.
   Bass-role instruments should land on the ROOT of the chord, dropped to
   MIDI 28-48. Rests: `pitch: null`.
5. Respect the instrument's `role` and `playing_style` — they refine the
   feel for this specific voice.
6. If the target instrument has `is_drum=true`, you WRITE the drum groove.
   Emit GM channel-10 percussion pitches, following the ensemble
   `rhythmic_feel` literally. Use these pitches:
      36  kick        (bass drum)
      38  snare
      40  electric snare / clap alternate
      42  closed hi-hat
      44  pedal hi-hat
      46  open hi-hat
      49  crash cymbal
      51  ride cymbal
      41 / 47 / 50  low / mid / high tom
      39  hand clap
      54  tambourine
      56  cowbell
      82  shaker
   The rhythmic_feel dictates placement — half-time snare on beat 3, kick
   on 1 and 3.5, hats in 16ths with accented offbeats, etc. Do NOT default
   to four-on-the-floor rock/house unless the rhythmic_feel actually says
   so. Rests are not needed for drums (they are triggered percussion —
   just omit hits you don't want).
7. Do NOT emit notes outside the requested bar range. Notes outside will
   be dropped and the other bars are being composed in separate calls.
8. The section's ENERGY drives dynamics — this is what makes builds and
   drops actually land:
     - low energy: SPARSE. Half (or less) of your normal density, soft
       velocities (50-85), leave space; resting entirely for some bars is
       musical, not a failure.
     - medium: your normal density, velocities 80-105.
     - high energy: FULL. Maximum idiomatic density, velocities 100-127,
       every rhythmic slot the feel allows. The FIRST downbeat of a high-
       energy section after a lower one is the impact moment — hit it hard
       (velocity 120+) with your lowest/strongest register.
   A song whose sections all have the same density has no build and no
   drop, whatever the genre.
"""


def fill_user_prompt(
    skeleton: dict[str, Any],
    instrument: dict[str, Any],
    *,
    bar_start: int | None = None,
    bar_end: int | None = None,
    section_name: str = "",
    section_energy: str = "",
) -> str:
    """Build the fill user prompt. When bar_start/bar_end are provided the ask
    is section-scoped — the LLM only writes notes for that range, so a 32-bar
    song is composed as multiple smaller calls that don't blow past the
    provider's structured-output budget."""
    range_line = ""
    if bar_start is not None and bar_end is not None:
        section_hint = ""
        if section_name:
            section_hint = f" (section '{section_name}'"
            if section_energy:
                section_hint += f", energy {section_energy}"
            section_hint += ")"
        range_line = (
            f"\nBAR RANGE FOR THIS CALL: {bar_start} to {bar_end - 1} inclusive"
            f"{section_hint}. Emit notes ONLY for these bars; notes outside "
            f"will be dropped."
        )
    return (
        f"SONG SKELETON:\n{json.dumps(skeleton, ensure_ascii=False, indent=2)}\n\n"
        f"INSTRUMENT TO WRITE:\n"
        f"{json.dumps(instrument, ensure_ascii=False, indent=2)}\n"
        f"{range_line}\n\n"
        "Emit an InstrumentFill for this instrument. Note density MUST fit "
        "the ensemble's rhythmic_feel (dubstep leads/bass need 8-16 notes "
        "per bar; ballads need 1-2)."
    )
