"""Smoke integration test for adapt.py."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import mlflow
import pytest

from pad_research.experiments.registry import RegistryRow

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "scripts" / "train.py"
ADAPT = ROOT / "scripts" / "adapt.py"
PREPARE = ROOT / "scripts" / "prepare_dataset.py"

pytestmark = pytest.mark.integration


def _prepare_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(ROOT / "configs", repo / "configs")
    (repo / "experiments" / "specs").mkdir(parents=True)
    (repo / "data" / "manifests").mkdir(parents=True)
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
        timeout=120,
        check=False,
    )


def _run_id(stdout: str) -> str:
    match = re.search(r"run_id=([0-9a-f]+)", stdout)
    assert match, stdout
    return match.group(1)


def _rows(repo: Path) -> list[RegistryRow]:
    path = repo / "experiments" / "registry.jsonl"
    return [
        RegistryRow.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_full_finetune_bf_only_writes_regression_check(tmp_path: Path) -> None:
    repo, env = _prepare_repo(tmp_path)
    source = _run(env, TRAIN, "+exp=syn_e02_video_source_only")
    assert source.returncode == 0, source.stderr + source.stdout
    source_run_id = _run_id(source.stdout)

    adapted = _run(
        env,
        ADAPT,
        "+exp=syn_e03_video_full_ft_bf_only",
        f"adaptation.source_run_id={source_run_id}",
    )
    assert adapted.returncode == 0, adapted.stderr + adapted.stdout
    adapted_run_id = _run_id(adapted.stdout)
    row = _rows(repo)[-1]
    assert row.mlflow_run_id == adapted_run_id
    assert row.results_dir is not None
    payload = json.loads((Path(row.results_dir) / "regression_check.json").read_text("utf-8"))
    assert payload["gate"]["verdict"] in {"pass", "security_regression"}
    assert payload["source_domain_delta"] is not None

    mlflow.set_tracking_uri(env["MLFLOW_TRACKING_URI"])
    run = mlflow.get_run(adapted_run_id)
    assert run.data.tags["status"] == "smoke_ok"
    assert run.data.tags["gate_verdict"] in {"pass", "security_regression"}
