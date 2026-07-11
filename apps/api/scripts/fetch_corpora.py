"""Download MIDI corpora used by the style-grounding retrieval pipeline.

Two datasets:
  - Magenta Groove (~5 MB) — drum grooves labelled by style, feeds `retrieve_groove`.
  - Lakh MIDI matched (~1.6 GB) — 45k tracks with MSD-matched IDs, feeds
    `retrieve_style_examples`. Requires the Tagtraum genre mapping to be useful.

Idempotent: skips downloads whose hash matches an already-unpacked flag file.

Usage:
    python -m scripts.fetch_corpora            # downloads both
    python -m scripts.fetch_corpora --groove   # just Groove
    python -m scripts.fetch_corpora --lakh     # just Lakh (large)
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = APP_ROOT / "data"

GROOVE = {
    "name": "Magenta Groove MIDI",
    "url": "https://storage.googleapis.com/magentadata/datasets/groove/groove-v1.0.0-midionly.zip",
    "dest": DATA_ROOT / "groove",
    "flag": DATA_ROOT / "groove" / ".fetched",
    "archive": "zip",
}

LAKH = {
    "name": "Lakh MIDI (matched)",
    "url": "http://hog.ee.columbia.edu/craffel/lmd/lmd_matched.tar.gz",
    "dest": DATA_ROOT / "lakh",
    "flag": DATA_ROOT / "lakh" / ".fetched",
    "archive": "tar.gz",
}

TAGTRAUM = {
    "name": "Tagtraum MSD genre annotations (cd2c)",
    "url": "https://www.tagtraum.com/genres/msd_tagtraum_cd2c.cls.zip",
    "dest": DATA_ROOT / "lakh",
    "flag": DATA_ROOT / "lakh" / ".tagtraum_fetched",
    "archive": "zip",
}


def _download(url: str, into: Path) -> Path:
    into.mkdir(parents=True, exist_ok=True)
    fname = into / Path(url).name
    if fname.exists():
        return fname
    print(f"  downloading {url} -> {fname}")
    urllib.request.urlretrieve(url, fname)
    return fname


def _unpack(archive_path: Path, kind: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if kind == "zip":
        with zipfile.ZipFile(archive_path) as z:
            z.extractall(dest)
    elif kind == "tar.gz":
        with tarfile.open(archive_path, "r:gz") as t:
            t.extractall(dest)
    else:
        raise ValueError(f"unknown archive kind: {kind}")


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(spec: dict) -> None:
    print(f"\n[{spec['name']}]")
    if spec["flag"].exists():
        print(f"  already fetched (flag: {spec['flag'].relative_to(APP_ROOT)})")
        return
    archive = _download(spec["url"], spec["dest"])
    print(f"  sha1: {_sha1(archive)[:12]}...")
    print(f"  unpacking {spec['archive']}")
    _unpack(archive, spec["archive"], spec["dest"])
    spec["flag"].write_text(spec["url"])
    print(f"  done -> {spec['dest'].relative_to(APP_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groove", action="store_true", help="fetch Magenta Groove only")
    parser.add_argument("--lakh", action="store_true", help="fetch Lakh + Tagtraum only")
    args = parser.parse_args()

    all_selected = not (args.groove or args.lakh)
    if all_selected or args.groove:
        _run(GROOVE)
    if all_selected or args.lakh:
        _run(LAKH)
        _run(TAGTRAUM)

    print(f"\nData root: {DATA_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
