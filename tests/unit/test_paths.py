"""Tests for environment-overridable repository paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from pad_research import paths


def test_repo_root_default_is_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAD_REPO_ROOT", raising=False)
    root = paths.repo_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "pad_research").is_dir()


def test_repo_root_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PAD_REPO_ROOT", str(tmp_path))
    assert paths.repo_root() == tmp_path.resolve()
    assert paths.configs_dir() == tmp_path.resolve() / "configs"
    assert paths.manifests_dir() == tmp_path.resolve() / "data" / "manifests"
    assert paths.specs_dir() == tmp_path.resolve() / "experiments" / "specs"
    assert paths.approvals_dir() == tmp_path.resolve() / "experiments" / "approvals"
    assert paths.artifact_root() == tmp_path.resolve() / "mlruns_artifacts"


def test_registry_and_output_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PAD_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("PAD_REGISTRY_PATH", raising=False)
    monkeypatch.delenv("PAD_OUTPUT_ROOT", raising=False)
    assert paths.registry_path() == tmp_path.resolve() / "experiments" / "registry.jsonl"
    assert paths.output_root() == tmp_path.resolve() / "outputs"
    monkeypatch.setenv("PAD_REGISTRY_PATH", str(tmp_path / "reg.jsonl"))
    monkeypatch.setenv("PAD_OUTPUT_ROOT", str(tmp_path / "out"))
    assert paths.registry_path() == tmp_path / "reg.jsonl"
    assert paths.output_root() == tmp_path / "out"


def test_data_root_requires_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PAD_DATA_ROOT", raising=False)
    with pytest.raises(paths.DataRootNotConfiguredError):
        paths.data_root()
    monkeypatch.setenv("PAD_DATA_ROOT", str(tmp_path))
    assert paths.data_root() == tmp_path
    monkeypatch.setenv("OTHER_ROOT", str(tmp_path / "x"))
    assert paths.data_root("OTHER_ROOT") == tmp_path / "x"


def test_tracking_uri(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PAD_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    assert paths.default_tracking_uri() == f"sqlite:///{tmp_path.resolve()}/mlruns.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    assert paths.default_tracking_uri() == "http://localhost:5000"
