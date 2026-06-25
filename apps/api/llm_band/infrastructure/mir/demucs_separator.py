"""Demucs stem-separation adapter."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote, urlparse

from llm_band.domain.audio_profile import ReferenceSource
from llm_band.ports.stem_separator import SeparatedStem


CommandRunner = Callable[[list[str]], object]


class DemucsSeparator:
    def __init__(
        self,
        output_root: Path | str,
        model_name: str = "htdemucs",
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.model_name = model_name
        self._command_runner = command_runner or self._run_command

    def separate(self, source: ReferenceSource) -> list[SeparatedStem]:
        source_path = self._resolve_local_path(source)
        stems_root = self.output_root / source.reference_id / "stems"
        stems_root.mkdir(parents=True, exist_ok=True)
        command = [
            "python",
            "-m",
            "demucs",
            "-n",
            self.model_name,
            "-o",
            str(stems_root),
            str(source_path),
        ]

        try:
            self._command_runner(command)
            return self._collect_stems(stems_root, source_path)
        except Exception:
            return [self._mix_fallback(source_path)]

    @staticmethod
    def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, check=True, capture_output=True, text=True)

    @staticmethod
    def _resolve_local_path(source: ReferenceSource) -> Path:
        if source.kind not in {"upload", "local"}:
            raise ValueError("Demucs separation requires a local audio path")

        parsed = urlparse(source.uri)
        if parsed.scheme in {"http", "https"}:
            raise ValueError("Demucs separation requires a local audio path")
        if parsed.scheme == "file":
            path = Path(unquote(parsed.path))
        elif parsed.scheme:
            raise ValueError("Demucs separation requires a local audio path")
        else:
            path = Path(source.uri).expanduser()

        if not path.exists():
            raise ValueError(f"Local audio path does not exist: {path}")
        return path

    def _collect_stems(self, stems_root: Path, source_path: Path) -> list[SeparatedStem]:
        source_stem = source_path.stem
        demucs_output = stems_root / self.model_name / source_stem
        roles = {
            "drums": "percussion",
            "bass": "bass",
            "vocals": "vocal",
            "other": "harmony",
        }
        stems: list[SeparatedStem] = []
        for name, role in roles.items():
            path = demucs_output / f"{name}.wav"
            if not path.exists():
                raise FileNotFoundError(f"Expected Demucs stem was not produced: {path}")
            stems.append(
                SeparatedStem(
                    name=name,
                    role=role,
                    path=str(path),
                    artifact_uri=None,
                    confidence=1.0,
                )
            )
        return stems

    @staticmethod
    def _mix_fallback(source_path: Path) -> SeparatedStem:
        return SeparatedStem(
            name="mix",
            role="mix",
            path=str(source_path),
            artifact_uri=None,
            confidence=0.25,
        )
