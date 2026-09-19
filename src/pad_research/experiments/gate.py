"""In-process full-run gate (contract §16, §24.3, §41-9), independent of the Claude hook."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pad_research.config.schema import ExperimentSpec, science_hash
from pad_research.experiments.approvals import read_token
from pad_research.experiments.registry import Registry
from pad_research.protocols.validator import ProtocolValidation
from pad_research.utils.git import GitState

ALLOWED_CONFIG_DIR_NAMES = ("configs", "tests/fixtures/configs")


@dataclass
class GpuInfo:
    cuda_available: bool
    gpu_names: list[str] = field(default_factory=list)


@dataclass
class GateResult:
    allowed: bool
    reasons: list[str]
    checks: dict[str, bool]
    approved_by: str | None = None


def touches_execution(token: str) -> bool:
    key = token.lstrip("+~").strip("'\"").split("=", 1)[0]
    return key == "execution" or key.startswith("execution.")


def is_smoke_demotion(token: str) -> bool:
    return token.lstrip("+~").strip("'\"").replace(" ", "") == "execution.mode=smoke"


def config_sources_ok(sources: list[str], repo_root: Path) -> bool:
    if not sources:
        return True
    allowed = [(repo_root / n).resolve() for n in ALLOWED_CONFIG_DIR_NAMES]
    return all(
        any(Path(s).resolve() == a or a in Path(s).resolve().parents for a in allowed)
        for s in sources
    )


def check_full_run_gate(
    spec: ExperimentSpec,
    *,
    git: GitState,
    task_overrides: list[str],
    protocol_validation: ProtocolValidation,
    tracking_ok: bool,
    registry: Registry,
    frozen: ExperimentSpec | None,
    gpu: GpuInfo | None,
    config_sources: list[str],
    repo_root: Path,
    approvals_dir: Path | None = None,
    require_approval: bool = True,
) -> GateResult:
    x = spec.execution
    sh = science_hash(spec)
    checks: dict[str, bool] = {}
    reasons: list[str] = []

    def add(name: str, ok: bool, why: str) -> None:
        checks[name] = ok
        if not ok:
            reasons.append(f"{name}: {why}")

    add("ALLOW_FLAG", x.allow_full_gpu_run, "execution.allow_full_gpu_run is false")
    add(
        "FLAG_NOT_FROM_CLI",
        not any(touches_execution(t) and not is_smoke_demotion(t) for t in task_overrides),
        "execution.* may only be set in configs/exp/<name>.yaml (demotion to smoke excepted)",
    )
    add(
        "CONFIG_SOURCES_OK",
        config_sources_ok(config_sources, repo_root),
        "config source outside configs/",
    )
    add(
        "PROTOCOL_OK",
        protocol_validation.ok and protocol_validation.status == "active",
        "protocol has errors or is draft",
    )
    add("MANIFESTS_OK", "MISSING_MANIFEST" not in protocol_validation.codes(), "manifest missing")
    add(
        "GIT_OK",
        git.sha is not None and (not git.dirty or x.allow_dirty_tree),
        "tracked working tree is dirty (commit first or set allow_dirty_tree)",
    )
    add("TRACKING_OK", tracking_ok, "MLflow tracking URI not writable")
    if x.require_gpu:
        gpu_ok = gpu is not None and gpu.cuda_available
        if gpu_ok and x.expected_gpu and gpu is not None:
            gpu_ok = any(x.expected_gpu.lower() in n.lower() for n in gpu.gpu_names)
        add("GPU_OK", gpu_ok, f"require_gpu={x.require_gpu} expected_gpu={x.expected_gpu}")
    else:
        checks["GPU_OK"] = True
    add(
        "SPEC_FROZEN",
        frozen is not None and science_hash(frozen) == sh,
        "no frozen spec with the same science_hash (run validate_spec --freeze)",
    )
    if x.smoke_test_first:
        smoke = registry.latest_success_smoke(sh, None if x.allow_dirty_tree else git.sha)
        add(
            "SMOKE_OK",
            smoke is not None,
            "no smoke_ok run with the same science_hash (and git sha)",
        )
    else:
        checks["SMOKE_OK"] = True
    token = read_token(spec.experiment.id, sh, approvals_dir)
    checks["APPROVAL_TOKEN"] = token is not None
    if x.mode == "smoke":
        return GateResult(allowed=True, reasons=[], checks=checks)
    if require_approval and token is None:
        reasons.append(
            "APPROVAL_TOKEN: full run requires a matching human approval token "
            "(run scripts/approve_full_run.py yourself after freeze+smoke)"
        )
    allowed = (
        all(checks.values())
        if require_approval
        else all(v for k, v in checks.items() if k != "APPROVAL_TOKEN")
    )
    return GateResult(
        allowed=allowed,
        reasons=reasons,
        checks=checks,
        approved_by=f"file:{token.approved_by}" if token else None,
    )
