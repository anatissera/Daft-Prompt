"""Tests for the Demucs stem-separation adapter."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from llm_band.domain.audio_profile import ReferenceSource
from llm_band.infrastructure.mir.demucs_separator import DemucsSeparator
from llm_band.ports.stem_separator import SeparatedStem


def _source(uri: str, kind: str = "upload") -> ReferenceSource:
    return ReferenceSource(
        reference_id="ref_demo",
        kind=kind,
        label="demo.wav",
        uri=uri,
        authorized=True,
    )


def _write_expected_stems(root: Path, reference_id: str = "ref_demo") -> dict[str, Path]:
    stem_root = root / reference_id / "stems" / "htdemucs" / "demo"
    stem_root.mkdir(parents=True)
    paths = {
        "drums": stem_root / "drums.wav",
        "bass": stem_root / "bass.wav",
        "vocals": stem_root / "vocals.wav",
        "other": stem_root / "other.wav",
    }
    for path in paths.values():
        path.write_bytes(b"fake wav")
    return paths


def test_separated_stem_confidence_is_bounded():
    with pytest.raises(ValueError):
        SeparatedStem(name="mix", role="mix", path="/tmp/demo.wav", confidence=1.5)


def test_demucs_separator_resolves_plain_local_paths_and_maps_stems(tmp_path):
    audio_path = tmp_path / "demo.wav"
    audio_path.write_bytes(b"input")
    output_root = tmp_path / "outputs"
    expected_paths = _write_expected_stems(output_root)
    calls: list[list[str]] = []

    def runner(command: list[str]) -> None:
        calls.append(command)

    separator = DemucsSeparator(output_root=output_root, command_runner=runner)

    stems = separator.separate(_source(str(audio_path)))

    assert calls == [
        [
            "python",
            "-m",
            "demucs",
            "-n",
            "htdemucs",
            "-o",
            str(output_root / "ref_demo" / "stems"),
            str(audio_path),
        ]
    ]
    assert [(stem.name, stem.role) for stem in stems] == [
        ("drums", "percussion"),
        ("bass", "bass"),
        ("vocals", "vocal"),
        ("other", "harmony"),
    ]
    assert [stem.path for stem in stems] == [str(expected_paths[name]) for name in ["drums", "bass", "vocals", "other"]]
    assert all(stem.confidence == 1.0 for stem in stems)


def test_demucs_separator_resolves_file_uris(tmp_path):
    audio_path = tmp_path / "demo.wav"
    audio_path.write_bytes(b"input")
    output_root = tmp_path / "outputs"
    _write_expected_stems(output_root)
    calls: list[list[str]] = []
    separator = DemucsSeparator(output_root=output_root, command_runner=lambda command: calls.append(command))

    stems = separator.separate(_source(audio_path.as_uri()))

    assert calls[0][-1] == str(audio_path)
    assert {stem.name for stem in stems} == {"drums", "bass", "vocals", "other"}


@pytest.mark.parametrize(
    ("kind", "uri"),
    [
        ("youtube", "https://youtube.example/watch?v=blocked"),
        ("direct_url", "https://example.com/audio.wav"),
        ("metadata", "spotify:track:demo"),
        ("upload", "https://example.com/uploaded.wav"),
    ],
)
def test_demucs_separator_rejects_remote_or_non_local_sources(tmp_path, kind, uri):
    separator = DemucsSeparator(output_root=tmp_path / "outputs")

    with pytest.raises(ValueError, match="local audio path"):
        separator.separate(_source(uri, kind=kind))


def test_demucs_separator_returns_mix_fallback_when_command_fails(tmp_path):
    audio_path = tmp_path / "demo.wav"
    audio_path.write_bytes(b"input")

    def failing_runner(command: list[str]) -> None:
        raise RuntimeError("demucs unavailable")

    separator = DemucsSeparator(output_root=tmp_path / "outputs", command_runner=failing_runner)

    stems = separator.separate(_source(str(audio_path)))

    assert stems == [
        SeparatedStem(
            name="mix",
            role="mix",
            path=str(audio_path),
            artifact_uri=None,
            confidence=0.25,
        )
    ]


def test_demucs_separator_returns_mix_fallback_when_outputs_are_missing(tmp_path):
    audio_path = tmp_path / "demo.wav"
    audio_path.write_bytes(b"input")
    separator = DemucsSeparator(output_root=tmp_path / "outputs", command_runner=lambda command: None)

    stems = separator.separate(_source(str(audio_path)))

    assert len(stems) == 1
    assert stems[0].name == "mix"
    assert stems[0].path == str(audio_path)


@pytest.mark.skipif(
    os.environ.get("LLMINEM_RUN_DEMUCS_TESTS") != "1",
    reason="real Demucs separation is slow and downloads model weights",
)
def test_demucs_separator_runs_real_demucs_when_enabled(tmp_path):
    pytest.importorskip("demucs")
    pytest.importorskip("soundfile")
    pytest.importorskip("numpy")
    import numpy as np
    import soundfile as sf

    sample_rate = 44100
    seconds = 1
    time = np.linspace(0.0, seconds, sample_rate * seconds, endpoint=False)
    signal = 0.1 * np.sin(2 * np.pi * 220 * time)
    audio_path = tmp_path / "tone.wav"
    sf.write(audio_path, signal, sample_rate)
    separator = DemucsSeparator(output_root=tmp_path / "outputs")

    stems = separator.separate(_source(str(audio_path)))

    assert {stem.name for stem in stems} == {"drums", "bass", "vocals", "other"}
    assert all(Path(stem.path).exists() for stem in stems)
