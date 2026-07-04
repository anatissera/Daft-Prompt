"""Demucs stem-separation adapter."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import unicodedata
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote, urlparse

from music_assistant.domain.audio_profile import ReferenceSource
from music_assistant.ports.stem_separator import SeparatedStem


CommandRunner = Callable[[list[str]], object]
CACHE_FORMAT_VERSION = "stems-v1"
STEM_ROLES = {
    "drums": "percussion",
    "bass": "bass",
    "vocals": "vocal",
    "other": "harmony",
}


class DemucsSeparator:
    def __init__(
        self,
        output_root: Path | str,
        model_name: str = "htdemucs",
        command_runner: CommandRunner | None = None,
        cache_enabled: bool = False,
        cache_root: Path | str | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.model_name = model_name
        self._command_runner = command_runner or self._run_command
        self.cache_enabled = cache_enabled
        self.cache_root = Path(cache_root) if cache_root is not None else self.output_root / ".stem-cache"
        self.last_cache_hit = False

    def separate(self, source: ReferenceSource) -> list[SeparatedStem]:
        source_path = self._resolve_local_path(source)
        self.last_cache_hit = False
        if self.cache_enabled:
            cached = self._collect_flat_stems(self.cache_path_for(source_path))
            if cached is not None:
                self.last_cache_hit = True
                return cached
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
            stems = self._collect_stems(stems_root, source_path)
            if self.cache_enabled:
                self._populate_cache(source_path, stems)
            return stems
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
        stems: list[SeparatedStem] = []
        for name, role in STEM_ROLES.items():
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

    def cache_path_for(self, source_path: Path) -> Path:
        normalized_name = unicodedata.normalize("NFKC", source_path.name).casefold()
        identity = (
            f"{normalized_name}:{source_path.stat().st_size}:"
            f"{self.model_name}:{CACHE_FORMAT_VERSION}"
        )
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        return self.cache_root / key

    def _collect_flat_stems(self, root: Path) -> list[SeparatedStem] | None:
        stems: list[SeparatedStem] = []
        for name, role in STEM_ROLES.items():
            path = root / f"{name}.wav"
            if not path.is_file() or path.stat().st_size <= 0:
                return None
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

    def _populate_cache(
        self, source_path: Path, stems: list[SeparatedStem]
    ) -> None:
        destination = self.cache_path_for(source_path)
        temporary = destination.with_name(f"{destination.name}.tmp")
        shutil.rmtree(temporary, ignore_errors=True)
        temporary.mkdir(parents=True, exist_ok=True)
        try:
            for stem in stems:
                shutil.copy2(stem.path, temporary / f"{stem.name}.wav")
            shutil.rmtree(destination, ignore_errors=True)
            temporary.replace(destination)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)

    @staticmethod
    def _mix_fallback(source_path: Path) -> SeparatedStem:
        return SeparatedStem(
            name="mix",
            role="mix",
            path=str(source_path),
            artifact_uri=None,
            confidence=0.25,
        )
