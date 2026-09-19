"""Smoke integration tests for train.py and evaluate.py."""

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
from pad_research.experiments.status import RunStatus

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "scripts" / "train.py"
EVALUATE = ROOT / "scripts" / "evaluate.py"
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


def test_train_frame_smoke_creates_run_artifacts_and_evaluate_matches(tmp_path: Path) -> None:
    repo, env = _prepare_repo(tmp_path)
    proc = _run(env, TRAIN, "+exp=syn_e01_frame_source_only")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    run_id = _run_id(proc.stdout)
    rows = _rows(repo)
    assert rows[-1].status == RunStatus.smoke_ok
    assert rows[-1].mlflow_run_id == run_id
    assert rows[-1].results_dir is not None
    run_dir = Path(rows[-1].results_dir)
    train_eval = json.loads((run_dir / "eval_test.json").read_text(encoding="utf-8"))
    assert (run_dir / "checkpoint.pt").is_file()
    assert train_eval["status"] == "smoke_ok"
    assert train_eval["metrics"]["n_bona_fide"] > 0

    mlflow.set_tracking_uri(env["MLFLOW_TRACKING_URI"])
    mlflow_run = mlflow.get_run(run_id)
    assert mlflow_run.data.tags["status"] == "smoke_ok"
    for metric in ("apcer", "bpcer", "acer", "hter", "auc"):
        assert metric in mlflow_run.data.metrics

    eval_proc = _run(
        env, EVALUATE, "+exp=syn_e01_frame_source_only", f"evaluation.checkpoint=mlflow:{run_id}"
    )
    assert eval_proc.returncode == 0, eval_proc.stderr + eval_proc.stdout
    eval_rows = _rows(repo)
    eval_dir = Path(eval_rows[-1].results_dir or "")
    eval_payload = json.loads((eval_dir / "eval_test.json").read_text(encoding="utf-8"))
    assert eval_payload["metrics"]["acer"] == pytest.approx(train_eval["metrics"]["acer"])
