"""Unit tests for the local append-only run registry."""

from __future__ import annotations

from pathlib import Path

from pad_research.experiments.registry import Registry, RegistryRow, utc_now
from pad_research.experiments.status import RunStatus


def _row(
    *,
    exp_id: str = "exp_a",
    science_hash: str = "s" * 64,
    protocol_hash: str = "p" * 64,
    mode: str = "smoke",
    status: RunStatus = RunStatus.smoke_ok,
    git_sha: str | None = "a" * 40,
    run_id: str = "run",
) -> RegistryRow:
    now = utc_now()
    return RegistryRow(
        exp_id=exp_id,
        seed=7,
        mode=mode,
        science_hash=science_hash,
        spec_hash="x" * 64,
        protocol_id="proto_v1",
        protocol_hash=protocol_hash,
        mlflow_run_id=run_id,
        status=status,
        git_sha=git_sha,
        git_dirty=False,
        started_at=now,
        finished_at=now,
    )


def test_append_and_query(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "registry.jsonl")
    first = _row(exp_id="exp_a", run_id="run-a")
    second = _row(exp_id="exp_b", protocol_hash="q" * 64, run_id="run-b")
    registry.append(first)
    registry.append(second)
    assert registry.rows() == [first, second]
    assert registry.find_runs(exp_id="exp_a") == [first]
    assert registry.find_runs(protocol_hash="q" * 64) == [second]
    assert registry.find_runs(mode="full") == []


def test_failed_run_is_kept(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "registry.jsonl")
    failed = _row(status=RunStatus.failed_training, mode="full", run_id="failed")
    ok = _row(status=RunStatus.smoke_ok, mode="smoke", run_id="ok")
    registry.append(failed)
    registry.append(ok)
    rows = registry.rows()
    assert rows == [failed, ok]
    assert registry.find_runs(status={RunStatus.failed_training}) == [failed]


def test_latest_success_smoke_filters_by_git_sha(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "registry.jsonl")
    sh = "s" * 64
    old = _row(science_hash=sh, git_sha="a" * 40, run_id="old")
    other_git = _row(science_hash=sh, git_sha="b" * 40, run_id="other")
    failed = _row(
        science_hash=sh,
        git_sha="a" * 40,
        run_id="failed",
        status=RunStatus.failed_training,
    )
    latest = _row(science_hash=sh, git_sha="a" * 40, run_id="latest")
    for row in (old, other_git, failed, latest):
        registry.append(row)
    assert registry.latest_success_smoke(sh, "a" * 40) == latest
    assert registry.latest_success_smoke(sh, "b" * 40) == other_git
    assert registry.latest_success_smoke(sh, None) == latest
    assert registry.latest_success_smoke("missing", "a" * 40) is None
