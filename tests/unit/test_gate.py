"""Unit tests for the in-process full-run gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pad_research.config.compose import compose_spec
from pad_research.config.schema import ExperimentSpec, science_hash, spec_hash
from pad_research.experiments.approvals import (
    TOKEN_ENV_VAR,
    create_key,
    mint_pasteable,
    write_token,
)
from pad_research.experiments.gate import GpuInfo, check_full_run_gate, config_sources_ok
from pad_research.experiments.registry import Registry, RegistryRow, utc_now
from pad_research.experiments.status import RunStatus
from pad_research.experiments.validator import tracking_writable
from pad_research.protocols.hashing import protocol_hash
from pad_research.protocols.validator import validate_protocol
from pad_research.utils.git import GitState

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CONFIGS = ROOT / "tests" / "fixtures" / "configs"
GIT_SHA = "a" * 40


def _compose(exp_name: str, *, fixture: bool = False) -> ExperimentSpec:
    _, spec = compose_spec(
        [f"+exp={exp_name}"],
        extra_config_dir=FIXTURE_CONFIGS if fixture else None,
    )
    return spec


def _with_execution(spec: ExperimentSpec, **updates: Any) -> ExperimentSpec:
    data = spec.model_dump(mode="json")
    data["execution"].update(updates)
    return ExperimentSpec.model_validate(data)


def _git(*, dirty: bool = False, sha: str | None = GIT_SHA) -> GitState:
    short = sha[:12] if sha else None
    return GitState(sha=sha, short_sha=short, branch="main", dirty=dirty, untracked_count=0)


def _registry_with_smoke(
    tmp_path: Path, spec: ExperimentSpec, git_sha: str | None = GIT_SHA
) -> Registry:
    registry = Registry(tmp_path / "registry.jsonl")
    now = utc_now()
    registry.append(
        RegistryRow(
            exp_id=spec.experiment.id,
            seed=spec.training.seed,
            mode="smoke",
            science_hash=science_hash(spec),
            spec_hash=spec_hash(spec),
            protocol_id=spec.protocol.protocol_id,
            protocol_hash=protocol_hash(spec.protocol),
            mlflow_run_id="run-smoke",
            status=RunStatus.smoke_ok,
            git_sha=git_sha,
            git_dirty=False,
            started_at=now,
            finished_at=now,
        )
    )
    return registry


def _approve(tmp_path: Path, spec: ExperimentSpec) -> None:
    write_token(spec.experiment.id, science_hash(spec), GIT_SHA, tmp_path / "approvals")


def _gate(
    spec: ExperimentSpec,
    tmp_path: Path,
    *,
    registry: Registry | None = None,
    frozen: ExperimentSpec | None = None,
    git: GitState | None = None,
    gpu: GpuInfo | None = None,
    task_overrides: list[str] | None = None,
    config_sources: list[str] | None = None,
    tracking_ok: bool = True,
):
    pv = validate_protocol(
        spec.protocol, ROOT / spec.data.manifests_dir, frames=spec.model.input.frames
    )
    assert pv.ok, pv.issues
    return check_full_run_gate(
        spec,
        git=git or _git(),
        task_overrides=task_overrides or [],
        protocol_validation=pv,
        tracking_ok=tracking_ok,
        registry=registry or Registry(tmp_path / "empty-registry.jsonl"),
        frozen=frozen,
        gpu=gpu or GpuInfo(cuda_available=False),
        config_sources=config_sources or [],
        repo_root=ROOT,
        approvals_dir=tmp_path / "approvals",
    )


def test_smoke_always_allowed(tmp_path: Path) -> None:
    spec = _compose("syn_e01_frame_source_only")
    result = _gate(
        spec,
        tmp_path,
        git=_git(dirty=True, sha=None),
        frozen=None,
        registry=Registry(tmp_path / "none.jsonl"),
    )
    assert result.allowed is True
    assert result.reasons == []


def test_full_denied_without_flag(tmp_path: Path) -> None:
    spec = _compose("full_cpu_ok", fixture=True)
    spec.execution.allow_full_gpu_run = False
    spec.execution.allow_dirty_tree = True
    registry = _registry_with_smoke(tmp_path, spec)
    result = _gate(spec, tmp_path, registry=registry, frozen=spec)
    assert result.allowed is False
    assert result.checks["ALLOW_FLAG"] is False


def test_full_denied_when_mode_flag_from_cli(tmp_path: Path) -> None:
    spec = _compose("full_cpu_ok", fixture=True)
    registry = _registry_with_smoke(tmp_path, spec)
    result = _gate(
        spec,
        tmp_path,
        registry=registry,
        frozen=spec,
        task_overrides=["++execution.mode=full"],
    )
    assert result.allowed is False
    assert result.checks["FLAG_NOT_FROM_CLI"] is False


def test_full_denied_when_required_gpu_is_missing(tmp_path: Path) -> None:
    spec = _compose("full_needs_gpu", fixture=True)
    registry = _registry_with_smoke(tmp_path, spec)
    result = _gate(
        spec,
        tmp_path,
        registry=registry,
        frozen=spec,
        gpu=GpuInfo(cuda_available=False),
    )
    assert result.allowed is False
    assert result.checks["GPU_OK"] is False


def test_full_allowed_after_frozen_spec_and_smoke_row(tmp_path: Path) -> None:
    spec = _compose("full_cpu_ok", fixture=True)
    _approve(tmp_path, spec)
    registry = _registry_with_smoke(tmp_path, spec)
    result = _gate(spec, tmp_path, registry=registry, frozen=spec)
    assert result.allowed is True
    assert result.reasons == []
    assert result.approved_by is not None and result.approved_by.startswith("file:")


def test_a_pasted_token_approves_the_run_and_is_recorded_as_such(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second approval route (ADR-011): a signed string in the launching shell.

    It has to satisfy the gate exactly as the file does, and the run has to record WHICH route
    approved it — a standing file approval and a token someone pasted for this launch are
    different facts about how a result came to exist.
    """
    monkeypatch.setenv("PAD_APPROVAL_KEY_FILE", str(tmp_path / "key"))
    create_key()
    spec = _compose("full_cpu_ok", fixture=True)
    monkeypatch.setenv(
        TOKEN_ENV_VAR, mint_pasteable(spec.experiment.id, science_hash(spec), GIT_SHA)
    )
    registry = _registry_with_smoke(tmp_path, spec)

    result = _gate(spec, tmp_path, registry=registry, frozen=spec)

    assert result.allowed is True
    assert result.approved_by is not None and result.approved_by.startswith("paste:")


