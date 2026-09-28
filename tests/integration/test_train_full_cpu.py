"""Slow CPU full-run integration tests for the launch gate and determinism."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from pad_research.experiments.registry import RegistryRow
from pad_research.experiments.status import RunStatus

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "scripts" / "train.py"
VALIDATE = ROOT / "scripts" / "validate_spec.py"
APPROVE = ROOT / "scripts" / "approve_full_run.py"
PREPARE = ROOT / "scripts" / "prepare_dataset.py"
FULL_FIXTURE = ROOT / "tests" / "fixtures" / "configs" / "exp" / "full_cpu_ok.yaml"

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def _prepare_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(ROOT / "configs", repo / "configs")
    shutil.copy2(FULL_FIXTURE, repo / "configs" / "exp" / "full_cpu_ok.yaml")
    (repo / "experiments" / "specs").mkdir(parents=True)
    (repo / "data" / "manifests").mkdir(parents=True)
    (repo / "README.md").write_text("fixture repo\n", encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    env = {
        **os.environ,
        "PAD_REPO_ROOT": str(repo),
        "PAD_DATA_ROOT": str(repo / "data" / "processed"),
        "PAD_REGISTRY_PATH": str(repo / "experiments" / "registry.jsonl"),
        "PAD_OUTPUT_ROOT": str(repo / "outputs"),
        "MLFLOW_TRACKING_URI": f"sqlite:///{repo / 'mlruns.db'}",
        "MLFLOW_DISABLE_AGENT_HINT": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    prep = subprocess.run(
        [
            sys.executable,
            str(PREPARE),
            "--adapter",
            "synthetic",
            "--dataset-id",
            "synthetic_a",
            "--dataset-id",
            "synthetic_b",
            "--root",
            env["PAD_DATA_ROOT"],
            "--manifests-dir",
            str(repo / "data" / "manifests"),
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert prep.returncode == 0, prep.stderr + prep.stdout
    return repo, env


def _run(env: dict[str, str], script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _rows(repo: Path) -> list[RegistryRow]:
    path = repo / "experiments" / "registry.jsonl"
    return [
        RegistryRow.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _metrics(row: RegistryRow) -> dict[str, float]:
    assert row.results_dir is not None
    payload = json.loads((Path(row.results_dir) / "eval_test.json").read_text("utf-8"))
    metrics = payload["metrics"]
    return {key: float(metrics[key]) for key in ("apcer", "bpcer", "acer", "hter", "auc")}


def test_full_mode_cpu_fixture_runs_two_epochs_and_is_deterministic(tmp_path: Path) -> None:
    repo, env = _prepare_repo(tmp_path)
    frozen = _run(env, VALIDATE, "--exp", "full_cpu_ok", "--freeze", "--json")
    assert frozen.returncode == 0, frozen.stderr + frozen.stdout

    smoke = _run(env, TRAIN, "+exp=full_cpu_ok", "execution.mode=smoke")
    assert smoke.returncode == 0, smoke.stderr + smoke.stdout

    approved = _run(env, APPROVE, "--exp", "full_cpu_ok")
    assert approved.returncode == 0, approved.stderr + approved.stdout

    first = _run(env, TRAIN, "+exp=full_cpu_ok")
    assert first.returncode == 0, first.stderr + first.stdout
    first_row = _rows(repo)[-1]
    assert first_row.status == RunStatus.success
    assert first_row.results_dir is not None
    first_curve = (Path(first_row.results_dir) / "training_curves.csv").read_text("utf-8")
    assert "1," in first_curve and "2," in first_curve

    second = _run(env, TRAIN, "+exp=full_cpu_ok")
    assert second.returncode == 0, second.stderr + second.stdout
    second_row = _rows(repo)[-1]
    assert second_row.status == RunStatus.success

    a = _metrics(first_row)
    b = _metrics(second_row)
    for key in a:
        assert np.isclose(a[key], b[key], atol=1e-6), key
