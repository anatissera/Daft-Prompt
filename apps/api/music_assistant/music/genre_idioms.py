"""Curated per-genre playing-idiom notes.

A hand-written baseline of how each instrument role idiomatically plays in a
given genre — ghost notes, comping, backbeat placement, and so on. The director
already commits to a `rhythmic_feel` and per-instrument `playing_style`, but the
primary model (MiniMax) is not a music-theory expert, and the structural corpus
(chord progressions, grooves) says nothing about *technique*. Injecting these
notes into the skeleton prompt grounds the director's commitments in expert
knowledge the model may otherwise approximate poorly.

This is a weak-to-medium prior, like the corpus digest: reference material, not
a rule. Roles are the coarse buckets the pipeline already uses (`bass`, `drums`,
`rhythm`, `lead`, `harmony`); the notes are phrased to apply whatever specific
instrument fills that slot.

Extend freely — adding a genre or role here needs no code change.
"""

from __future__ import annotations

from typing import Optional

# genre -> role -> one or two sentences of concrete, idiomatic technique.
IDIOMS: dict[str, dict[str, str]] = {
    "funk": {
        "bass": "Lock to the kick and anchor beat 1 (the 'One'). Syncopated 16ths with ghost notes between the accents; slap/pop or muted plucks, lots of space.",
        "drums": "Tight 16th-note hi-hat grid, backbeat snare on 2 and 4 with ghost snares in between, kick on 1 and syncopated 16ths. Groove sits in the pocket, slightly behind.",
        "rhythm": "16th-note muted scratch chops between chords, emphasis on upbeats, short percussive stabs. Leave gaps for the bass to move.",
        "lead": "Sparse, syncopated riffs answering the groove rather than soloing over it. Pentatonic and blues-scale licks, bent notes, call-and-response phrasing.",
        "harmony": "Extended chords (9ths, 11ths, 13ths) as short stabs on the upbeats, clav or Rhodes comping. Rhythm over harmonic motion.",
    },
    "jazz": {
        "bass": "Walking quarter-note bass line outlining the changes, chromatic approach tones into each chord root. Steady, propulsive, occasional triplet fills at phrase ends.",
        "drums": "Swung ride-cymbal pattern (ding, ding-da-ding), hi-hat on 2 and 4, brushes or light sticks. Comp with snare/bass-drum accents ('feathering' the kick), trade space with the soloist.",
        "rhythm": "Comping: sparse, syncopated chord voicings behind the soloist, rootless voicings, never on every beat. Listen and leave space.",
        "lead": "Bebop lines over the changes — arpeggios, enclosures, chromatic passing tones, swung eighths. Phrase like a horn: breathe between ideas.",
        "harmony": "Rootless 7th/9th/13th voicings, tritone substitutions, ii-V-I motion. Comp rhythmically, not on every beat.",
    },
    "bossa nova": {
        "bass": "Sparse root–fifth pattern on beats 1 and the 'and' of 2, gentle and rounded. Follows the surdo feel, never busy.",
        "drums": "Soft bossa clave on rim/cross-stick, brushed or light snare, steady quiet hi-hat. Understated — the groove is in the guitar, not the kit.",
        "rhythm": "Nylon-string guitar bossa pattern: thumb plays bass notes on 1 and 2-and, fingers syncopate the chord on the offbeats. The signature bossa clave.",
        "lead": "Lyrical, laid-back melody with lots of rest, soft dynamics, subtle chromaticism. Never rushed.",
        "harmony": "Lush jazz voicings — maj7, m7, 6/9, altered dominants — voiced high and soft, moving smoothly. Bossa syncopation in the comping.",
    },
    "disco": {
        "bass": "Octave-jumping bass line, driving 8th or 16th notes, prominent and melodic. Locks to the four-on-the-floor kick.",
        "drums": "Four-on-the-floor kick on every beat, open hi-hat on the offbeats, snare/clap backbeat on 2 and 4. Relentless, danceable.",
        "rhythm": "16th-note wah/muted guitar chucks on the upbeats, tight and percussive. Strings and guitar answer each other.",
        "lead": "Soaring string lines or synth hooks, glissandos, orchestral stabs punctuating the phrase ends.",
        "harmony": "Lush 7th and 9th chords, syncopated stabs, string-section swells. Bright and full.",
    },
    "rock": {
        "bass": "Root-driven eighth notes locked to the kick, staying in the pocket. Simple, powerful, occasional fills into the chorus.",
        "drums": "Solid backbeat — kick on 1 and 3, snare on 2 and 4 — driving eighth-note hi-hats, crashes on section changes. Steady and forceful.",
        "rhythm": "Power chords (root + fifth), palm-muted eighths in verses, open ringing chords in choruses. Down-picked drive.",
        "lead": "Pentatonic/blues riffs and hooks, string bends, vibrato. Melodic in verses, bigger in the chorus.",
        "harmony": "Straightforward triads and power chords following the progression, held or strummed. Supports rather than decorates.",
    },
    "soul": {
        "bass": "Melodic, syncopated line locked to the kick with tasteful fills, walking into chord changes. Warm and round.",
        "drums": "Backbeat on 2 and 4, ghost snares, tight hi-hats with subtle openings, deep pocket slightly behind the beat.",
        "rhythm": "Clean chord comping with 16th-note upstroke chops, Rhodes or guitar, answering the vocal phrase.",
        "lead": "Vocal-like, expressive melodic lines with bends and slides, gospel-inflected. Answers the lead vocal, never crowds it.",
        "harmony": "Rich 7th/9th chords, gospel voicings, organ pads and Rhodes, plagal (IV-I) motion.",
    },
    "reggaeton": {
        "bass": "Deep sub bass following the dembow, hits on 1 and the syncopated dembow accents. Simple and heavy.",
        "drums": "Dembow pattern: kick on 1, snare/rim on the 'a' of 1 and beat 3-and (the boom-ch-boom-chick), steady hats. The signature reggaeton groove.",
        "rhythm": "Sparse muted stabs on the offbeats, leaving room for the dembow and vocal. Minimal.",
        "lead": "Short catchy synth or pluck hooks, repetitive and memorable, sitting in the mid range.",
        "harmony": "Minor-key pads and plucks, simple 4-chord loops, dark and atmospheric.",
    },
    "metal": {
        "bass": "Fast root-following eighths or sixteenths locked to the double-kick, palm-muted and aggressive. Follows the guitar riff.",
        "drums": "Double-bass kick patterns, driving or blast-beat depending on subgenre, crashes and china accents, tight fast fills.",
        "rhythm": "Palm-muted low power-chord chugs, tight gallop rhythms, drop-tuned. Precise and heavy.",
        "lead": "Fast shredding runs, harmonic minor and pentatonic, tapping, aggressive bends and dive bombs.",
        "harmony": "Power chords and diminished/harmonic-minor tensions, held under the riffs. Dark and dissonant.",
    },
}


