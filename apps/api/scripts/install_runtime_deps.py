"""Install the runtime dependency set selected by the API Docker image.

Keeps the Docker cache layer tied to ``pyproject.toml`` rather than application
source files. The editable package itself is installed after source is copied.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path


def requirements_for(extras: list[str]) -> list[str]:
    manifest = tomllib.loads(Path("pyproject.toml").read_text())
    project = manifest["project"]
    requirements = list(project["dependencies"])
    optional = project.get("optional-dependencies", {})
    unknown = [extra for extra in extras if extra not in optional]
    if unknown:
        raise ValueError(f"Unknown optional dependency group(s): {', '.join(unknown)}")
    for extra in extras:
        requirements.extend(optional[extra])
    return requirements


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("extras", nargs="*", help="optional dependency groups to include")
    parser.add_argument("--print", action="store_true", dest="print_only")
    args = parser.parse_args()
    requirements = requirements_for(args.extras)
    if args.print_only:
        print("\n".join(requirements))
        return
    subprocess.check_call([sys.executable, "-m", "pip", "install", *requirements])


if __name__ == "__main__":
    main()
