"""Index the Magenta Groove MIDI Dataset into a parquet of drum patterns.

Groove ships an `info.csv` with per-file style/bpm/time_signature/type. We read
each `.mid` with our `read_midi`, extract a compact grid string per drum channel
using `extract_drum_pattern`, and store one row per file. The runtime retriever
(`retrieve.retrieve_groove`) filters this table by style + bpm proximity.

Run: `python -m music_assistant.corpus.groove_index`
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional

from ..music.read_midi import extract_drum_pattern, read_midi

APP_ROOT = Path(__file__).resolve().parents[2]
GROOVE_ROOT_DEFAULT = APP_ROOT / "data" / "groove"
INDEX_ROOT = APP_ROOT / "data" / "index"


def _find_info_csv(root: Path) -> Optional[Path]:
    # Groove archive unpacks into a `groove/` subdir with `info.csv`.
    for cand in [root / "info.csv", root / "groove" / "info.csv"]:
        if cand.exists():
            return cand
    matches = list(root.rglob("info.csv"))
    return matches[0] if matches else None


def _parse_time_sig(raw: str) -> tuple[int, int]:
    try:
        n, d = raw.split("-")
        return int(n), int(d)
    except Exception:
        return (4, 4)


def build_index(groove_root: Path, out_path: Path) -> int:
    info = _find_info_csv(groove_root)
    if info is None:
        raise FileNotFoundError(
            f"Groove info.csv not under {groove_root}. Run `python -m scripts.fetch_corpora --groove`."
        )
    base = info.parent
    rows: list[dict] = []
    with info.open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            midi_path = r.get("midi_filename") or r.get("midi_file") or ""
            if not midi_path:
                continue
            full = base / midi_path
            if not full.exists():
                continue
            try:
                song = read_midi(str(full))
            except Exception:
                continue
            pattern = extract_drum_pattern(song, subdivision=16)
            if not pattern:
                continue
            style = (r.get("style") or "").split("/", 1)[0].strip() or "unknown"
            bpm = _safe_float(r.get("bpm"), 0.0)
            ts = _parse_time_sig(r.get("time_signature", "4-4"))
            row_type = (r.get("beat_type") or r.get("type") or "beat").strip()
            rows.append(
                {
                    "path": str(full.relative_to(base)),
                    "style": style,
                    "bpm": bpm,
                    "time_sig_num": ts[0],
                    "time_sig_den": ts[1],
                    "type": row_type,
                    "num_bars": song.num_bars,
                    "pattern_by_channel": pattern,
                }
            )
    _write_index(rows, out_path)
    return len(rows)


def _safe_float(raw: Optional[str], default: float) -> float:
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _write_index(rows: list[dict], out_path: Path) -> None:
    """Prefer parquet when pyarrow is available; fall back to JSON-lines otherwise.
    JSONL is enough for the small Groove index (~1000 rows) and keeps the corpus
    module dependency-light for dev environments without pyarrow."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pyarrow as pa  # noqa: F401
        import pyarrow.parquet as pq
        table = _rows_to_arrow(rows)
        pq.write_table(table, out_path.with_suffix(".parquet"))
    except Exception:
        jsonl_path = out_path.with_suffix(".jsonl")
        with jsonl_path.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")


def _rows_to_arrow(rows: list[dict]):
    import pyarrow as pa
    if not rows:
        return pa.table({})
    keys = list(rows[0].keys())
    cols = {k: [r.get(k) for r in rows] for k in keys}
    # pattern_by_channel is a dict — arrow can store it as a string-map struct,
    # but the safest cross-version option is a JSON-encoded string column.
    if "pattern_by_channel" in cols:
        cols["pattern_by_channel"] = [json.dumps(v) for v in cols["pattern_by_channel"]]
    return pa.table(cols)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(GROOVE_ROOT_DEFAULT))
    parser.add_argument("--out", default=str(INDEX_ROOT / "groove_patterns"))
    args = parser.parse_args()

    out_path = Path(args.out)
    count = build_index(Path(args.root), out_path)
    print(f"indexed {count} groove files -> {out_path}.(parquet|jsonl)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
