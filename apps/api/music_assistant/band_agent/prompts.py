"""Planner system + user prompts for the from-scratch band agent."""

from __future__ import annotations

import json
from typing import Any, Optional

from music_assistant.domain.patch import PATCH_SPEC
from music_assistant.music.genre_idioms import lookup as lookup_idioms


def _idiom_block(genre: Optional[str]) -> str:
    """Reference text on how each role idiomatically plays in this genre.

    Empty when the genre isn't in the curated library — the director then relies
    on the corpus and its own knowledge, exactly as before.
    """
    idioms = lookup_idioms(genre)
    if not idioms:
        return ""
    lines = "\n".join(f"- {role}: {note}" for role, note in idioms.items())
    return (
        "GENRE PLAYING IDIOMS (expert reference for how each role idiomatically "
        "plays in this style — ground `rhythmic_feel` and each instrument's "
        "`playing_style` in these; a strong prior, but honour the specific "
        f"request when it diverges):\n{lines}\n\n"
    )


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
   reference track, and match the SOUND SOURCE to the tradition:
     - Acoustic/traditional styles get REAL instruments from the sampled
       bank. Tango: tango_accordion (bandoneón), violin, acoustic piano,
       contrabass, acoustic guitar — never synth pads or electronic
       drums. Rock: electric guitars (distortion/overdriven/clean),
       electric bass, drum kit, maybe hammond organ. Jazz, folk, salsa,
       flamenco, classical: same principle — sampled acoustic patches.
     - Electronic styles (dubstep, trap, EDM, house, future bass,
       reggaeton's beat layer) are built from synthesized sources: sub
       bass, wobble/growl bass, supersaw or pluck leads, pads, chopped
       vocal fx, electronic drums.
     - Hybrid styles mix deliberately: reggaeton = dembow electronic
       drums + synth bass + plucked/latin melodic elements; latin pop =
       acoustic percussion flavor + synth pads.
   Never pad this list with instruments that merely "could work" — only
   what DEFINES the style.

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

5. `arrangement_plan` (emitted AFTER the roster) — 3-6 sentences assigning
   each roster id its OWN space so parallel-composed parts don't collide:
     - REGISTER: which octave range each voice owns (e.g. "sub: C1-C2;
       piano comps C3-C4; lead sings C5-C6"). No two sustained voices in
       the same octave band.
     - RHYTHMIC SLOT: who plays on the beat, who syncopates, who fills the
       gaps (call-and-response with the lead, comping between vocal
       phrases).
     - DENSITY BUDGET: at most 1-2 voices busy at any moment; name which
       voice leads each section and who steps back.
   Reference roster ids explicitly. Every fill call reads this plan.

RULES — non-negotiable:

6. Every roster item's `patch` MUST be one of these exact strings (case-
   sensitive), chosen to fit the style. Do NOT invent new names. The
   `instrument` display name and the `patch` MUST denote the SAME
   instrument — a roster item named "guitar_rhythm" with a piano patch is
   a defect, not a stylistic choice.

   Sampled patches ({len(_SAMPLER_PATCHES)} — real recorded instruments;
   the right choice for every acoustic/traditional style):
{_bullet_list(_SAMPLER_PATCHES)}

   Native synth patches ({len(_SYNTH_PATCHES)} — true synthesis for
   electronic styles: EDM/dubstep/trap leads, pads, subs, plucks,
   vocal fx; do NOT use these for acoustic/traditional genres):
{_bullet_list(_SYNTH_PATCHES)}

7. Include AT MOST one drum roster item with `is_drum=true` and id `drums`.
   Pick any patch as a placeholder (drums route through GM channel 10).
   OMIT the drum item entirely for styles that have no drum kit — tango,
   classical, choral, solo piano, bossa nova trio without kit. Forcing a
   kit into those styles is a defect. When the style's percussion is not
   a kit (congas, timbales, cajón), still use the single drum item — the
   fill stage writes GM percussion pitches for those voices.

8. `chord_progression` covers every bar 0..num_bars-1. Emit a chord at bar 0
   and at every change. Use plain symbols: `Cmaj7`, `Am7`, `F#m`, `Bb7`,
   `G/B`, etc.

9. ENSEMBLE SIZE: first choose the SMALLEST ensemble capable of an
   authentic arrangement of this style, then declare it. A solo, duo or
   trio is valid; silence and omitted layers are valid. NEVER add an
   instrument merely because a slot is available or to make the plan
   look more sophisticated — every roster item must earn its place with
   a distinct purpose stated in its `role` (why does THIS style need
   THIS voice?). Give each a clear `role` and short `playing_style` —
   the fill stage relies on these to write good notes.

   Each roster item ALSO commits two rhythmic contracts that are enforced
   mechanically downstream (notes violating them get dropped):

   - `onset_grid`: the instrument's one-bar rhythmic cell as a 16th-note
     grid string — one char per 16th, "x" = onset, "." = rest; 16 chars
     for 4/4 (numerator × 4 otherwise). This is where the GENRE'S RHYTHM
     LIVES — write the actual pattern, not a generic one:
       reggaeton dembow kick:  "x.......x......."
       reggaeton dembow snare: "...x..x....x..x."  (as part of drums' grid)
       tango habanera bass:    "x.....x.x...x..."
       four-on-the-floor kick: "x...x...x...x..."
       offbeat house hats:     "..x...x...x...x."
     Drums are the exception: their kit has several voices with different
     patterns, so put the EXACT per-voice beats in `rhythmic_feel` /
     `playing_style` instead (e.g. "kick on 1 and 3; snare on the
     2.75 and 3.5") and leave the drum item's grid empty. Bass and
     comping voices get STRICT grids. Leads/melodies that need free
     phrasing may leave it empty ("").
   - `max_notes_per_bar`: hard density ceiling per bar (simultaneous
     chord tones count as ONE event). Calm/sparse styles: 2-4 for
     accompaniment. Busy styles: 8-16. 0 = unlimited (use sparingly).
   - `pitch_low` / `pitch_high`: the sensible MIDI register for THIS
     instrument in THIS role (bass: 28-52, not 0-127; a comping guitar:
     48-76; a lead: 60-88). Notes outside get octave-folded back in —
     a bass wandering into the 5th octave stops sounding like a bass.
   A slow blues where every instrument commits max 3-4 events/bar CANNOT
   turn into a wall of sound — that is the point of these fields.

10. Do NOT include a `notes` field. That comes later.

11. The CORPUS DIGEST's `common_roles` come from a coarse genre-tagged MIDI
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
    song_evidence: dict[str, Any] | None = None,
    genre: str | None = None,
) -> str:
    idiom_block = _idiom_block(genre if genre is not None else style)
    excerpt_block = ""
    if excerpts:
        excerpt_block = (
            f"STYLE RESEARCH EXCERPTS (real page text about this style/artist — "
            f"ground `style_summary` and `canonical_instruments` in these):\n"
            f"{json.dumps(excerpts, ensure_ascii=False, indent=2)}\n\n"
        )
    evidence_block = ""
    if song_evidence:
        evidence_block = (
            f"KNOWN-SONG EVIDENCE (scraped from tab/chord sites for the exact "
            f"song the user referenced — STRONG grounding: prefer these tempo/"
            f"key/meter values and let the per-section chord progressions "
            f"shape yours):\n"
            f"{json.dumps(song_evidence, ensure_ascii=False, indent=2)}\n\n"
        )
    return (
        f"USER REQUEST:\n{style.strip() or 'a short demo song'}\n\n"
        f"{idiom_block}"
        f"{evidence_block}"
        f"{excerpt_block}"
        f"WEB RESEARCH (titles only):\n{json.dumps(research, ensure_ascii=False, indent=2)}\n\n"
        f"CORPUS DIGEST (weak prior — see rule 11):\n{json.dumps(corpus, ensure_ascii=False, indent=2)}\n\n"
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
   Your instrument carries two BINDING contracts (enforced mechanically —
   violating notes are deleted, so don't waste them):
     - `onset_grid`: a 16th-note grid of your one-bar cell ("x" = allowed
       onset slot, "." = rest; slot k = beat k/4). Every note's start_beat
       MUST land on an "x" slot. You may SKIP slots (especially in low-
       energy sections) but never add onsets between them. Empty grid =
       free phrasing.
     - `max_notes_per_bar`: your density ceiling (chord tones struck
       together count as one event). Stay under it.
     - `pitch_low` / `pitch_high`: your register. Notes outside get
       octave-folded back in, so write inside it from the start.
4. On the downbeat of each bar, land on a chord tone of that bar's chord.
   Bass-role instruments should land on the ROOT of the chord, dropped to
   MIDI 28-48. Rests: `pitch: null`.
5. Respect the instrument's `role` and `playing_style` — they refine the
   feel for this specific voice.
6. If the target instrument has `is_drum=true`, you WRITE the drum groove.
   Your onset_grid does NOT bind you (a kit has several voices with
   different patterns) — instead, work VOICE BY VOICE: first decide the
   kick's one-bar pattern from the rhythmic_feel, then the snare's, then
   the hats', and only then emit the notes, repeating each voice's cell
   every bar (with fills at section boundaries). If the rhythmic_feel
   names exact beats for a voice, those beats are law.
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
9. ARRANGEMENT AWARENESS. The skeleton's `ensemble` lists every band
   member's role and committed playing style, and `arrangement_plan`
   assigns registers, rhythmic slots and the density budget. You are ONE
   voice in that band — carve your own space:
     - Stay in the register the plan assigns you; if unassigned, pick a
       band no other sustained voice occupies.
     - Do not duplicate another instrument's rhythmic pattern in the same
       register; interlock instead (comp between the lead's phrases,
       syncopate against the on-beat voice).
     - Respect the density budget: when the plan says another voice leads
       a section, play sparser there — long notes, gaps, or rest.
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
