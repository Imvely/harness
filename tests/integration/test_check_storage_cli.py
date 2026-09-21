"""Integration tests for scripts/check_storage.py.

The point of the command is the *message*, so these run it as a subprocess and read what a
person would see: does a missing variable get named, does a wrong key prefix get told apart
from an unreachable store, and does the exit code let a launch script stop early.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_storage.py"

pytestmark = pytest.mark.integration


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PAD_REPO_ROOT": str(ROOT)}
    environment.pop("PAD_LMDB_PATH", None)
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env=environment,
    )


def test_a_reachable_dataset_exits_zero() -> None:
    result = _run(
        "--storage",
        "local",
        "--dataset-id",
        "synthetic_a",
        env={"PAD_DATA_ROOT": str(ROOT / "data" / "processed")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MEDIA_READABLE" in result.stdout


def test_an_unset_variable_exits_one_and_names_the_variable() -> None:
    # Exit 1 rather than 0 is what lets a launch script stop before queueing on the GPU.
    result = _run("--storage", "lmdb", "--dataset-id", "synthetic_a")
    assert result.returncode == 1
    assert "PAD_LMDB_PATH" in result.stdout
    assert "export PAD_LMDB_PATH=" in result.stdout


def test_an_unknown_storage_name_lists_the_real_ones() -> None:
    result = _run("--storage", "lmbd")  # a plausible typo
    assert result.returncode == 2
    assert "lmdb" in result.stdout and "local" in result.stdout


def test_the_json_form_is_machine_readable() -> None:
    result = _run(
        "--storage",
        "local",
        "--dataset-id",
        "synthetic_a",
        "--json",
        env={"PAD_DATA_ROOT": str(ROOT / "data" / "processed")},
    )
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    names = [check["name"] for check in payload["reports"][0]["checks"]]
    assert names == ["BACKEND_REACHABLE", "MANIFEST_READABLE", "MEDIA_READABLE"]


def test_the_experiment_form_checks_every_dataset_its_protocol_names() -> None:
    # A protocol with three source datasets and one target has four ways to be misconfigured;
    # checking only the one the user happened to name would miss three of them.
    result = _run(
        "--exp",
        "syn_e02_video_source_only",
        "--json",
        env={"PAD_DATA_ROOT": str(ROOT / "data" / "processed")},
    )
    payload = json.loads(result.stdout)
    assert [report["dataset_id"] for report in payload["reports"]] == [
        "synthetic_a",
        "synthetic_b",
    ]
