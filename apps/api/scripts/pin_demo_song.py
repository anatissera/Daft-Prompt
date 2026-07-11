"""Pin a composed song to one or more demo prompts.

Usage (from apps/api):
    .venv/bin/python scripts/pin_demo_song.py <job_id> "una cancion de rock" ["una de rock" ...]
    .venv/bin/python scripts/pin_demo_song.py --list

After pinning, a compose request whose prompt matches any of the phrasings
(accents/case/punctuation ignored) replays the stored song instantly instead
of running the pipeline. The mapping lives in outputs/demo_cache.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from music_assistant.infrastructure.storage import demo_cache  # noqa: E402

OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"


def main() -> int:
    args = sys.argv[1:]
    if args == ["--list"]:
        print(json.dumps(demo_cache.load(OUTPUTS), ensure_ascii=False, indent=2))
        return 0
    if len(args) < 2:
        print(__doc__)
        return 1
    job_id, prompts = args[0], args[1:]
    if not (OUTPUTS / job_id / "song.json").is_file():
        print(f"error: {OUTPUTS / job_id / 'song.json'} not found — is that a real job_id?")
        return 1
    cache = demo_cache.pin(OUTPUTS, job_id, prompts)
    print(f"pinned {len(prompts)} prompt(s) -> {job_id}; cache now has {len(cache)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
