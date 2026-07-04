"""Index the Lakh MIDI (matched) dataset into a parquet of 8-bar segments.

Each MIDI is: read via `read_midi`, keyed by `extract_key`, chorded by
`extract_progression` (heuristic), and split into 8-bar windows. Genre comes
from the Tagtraum MSD annotation file if present.

Costly (~45k files × ~150 ms of parsing/analysis on one core). We parallelise
with `multiprocessing.Pool`. Runs once, cached, doesn't repeat.

Run: `python -m music_assistant.corpus.lakh_index --workers 8`
"""

from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Iterable, Optional

from ..music.read_midi import (
    extract_density_by_role,
    extract_key,
    extract_progression,
    program_role,
    read_midi,
)

APP_ROOT = Path(__file__).resolve().parents[2]
LAKH_ROOT_DEFAULT = APP_ROOT / "data" / "lakh"
INDEX_ROOT = APP_ROOT / "data" / "index"

SEGMENT_BARS = 8


def _load_tagtraum(lakh_root: Path) -> dict[str, str]:
    """MSD_track_id -> majority genre. The `msd_tagtraum_cd2c.cls` file has
    tab-separated lines: `TRACKID<tab>MAJOR<tab>MINOR?`. Missing → {}."""
    for name in ("msd_tagtraum_cd2c.cls", "msd_tagtraum_cd2.cls"):
        p = lakh_root / name
        if p.exists():
            return _parse_cls(p)
    matches = list(lakh_root.rglob("msd_tagtraum_*.cls"))
    if matches:
        return _parse_cls(matches[0])
    return {}


def _parse_cls(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            out[parts[0].strip()] = parts[1].strip().lower()
    return out


def _iter_midis(lakh_root: Path) -> Iterable[tuple[str, Path]]:
    # LMD-matched layout: lakh/lmd_matched/<A>/<B>/<C>/<TRACKID>/<hash>.mid
    for mid in lakh_root.rglob("*.mid"):
        parts = mid.parts
        # parent directory name is the MSD track id (starts with 'TR').
        track_id = ""
        for p in reversed(parts):
            if p.startswith("TR"):
                track_id = p
                break
        yield track_id, mid


def _process_one(args_tuple: tuple[str, str, str]) -> list[dict]:
    track_id, midi_path, genre = args_tuple
    try:
        song = read_midi(midi_path)
    except Exception:
        return []
    if song.num_bars < SEGMENT_BARS:
        return []
    key = extract_key(song)
    progression = extract_progression(song)
    density = extract_density_by_role(song)
    gm_programs = sorted({t.program for t in song.tracks if not t.is_drum})
    roles = sorted({program_role(t.program, t.is_drum) for t in song.tracks})

    rows: list[dict] = []
    for start in range(0, song.num_bars - SEGMENT_BARS + 1, SEGMENT_BARS):
        end = start + SEGMENT_BARS
        rows.append(
            {
                "track_id": track_id,
                "genre": genre or "unknown",
                "key": key,
                "tempo": song.tempo_bpm,
                "time_sig_num": song.time_signature[0],
                "time_sig_den": song.time_signature[1],
                "bar_start": start,
                "bar_end": end,
                "progression": progression[start:end],
                "density_by_role": density,
                "gm_programs": gm_programs,
                "roles": roles,
            }
        )
    return rows


def build_index(lakh_root: Path, out_path: Path, workers: int = 4, limit: Optional[int] = None) -> int:
    tagtraum = _load_tagtraum(lakh_root)
    tasks = []
    for track_id, mid in _iter_midis(lakh_root):
        genre = tagtraum.get(track_id, "")
        tasks.append((track_id, str(mid), genre))
        if limit is not None and len(tasks) >= limit:
            break

    all_rows: list[dict] = []
    if workers <= 1:
        for t in tasks:
            all_rows.extend(_process_one(t))
    else:
        with Pool(processes=workers) as pool:
            for rows in pool.imap_unordered(_process_one, tasks, chunksize=32):
                all_rows.extend(rows)

    _write_index(all_rows, out_path)
    return len(all_rows)


def _write_index(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        cols = _to_arrow_columns(rows)
        pq.write_table(pa.table(cols), out_path.with_suffix(".parquet"))
    except Exception:
        jsonl_path = out_path.with_suffix(".jsonl")
        with jsonl_path.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")


def _to_arrow_columns(rows: list[dict]) -> dict[str, list]:
    if not rows:
        return {}
    keys = list(rows[0].keys())
    cols: dict[str, list] = {k: [] for k in keys}
    for r in rows:
        for k in keys:
            v = r.get(k)
            if isinstance(v, (dict, list)):
                cols[k].append(json.dumps(v))
            else:
                cols[k].append(v)
    return cols


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(LAKH_ROOT_DEFAULT))
    parser.add_argument("--out", default=str(INDEX_ROOT / "lakh_segments"))
    parser.add_argument("--workers", type=int, default=max(1, cpu_count() // 2))
    parser.add_argument("--limit", type=int, default=None, help="cap number of MIDIs (debug)")
    args = parser.parse_args()

    count = build_index(Path(args.root), Path(args.out), workers=args.workers, limit=args.limit)
    print(f"indexed {count} lakh segments -> {args.out}.(parquet|jsonl) using {args.workers} workers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
