"""MIDI file -> compact symbolic representation, offline only.

Mirror of `render_midi.py`. This module exists so the corpus pipeline (Lakh,
Groove) can ingest external `.mid` files. **Never called from the runtime LLM
path** — LLMs never see raw MIDI or per-note dicts; they see the compact symbols
extracted here after they land in a parquet index.

`ReadSong` is intentionally distinct from `SongState` so a foreign track cannot
accidentally be fed into the composition graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pretty_midi

from .theory import beats_per_bar as _beats_per_bar


@dataclass
class ReadNote:
    bar: int
    start_beat: float
    pitch: int
    dur: float
    velocity: int


@dataclass
class ReadTrack:
    program: int
    is_drum: bool
    name: str
    notes: list[ReadNote] = field(default_factory=list)


@dataclass
class ReadSong:
    tempo_bpm: float
    time_signature: tuple[int, int]
    num_bars: int
    tracks: list[ReadTrack] = field(default_factory=list)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def read_midi(path: str) -> ReadSong:
    """Read a `.mid` file and return a `ReadSong` in bar/beat form. Multi-tempo
    and multi-time-signature files use their first entry (LMD tracks are usually
    stable within a track); notes past `num_bars` are dropped defensively."""
    try:
        pm = pretty_midi.PrettyMIDI(path)
    except OSError as exc:
        if "data byte must be in range" not in str(exc):
            raise
        # Wild MIDIs (Bitmidi downloads especially) often carry data bytes
        # >127. mido can CLIP those instead of refusing the file; re-save a
        # sanitized copy and parse that. This is what let "Smells Like Teen
        # Spirit" import instead of crashing the whole replicate flow.
        import tempfile

        import mido

        clipped = mido.MidiFile(filename=path, clip=True)
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
            clipped.save(tmp.name)
            pm = pretty_midi.PrettyMIDI(tmp.name)
    return pretty_midi_to_song(pm)


def pretty_midi_to_song(pm: pretty_midi.PrettyMIDI) -> ReadSong:
    tempo_bpm = _first_tempo(pm)
    time_sig = _first_time_signature(pm)
    bpb = _beats_per_bar(time_sig)
    sec_per_beat = 60.0 / tempo_bpm if tempo_bpm > 0 else 0.5

    total_beats = _total_beats(pm, sec_per_beat)
    num_bars = max(1, int(total_beats // bpb) + (1 if total_beats % bpb > 1e-6 else 0))

    tracks: list[ReadTrack] = []
    for inst in pm.instruments:
        notes: list[ReadNote] = []
        for pmn in inst.notes:
            start_beat_abs = pmn.start / sec_per_beat
            bar = int(start_beat_abs // bpb)
            if bar < 0 or bar >= num_bars:
                continue
            beat_in_bar = start_beat_abs - bar * bpb
            dur = max(0.0, (pmn.end - pmn.start) / sec_per_beat)
            notes.append(
                ReadNote(
                    bar=bar,
                    start_beat=round(beat_in_bar, 4),
                    pitch=int(pmn.pitch),
                    dur=round(dur, 4),
                    velocity=int(pmn.velocity),
                )
            )
        tracks.append(
            ReadTrack(
                program=int(inst.program),
                is_drum=bool(inst.is_drum),
                name=str(inst.name or ""),
                notes=notes,
            )
        )
    return ReadSong(
        tempo_bpm=float(tempo_bpm),
        time_signature=time_sig,
        num_bars=num_bars,
        tracks=tracks,
    )


def _first_tempo(pm: pretty_midi.PrettyMIDI) -> float:
    times, tempi = pm.get_tempo_changes()
    if len(tempi) > 0:
        return float(tempi[0])
    return 120.0


def _first_time_signature(pm: pretty_midi.PrettyMIDI) -> tuple[int, int]:
    if pm.time_signature_changes:
        ts = pm.time_signature_changes[0]
        return (int(ts.numerator), int(ts.denominator))
    return (4, 4)


def _total_beats(pm: pretty_midi.PrettyMIDI, sec_per_beat: float) -> float:
    end = pm.get_end_time()
    if sec_per_beat <= 0:
        return 0.0
    return end / sec_per_beat


# ---------------------------------------------------------------------------
# Symbolic extractors — all pure, all deterministic, no LLM
# ---------------------------------------------------------------------------


# GM program buckets → coarse instrument role, used for density-by-role and for
# matching a corpus track's instruments to a session's roster during retrieval.
GM_ROLE_BUCKETS: list[tuple[str, range]] = [
    ("piano", range(0, 8)),
    ("chromatic_perc", range(8, 16)),
    ("organ", range(16, 24)),
    ("guitar", range(24, 32)),
    ("bass", range(32, 40)),
    ("strings", range(40, 48)),
    ("ensemble", range(48, 56)),
    ("brass", range(56, 64)),
    ("reed", range(64, 72)),
    ("pipe", range(72, 80)),
    ("synth_lead", range(80, 88)),
    ("synth_pad", range(88, 96)),
    ("synth_effects", range(96, 104)),
    ("ethnic", range(104, 112)),
    ("percussive", range(112, 120)),
    ("sfx", range(120, 128)),
]


def program_role(program: int, is_drum: bool) -> str:
    if is_drum:
        return "drums"
    for name, r in GM_ROLE_BUCKETS:
        if program in r:
            return name
    return "unknown"


def extract_key(song: ReadSong) -> str:
    """Estimate key as a music21 string like 'C major' / 'A minor'. Uses
    Krumhansl-Schmuckler on aggregated pitch content of non-drum tracks. Falls
    back to 'C major' when there is nothing to analyze."""
    pitches: list[int] = []
    for t in song.tracks:
        if t.is_drum:
            continue
        pitches.extend(n.pitch for n in t.notes)
    if not pitches:
        return "C major"
    from music21 import note as m21note, stream as m21stream
    from music21.analysis.discrete import KrumhanslSchmuckler

    s = m21stream.Stream()
    for p in pitches[:2000]:  # cap for very long tracks
        n = m21note.Note()
        n.pitch.midi = int(p)
        s.append(n)
    try:
        k = KrumhanslSchmuckler().getSolution(s)
        return f"{k.tonic.name.replace('-', 'b')} {k.mode}"
    except Exception:
        return "C major"


# Chord templates as pitch-class sets. Ordered so specific chords (7ths) are
# tried before their triad supersets — a bar with a clear dominant-7 sound
# shouldn't collapse to a plain major triad.
_TRIAD_TEMPLATES: list[tuple[str, frozenset[int]]] = [
    ("maj7", frozenset({0, 4, 7, 11})),
    ("m7", frozenset({0, 3, 7, 10})),
    ("7", frozenset({0, 4, 7, 10})),
    ("m", frozenset({0, 3, 7})),
    ("", frozenset({0, 4, 7})),  # major triad, suffix ""
    ("dim", frozenset({0, 3, 6})),
]

_PC_TO_NAME = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def extract_progression(song: ReadSong) -> list[str]:
    """One chord symbol per bar, `num_bars` long. Uses a per-bar pitch-class
    histogram (weighted by note duration) matched against templates. Empty bars
    inherit the previous chord (or "N.C." if none yet)."""
    if song.num_bars <= 0:
        return []
    hist_per_bar = _pitch_class_histograms(song)
    out: list[str] = []
    last: Optional[str] = None
    for hist in hist_per_bar:
        if not hist or sum(hist) == 0:
            out.append(last or "N.C.")
            continue
        best_score = -1.0
        best_symbol = last or "N.C."
        for root_pc in range(12):
            for suffix, template in _TRIAD_TEMPLATES:
                score = _score_template(hist, template, root_pc)
                if score > best_score:
                    best_score = score
                    best_symbol = f"{_PC_TO_NAME[root_pc]}{suffix}"
        out.append(best_symbol)
        last = best_symbol
    return out


def _pitch_class_histograms(song: ReadSong) -> list[list[float]]:
    bars: list[list[float]] = [[0.0] * 12 for _ in range(song.num_bars)]
    for t in song.tracks:
        if t.is_drum:
            continue
        for n in t.notes:
            if 0 <= n.bar < song.num_bars:
                bars[n.bar][n.pitch % 12] += max(n.dur, 0.05)
    return bars


def _score_template(hist: list[float], template: frozenset[int], root_pc: int) -> float:
    """Chord-tone mass minus out-of-template mass. Fraction, in [-1, 1].
    Rewards tight chord-tone concentration and penalises alien pitch classes."""
    total = sum(hist) or 1.0
    on = 0.0
    off = 0.0
    for pc, mass in enumerate(hist):
        if (pc - root_pc) % 12 in template:
            on += mass
        else:
            off += mass
    return (on - off) / total


# ---------------------------------------------------------------------------
# Drum pattern — canonical GM drum keys → channels
# ---------------------------------------------------------------------------


GM_DRUM_CHANNELS: dict[str, set[int]] = {
    "kick": {35, 36},
    "snare": {38, 40, 37},
    "closed_hihat": {42, 44},
    "open_hihat": {46},
    "ride": {51, 59, 53},
    "crash": {49, 57, 55},
    "tom_low": {41, 43, 45},
    "tom_mid": {47, 48},
    "tom_high": {50},
    "clap": {39},
    "perc": {56, 58, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81},
}


def extract_drum_pattern(song: ReadSong, subdivision: int = 16) -> dict[str, str]:
    """Per canonical drum channel, a string of length `num_bars * subdivision`
    where 'x' marks a hit at that grid position and '.' means silence. Bars
    concatenate. When there is no drum track, returns {}.

    `subdivision` is steps per bar (16 = sixteenths in 4/4, common enough for
    most modern grooves; use 12 for triplet-heavy styles at call time)."""
    drum_tracks = [t for t in song.tracks if t.is_drum]
    if not drum_tracks:
        return {}
    bpb = _beats_per_bar(song.time_signature)
    step_per_beat = subdivision / bpb
    steps_total = song.num_bars * subdivision

    grids: dict[str, list[str]] = {name: ["."] * steps_total for name in GM_DRUM_CHANNELS}
    for t in drum_tracks:
        for n in t.notes:
            channel = _classify_drum_pitch(n.pitch)
            if channel is None:
                continue
            step = n.bar * subdivision + int(round(n.start_beat * step_per_beat))
            if 0 <= step < steps_total:
                grids[channel][step] = "x"
    # Drop always-silent channels so the caller doesn't drown in "."-only rows.
    return {name: "".join(row) for name, row in grids.items() if "x" in row}


def _classify_drum_pitch(pitch: int) -> Optional[str]:
    for name, keys in GM_DRUM_CHANNELS.items():
        if pitch in keys:
            return name
    return None


def extract_density_by_role(song: ReadSong) -> dict[str, float]:
    """Notes per bar, keyed by GM role (drums, bass, guitar, ...). Notes across
    tracks of the same role are summed; drums count all pitches. Used to match
    a corpus track's texture to a session's target energy at retrieval time."""
    if song.num_bars <= 0:
        return {}
    by_role: dict[str, int] = {}
    for t in song.tracks:
        role = program_role(t.program, t.is_drum)
        by_role[role] = by_role.get(role, 0) + len(t.notes)
    return {role: count / song.num_bars for role, count in by_role.items()}