# Aliases so common prompt words hit a curated entry.
_GENRE_ALIASES: dict[str, str] = {
    "bossa": "bossa nova",
    "bossanova": "bossa nova",
    "hard rock": "rock",
    "classic rock": "rock",
    "punk": "rock",
    "grunge": "rock",
    "rnb": "soul",
    "r&b": "soul",
    "motown": "soul",
    "neo-soul": "soul",
    "neo soul": "soul",
    "reggeton": "reggaeton",
    "reguetón": "reggaeton",
    "reggaetón": "reggaeton",
    "dark metal": "metal",
    "heavy metal": "metal",
    "death metal": "metal",
    "thrash": "metal",
}


def lookup(genre: Optional[str]) -> Optional[dict[str, str]]:
    """Return the role→technique map for a genre, or None if none matches.

    Best-effort: exact match, then alias, then a substring scan (so "80s funk"
    still finds "funk"). Prefers the longest genre key on a substring tie so
    "bossa nova" wins over a stray "nova".
    """
    if not genre:
        return None
    g = genre.strip().lower()
    if not g:
        return None
    if g in IDIOMS:
        return IDIOMS[g]
    if g in _GENRE_ALIASES:
        return IDIOMS[_GENRE_ALIASES[g]]
    # Substring scan over both canonical names and aliases.
    candidates: list[tuple[int, str]] = []
    for key in IDIOMS:
        if key in g:
            candidates.append((len(key), key))
    for alias, canonical in _GENRE_ALIASES.items():
        if alias in g:
            candidates.append((len(alias), canonical))
    if candidates:
        return IDIOMS[max(candidates)[1]]
    return None
