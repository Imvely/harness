"""Experiment spec validation for ``scripts/validate_spec.py`` and the launch hook (no torch/mlflow)."""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, ValidationError

from pad_research import paths
from pad_research.config.compose import compose_spec, exp_name_from_overrides
from pad_research.config.freeze import read_frozen_spec, write_resolved_spec
from pad_research.config.schema import ExperimentSpec, science_hash, spec_hash
from pad_research.experiments.approvals import read_token
from pad_research.experiments.gate import GateResult, GpuInfo, check_full_run_gate
from pad_research.experiments.registry import Registry
from pad_research.protocols.validator import validate_protocol
from pad_research.utils.git import git_state
from pad_research.utils.redaction import redact_text


class SpecValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    exit_code: int
    errors: list[str]
    warnings: list[str]
    experiment_id: str | None = None
    mode: str | None = None
    science_hash: str | None = None
    spec_hash: str | None = None
    protocol_id: str | None = None
    protocol_hash: str | None = None
    manifest_hashes: dict[str, str] = {}
    adaptation_set_hash: str | None = None
    tracking_uri_scheme: str = ""
    approval_token_ok: bool = False
    frozen_path: str | None = None
    gate: dict[str, object] | None = None


def resolve_tracking_uri(spec_uri: str | None) -> str:
    return spec_uri or paths.default_tracking_uri()


def tracking_uri_scheme(uri: str) -> str:
    return urlparse(uri).scheme.lower()


def tracking_writable(uri: str, *, allow_remote: bool = True) -> tuple[bool, str | None]:
    scheme = tracking_uri_scheme(uri)
    if scheme in ("sqlite", "file", ""):
        target = uri.split("///", 1)[1] if "///" in uri else uri
        try:
            Path(target).expanduser().parent.mkdir(parents=True, exist_ok=True)
            if scheme == "sqlite":
                sqlite3.connect(target).close()
            return True, None
        except (OSError, sqlite3.Error) as exc:
            return False, f"tracking location not writable: {exc}"
    note = f"remote tracking URI ({scheme}); artifacts leave the machine"
    return allow_remote, note


def probe_gpu() -> GpuInfo:
    """Approximate GPU availability WITHOUT importing torch (validator/hook path)."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return GpuInfo(cuda_available=False)
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return GpuInfo(cuda_available=False)
    names = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    return GpuInfo(cuda_available=out.returncode == 0 and bool(names), gpu_names=names)


def validate_spec(
    overrides: list[str],
    *,
    for_launch: bool = False,
    freeze: bool = False,
    repo_root: Path | None = None,
    extra_config_dir: Path | None = None,
    gpu: GpuInfo | None = None,
    require_approval: bool = True,
) -> SpecValidationReport:
    root = repo_root or paths.repo_root()
    errors: list[str] = []
    warnings: list[str] = []
    if exp_name_from_overrides(overrides) is None:
        return SpecValidationReport(
            ok=False, exit_code=2, errors=["no +exp=<name> override"], warnings=[]
        )
    try:
        _, spec = compose_spec(
            overrides, config_dir=root / "configs", extra_config_dir=extra_config_dir
        )
    except ValidationError as exc:
        msgs = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return SpecValidationReport(
            ok=False,
            exit_code=2,
            errors=[redact_text(msg, root) for msg in msgs[:20]],
            warnings=[],
        )
    except Exception as exc:  # Hydra composition errors
        return SpecValidationReport(
            ok=False,
            exit_code=2,
            errors=[redact_text(f"compose: {exc}", root)],
            warnings=[],
        )

    sh, ph = science_hash(spec), spec_hash(spec)
    pv = validate_protocol(
        spec.protocol, root / spec.data.manifests_dir, frames=spec.model.input.frames
    )
    errors += [redact_text(f"protocol {i.code}: {i.message}", root) for i in pv.errors()]
    warnings += [redact_text(f"protocol {i.code}: {i.message}", root) for i in pv.warnings()]

    uri = resolve_tracking_uri(spec.tracking.tracking_uri)
    tracking_ok, note = tracking_writable(uri, allow_remote=spec.execution.mode != "full")
    if note:
        note = redact_text(note, root)
        if tracking_ok or for_launch:
            warnings.append(note)
        else:
            errors.append(note)

    frozen_path = (
        str(write_resolved_spec(spec, paths.specs_dir())) if freeze and not errors else None
    )
    report = SpecValidationReport(
        ok=not errors,
        exit_code=3 if errors else 0,
        errors=errors,
        warnings=warnings,
        experiment_id=spec.experiment.id,
        mode=spec.execution.mode,
        science_hash=sh,
        spec_hash=ph,
        protocol_id=spec.protocol.protocol_id,
        protocol_hash=pv.protocol_hash,
        manifest_hashes=pv.manifest_hashes,
        adaptation_set_hash=pv.adaptation_set_hash,
        tracking_uri_scheme=tracking_uri_scheme(uri),
        approval_token_ok=read_token(spec.experiment.id, sh) is not None,
        frozen_path=frozen_path,
    )
    if for_launch and report.ok:
        gate = check_full_run_gate(
            spec,
            git=git_state(root),
            task_overrides=[t for t in overrides if not t.lstrip("+~").startswith("exp=")],
            protocol_validation=pv,
            tracking_ok=tracking_ok,
            registry=Registry(),
            frozen=read_frozen_spec(spec.experiment.id, paths.specs_dir()),
            gpu=gpu if gpu is not None else probe_gpu(),
            config_sources=[],
            repo_root=root,
            require_approval=require_approval,
        )
        report.gate = _gate_dict(gate)
        if not gate.allowed:
            report.ok, report.exit_code = False, 4
            report.errors = report.errors + [f"gate {r}" for r in gate.reasons]
    return report


def _gate_dict(gate: GateResult) -> dict[str, object]:
    return {
        "allowed": gate.allowed,
        "reasons": gate.reasons,
        "checks": gate.checks,
        "approved_by": gate.approved_by,
    }


__all__ = ["ExperimentSpec", "SpecValidationReport", "validate_spec"]