def test_a_pasted_token_for_another_experiment_does_not_approve_this_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A token left exported in a long-lived shell must not approve whatever runs next.
    monkeypatch.setenv("PAD_APPROVAL_KEY_FILE", str(tmp_path / "key"))
    create_key()
    spec = _compose("full_cpu_ok", fixture=True)
    monkeypatch.setenv(
        TOKEN_ENV_VAR, mint_pasteable("exp_something_else", science_hash(spec), GIT_SHA)
    )
    registry = _registry_with_smoke(tmp_path, spec)

    result = _gate(spec, tmp_path, registry=registry, frozen=spec)

    assert result.allowed is False
    assert result.checks["APPROVAL_TOKEN"] is False


def test_full_denied_without_human_approval_token(tmp_path: Path) -> None:
    spec = _compose("full_cpu_ok", fixture=True)
    registry = _registry_with_smoke(tmp_path, spec)
    result = _gate(spec, tmp_path, registry=registry, frozen=spec)
    assert result.allowed is False
    assert result.checks["APPROVAL_TOKEN"] is False
    assert any("APPROVAL_TOKEN" in reason for reason in result.reasons)


def test_full_denied_for_remote_tracking(tmp_path: Path) -> None:
    spec = _compose("full_cpu_ok", fixture=True)
    _approve(tmp_path, spec)
    registry = _registry_with_smoke(tmp_path, spec)
    result = _gate(spec, tmp_path, registry=registry, frozen=spec, tracking_ok=False)
    assert result.allowed is False
    assert result.checks["TRACKING_OK"] is False


def test_tracking_writable_can_deny_remote_uri_for_full_runs() -> None:
    ok, note = tracking_writable("https://mlflow.example.test", allow_remote=False)
    assert ok is False
    assert note is not None and "remote tracking URI" in note

    ok, note = tracking_writable("https://mlflow.example.test", allow_remote=True)
    assert ok is True
    assert note is not None and "remote tracking URI" in note


def test_full_denied_on_dirty_tree_without_override(tmp_path: Path) -> None:
    spec = _with_execution(_compose("full_cpu_ok", fixture=True), allow_dirty_tree=False)
    registry = _registry_with_smoke(tmp_path, spec)
    result = _gate(spec, tmp_path, registry=registry, frozen=spec, git=_git(dirty=True))
    assert result.allowed is False
    assert result.checks["GIT_OK"] is False


def test_full_denied_without_frozen_spec(tmp_path: Path) -> None:
    spec = _compose("full_cpu_ok", fixture=True)
    registry = _registry_with_smoke(tmp_path, spec)
    result = _gate(spec, tmp_path, registry=registry, frozen=None)
    assert result.allowed is False
    assert result.checks["SPEC_FROZEN"] is False


def test_full_denied_without_prior_smoke(tmp_path: Path) -> None:
    spec = _compose("full_cpu_ok", fixture=True)
    result = _gate(spec, tmp_path, frozen=spec, registry=Registry(tmp_path / "registry.jsonl"))
    assert result.allowed is False
    assert result.checks["SMOKE_OK"] is False


def test_full_passes_after_smoke_row_appended(tmp_path: Path) -> None:
    spec = _compose("full_cpu_ok", fixture=True)
    registry = Registry(tmp_path / "registry.jsonl")
    before = _gate(spec, tmp_path, registry=registry, frozen=spec)
    assert before.allowed is False
    assert before.checks["SMOKE_OK"] is False
    _approve(tmp_path, spec)
    after = _gate(spec, tmp_path, registry=_registry_with_smoke(tmp_path, spec), frozen=spec)
    assert after.allowed is True


def test_config_sources_ok() -> None:
    assert config_sources_ok([], ROOT)
    assert config_sources_ok([str(ROOT / "configs")], ROOT)
    assert config_sources_ok([str(ROOT / "tests" / "fixtures" / "configs")], ROOT)
    assert not config_sources_ok([str(ROOT / "docs")], ROOT)
    assert not config_sources_ok([str(ROOT.parent)], ROOT)


def test_unwritable_local_tracking_store_is_an_error_even_for_launch(tmp_path: Path) -> None:
    """An unwritable local store must fail validation in every mode.

    The smoke path short-circuits the gate, so downgrading this to a warning let a doomed run
    pass validation and die later inside MlflowTracker instead of being refused up front.
    """
    from pad_research.experiments.validator import validate_spec

    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    broken_uri = f"sqlite:///{blocker / 'nested' / 'mlruns.db'}"

    ok, note = tracking_writable(broken_uri, allow_remote=True)
    assert ok is False
    assert note is not None and "not writable" in note

    report = validate_spec(
        ["+exp=syn_e01_frame_source_only", f"tracking.tracking_uri={broken_uri}"],
        for_launch=True,
    )
    assert report.ok is False
    assert any("not writable" in message for message in report.errors)
    assert not any("not writable" in message for message in report.warnings)
