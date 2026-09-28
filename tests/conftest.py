"""Repository-wide pytest fixtures.

Isolation policy (contract §17, coding-style rule): no test may write to the real
``experiments/registry.jsonl``, ``mlruns.db``, ``outputs/`` or ``experiments/specs``.
Every test gets a private tmp root for those via environment variables consumed by
``pad_research.paths``. Data lives in the real ``data/processed`` (synthetic, gitignored).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


@pytest.fixture(autouse=True)
def _isolated_run_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect every mutable run-state location to a per-test tmp directory."""
    monkeypatch.setenv("PAD_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("PAD_OUTPUT_ROOT", str(tmp_path / "outputs"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlruns.db'}")
    monkeypatch.setenv("MLFLOW_DISABLE_AGENT_HINT", "1")
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    if "PAD_DATA_ROOT" not in os.environ:
        monkeypatch.setenv("PAD_DATA_ROOT", str(REPO_ROOT / "data" / "processed"))


@pytest.fixture()
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def torch_single_thread():
    """Import torch lazily and pin it to one thread for deterministic CPU tests."""
    import torch

    torch.set_num_threads(1)
    return torch
