"""Integration tests for scripts/validate_spec.py."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_spec.py"
FIXTURE_CONFIGS = ROOT / "tests" / "fixtures" / "configs"

pytestmark = pytest.mark.integration


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _copy_tree(ROOT / "configs", root / "configs")
    _copy_tree(ROOT / "data" / "manifests", root / "data" / "manifests")
    (root / "experiments" / "specs").mkdir(parents=True)
    return root


def _run(tmp_repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PAD_REPO_ROOT": str(tmp_repo),
        "PAD_DATA_ROOT": str(tmp_repo / "data" / "processed"),
        "PAD_REGISTRY_PATH": str(tmp_repo / "experiments" / "registry.jsonl"),
        "PAD_OUTPUT_ROOT": str(tmp_repo / "outputs"),
        "MLFLOW_TRACKING_URI": f"sqlite:///{tmp_repo / 'mlruns.db'}",
        "MLFLOW_DISABLE_AGENT_HINT": "1",
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _json(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert proc.stdout.strip(), proc.stderr
    data = json.loads(proc.stdout)
    assert isinstance(data, dict)
    return data


def test_validate_cli_exit_code_zero_and_json_schema(tmp_repo: Path) -> None:
    proc = _run(tmp_repo, "--exp", "syn_e02_video_source_only", "--json")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = _json(proc)
    assert data["ok"] is True
    assert data["exit_code"] == 0
    assert data["experiment_id"] == "exp_syn_e02_video_source_only"
    assert data["mode"] == "smoke"
    assert len(data["science_hash"]) == 64
    assert len(data["spec_hash"]) == 64
    assert data["protocol_id"] == "syn_a_to_b_bf_adapt_v1"
    assert len(data["protocol_hash"]) == 64
    assert data["tracking_uri_scheme"] == "sqlite"
    assert data["gate"] is None


def test_validate_cli_exit_code_two_for_spec_error(tmp_repo: Path) -> None:
    proc = _run(tmp_repo, "--exp", "does_not_exist", "--json")
    assert proc.returncode == 2
    data = _json(proc)
    assert data["ok"] is False
    assert data["exit_code"] == 2
    assert data["errors"]


def test_validate_cli_exit_code_three_for_protocol_error(tmp_repo: Path) -> None:
    proc = _run(
        tmp_repo,
        "--exp",
        "syn_e02_video_source_only",
        "--json",
        "--",
        "protocol.target_adaptation.total_samples=999999",
    )
    assert proc.returncode == 3
    data = _json(proc)
    assert data["ok"] is False
    assert data["exit_code"] == 3
    assert any("ADAPT_INSUFFICIENT_CANDIDATES" in e for e in data["errors"])


def test_validate_cli_exit_code_four_for_gate_denial(tmp_repo: Path) -> None:
    proc = _run(
        tmp_repo,
        "--exp",
        "full_cpu_ok",
        "--config-dir",
        str(FIXTURE_CONFIGS),
        "--for-launch",
        "--json",
    )
    assert proc.returncode == 4
    data = _json(proc)
    assert data["ok"] is False
    assert data["exit_code"] == 4
    assert data["gate"]["allowed"] is False
    assert "SPEC_FROZEN" in data["gate"]["checks"]


def test_validate_cli_freeze_writes_tmp_resolved_spec_without_absolute_paths(
    tmp_repo: Path,
) -> None:
    proc = _run(tmp_repo, "--exp", "syn_e01_frame_source_only", "--freeze", "--json")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = _json(proc)
    frozen_path = Path(data["frozen_path"])
    assert frozen_path == tmp_repo / "experiments" / "specs" / (
        "exp_syn_e01_frame_source_only.resolved.yaml"
    )
    assert frozen_path.is_file()
    text = frozen_path.read_text(encoding="utf-8")
    assert "/home/" not in text
    assert str(ROOT) not in text
    assert "science_hash:" in text
    assert "spec_hash:" in text


def test_validate_cli_full_mode_cli_override_is_spec_or_gate_error(tmp_repo: Path) -> None:
    proc = _run(
        tmp_repo,
        "--exp",
        "syn_e02_video_source_only",
        "--for-launch",
        "--json",
        "--",
        "execution.mode=full",
    )
    assert proc.returncode in {2, 4}
    data = _json(proc)
    assert data["ok"] is False
    assert data["exit_code"] in {2, 4}
