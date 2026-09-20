"""Export PAD run records into a safe dashboard JSON document."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, cast

from pad_research import paths
from pad_research.data.manifest import ManifestNotFoundError, load_manifest
from pad_research.reporting.report import RunRecord, load_runs
from pad_research.tracking.mlflow_tracker import MlflowTracker
from pad_research.utils.redaction import is_sensitive_text, redact_tag_value

from .schema import (
    ClaimBlocker,
    ClaimEligibility,
    DashboardArtifact,
    DashboardBundle,
    DashboardMetrics,
    DashboardPerAttack,
    DashboardRun,
    DashboardThreshold,
    GateVerdict,
    PiiPolicy,
)

# (relative_path, kind). No label: an English name on the wire is one the dashboard cannot
# translate, and the path already identifies the file.
_SAFE_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("resolved_spec.yaml", "yaml"),
    ("eval_test.json", "json"),
    ("eval_source_dev.json", "json"),
    ("regression_check.json", "json"),
    ("roc_curve.png", "image"),
    ("training_curves.csv", "csv"),
    ("latency.json", "json"),
)

_DASHBOARD_TAG_ALLOWLIST = frozenset(
    {
        "research_question",
        "protocol_id",
        "protocol_hash",
        "model_family",
        "adaptation_method",
        "target_supervision",
        "dataset_manifest_hash",
        "git_sha",
        "git_dirty",
        "git_branch",
        "lock_hash",
        "torch_build",
        "status",
        "experiment_id",
        "science_hash",
        "spec_hash",
        "execution_mode",
        "seed",
        "parent_experiment_id",
        "baseline_experiment_id",
        "adaptation_set_hash",
        "threshold_source",
        "threshold_rule",
        "research_claim_allowed",
        "model_init",
        "remote_artifacts",
        "gate_verdict",
    }
)


def _utc_now() -> str:
    return dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds")


def _parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _duration_seconds(started_at: str | None, finished_at: str | None) -> float | None:
    start = _parse_time(started_at)
    end = _parse_time(finished_at)
    if start is None or end is None:
        return None
    return max((end - start).total_seconds(), 0.0)


def _is_safe_relative_path(value: str) -> bool:
    if not value or "\\" in value:
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        return False
    return ".." not in posix.parts


def _artifact(relative_path: str, kind: str) -> DashboardArtifact:
    if not _is_safe_relative_path(relative_path):
        raise ValueError(f"unsafe dashboard artifact path: {relative_path!r}")
    return DashboardArtifact(relative_path=relative_path, kind=cast(Any, kind))


def _safe_artifacts(record: RunRecord) -> list[DashboardArtifact]:
    """List only the safe artifacts this run actually wrote.

    Emitting the whole fixed list advertised files a run never produced: a source-only run
    has no regression_check.json, and a run with measure_latency off has no latency.json.
    The dashboard then linked to files that 404, which reads as a lost artifact rather than
    an artifact that was never meant to exist.
    """
    results_dir = record.registry.results_dir
    if not results_dir:
        return []
    base = Path(results_dir)
    return [_artifact(rel, kind) for rel, kind in _SAFE_ARTIFACTS if (base / rel).is_file()]


def _safe_tags(record: RunRecord, repo_root: Path) -> dict[str, str]:
    return {
        k: redact_tag_value(v, repo_root)
        for k, v in sorted(record.tags.items())
        if k in _DASHBOARD_TAG_ALLOWLIST
    }


def _load_regression_check(run_id: str) -> dict[str, Any] | None:
    try:
        import mlflow.artifacts

        obj = mlflow.artifacts.load_dict(f"runs:/{run_id}/regression_check.json")
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _gate_verdict(record: RunRecord, regression_check: Mapping[str, Any] | None) -> GateVerdict:
    tag_value = record.tags.get("gate_verdict")
    if isinstance(tag_value, str) and tag_value in (
        "pass",
        "no_gate",
        "security_regression",
        "inconclusive",
        "comparison_blocked",
    ):
        return cast(GateVerdict, tag_value)
    gate = regression_check.get("gate") if regression_check else None
    if isinstance(gate, Mapping):
        verdict = gate.get("verdict")
        if isinstance(verdict, str) and verdict in (
            "pass",
            "no_gate",
            "security_regression",
            "inconclusive",
            "comparison_blocked",
        ):
            return cast(GateVerdict, verdict)
    status_value = record.registry.status.value
    if status_value == "security_regression":
        return "security_regression"
    if status_value == "inconclusive":
        return "inconclusive"
    if record.spec.adaptation.method == "none" and status_value in ("success", "smoke_ok"):
        return "no_gate"
    return "unknown"


def _dataset_pii_policies(record: RunRecord, repo_root: Path) -> dict[str, PiiPolicy]:
    manifests_dir = repo_root / record.spec.data.manifests_dir
    policies: dict[str, PiiPolicy] = {}
    for dataset_id in [*record.spec.protocol.source_datasets, *record.spec.protocol.target_dataset]:
        try:
            manifest = load_manifest(dataset_id, manifests_dir)
        except (ManifestNotFoundError, OSError, ValueError):
            policies[dataset_id] = "unknown"
            continue
        policies[dataset_id] = cast(PiiPolicy, manifest.meta.pii_policy)
    return policies


def _research_claim_allowed(record: RunRecord, policies: Mapping[str, PiiPolicy]) -> bool:
    tag_allows = record.tags.get("research_claim_allowed", "false").lower() == "true"
    policies_known = bool(policies) and all(value != "unknown" for value in policies.values())
    policies_allow = policies_known and all(value != "synthetic" for value in policies.values())
    return tag_allows and policies_allow


def _per_attack(
    record: RunRecord,
    regression_check: Mapping[str, Any] | None,
) -> list[DashboardPerAttack]:
    metrics = record.eval.metrics
    gate_rows: dict[str, Mapping[str, Any]] = {}
    gate = regression_check.get("gate") if regression_check else None
    if isinstance(gate, Mapping):
        raw_rows = gate.get("per_pai")
        if isinstance(raw_rows, list):
            for raw in raw_rows:
                if isinstance(raw, Mapping) and isinstance(raw.get("pai"), str):
                    gate_rows[str(raw["pai"])] = raw

    rows: list[DashboardPerAttack] = []
    # Same rule as pad_research.metrics.security_gate: a PAI counts as supported only once it
    # reaches the protocol's min_attack_samples_per_pai. Using "> 0" here would show a thin PAI
    # as fully supported while the gate calls the same comparison inconclusive (contract 14.3).
    min_support = record.spec.protocol.security_gate.min_attack_samples_per_pai
    for pai, apcer in sorted(metrics.apcer_per_pai.items()):
        gate_row = gate_rows.get(pai)
        baseline_apcer = None
        delta = None
        regressed = None
        insufficient = metrics.n_attack_per_pai.get(pai, 0) < min_support
        if gate_row is not None:
            before = gate_row.get("apcer_before")
            raw_delta = gate_row.get("delta")
            raw_regressed = gate_row.get("regressed")
            raw_insufficient = gate_row.get("insufficient_support")
            baseline_apcer = float(before) if isinstance(before, int | float) else None
            delta = float(raw_delta) if isinstance(raw_delta, int | float) else None
            regressed = bool(raw_regressed) if isinstance(raw_regressed, bool) else None
            if isinstance(raw_insufficient, bool):
                insufficient = raw_insufficient
        rows.append(
            DashboardPerAttack(
                pai=pai,
                apcer=float(apcer),
                baseline_apcer=baseline_apcer,
                delta=delta,
                n_attack=int(metrics.n_attack_per_pai.get(pai, 0)),
                insufficient_support=insufficient,
                regressed=regressed,
            )
        )
    return rows


def _claim_eligibility(
    record: RunRecord,
    *,
    research_claim_allowed: bool,
    gate_verdict: GateVerdict,
    protocol_count_for_experiment: int,
    seed_count_for_experiment: int,
    policies: Mapping[str, PiiPolicy],
) -> ClaimEligibility:
    full_mode = record.eval.mode == "full"
    enough_pai_support = all(
        count >= record.spec.protocol.security_gate.min_attack_samples_per_pai
        for count in record.eval.metrics.n_attack_per_pai.values()
    )
    threshold_from_dev = (record.eval.threshold.fitted_on or "").endswith("/dev")
    no_security_regression = gate_verdict != "security_regression"
    single_protocol = protocol_count_for_experiment == 1
    at_least_three_seeds = seed_count_for_experiment >= 3

    # Codes, not sentences. These are read by a Korean-first dashboard that cannot translate
    # English prose, and by anything else that wants to branch on *why* a claim is blocked.
    blockers: list[ClaimBlocker] = []
    if not full_mode:
        blockers.append("mode_not_full")
    if not research_claim_allowed:
        blockers.append("research_claim_not_allowed")
    if any(value == "synthetic" for value in policies.values()):
        blockers.append("dataset_synthetic")
    if any(value == "unknown" for value in policies.values()):
        blockers.append("dataset_pii_unknown")
    if not at_least_three_seeds:
        blockers.append("fewer_than_three_seeds")
    if not enough_pai_support:
        blockers.append("insufficient_pai_support")
    if not threshold_from_dev:
        blockers.append("threshold_not_from_dev")
    if not no_security_regression:
        blockers.append("security_regression")
    if not single_protocol:
        blockers.append("multiple_protocol_hashes")

    allowed = (
        full_mode
        and research_claim_allowed
        and at_least_three_seeds
        and enough_pai_support
        and threshold_from_dev
        and no_security_regression
        and single_protocol
    )
    return ClaimEligibility(
        allowed=allowed,
        full_mode=full_mode,
        research_claim_allowed=research_claim_allowed,
        at_least_three_seeds=at_least_three_seeds,
        enough_pai_support=enough_pai_support,
        threshold_from_dev=threshold_from_dev,
        no_security_regression=no_security_regression,
        single_protocol_in_experiment=single_protocol,
        blockers=blockers,
    )


def dashboard_run_from_record(
    record: RunRecord,
    *,
    protocol_count_for_experiment: int = 1,
    seed_count_for_experiment: int = 1,
    repo_root: Path | None = None,
    regression_check: Mapping[str, Any] | None = None,
) -> DashboardRun:
    """Convert a loaded MLflow/reporting run into one safe dashboard row."""
    root = repo_root or paths.repo_root()
    loaded_regression_check = regression_check or _load_regression_check(record.mlflow_run_id)
    gate_verdict = _gate_verdict(record, loaded_regression_check)
    policies = _dataset_pii_policies(record, root)
    research_allowed = _research_claim_allowed(record, policies)
    metrics = record.eval.metrics
    threshold = record.eval.threshold
    return DashboardRun(
        run_id=record.mlflow_run_id,
        experiment_id=record.eval.experiment_id,
        title=record.spec.experiment.title,
        status=record.registry.status.value,
        gate_verdict=gate_verdict,
        mode=cast(Any, record.eval.mode),
        seed=record.registry.seed,
        started_at=record.registry.started_at,
        finished_at=record.registry.finished_at,
        duration_seconds=_duration_seconds(record.registry.started_at, record.registry.finished_at),
        model_family=record.spec.model.family,
        adaptation_method=record.spec.adaptation.method,
        source_datasets=list(record.spec.protocol.source_datasets),
        target_datasets=list(record.spec.protocol.target_dataset),
        protocol_id=record.eval.protocol_id,
        protocol_hash=record.eval.protocol_hash,
        science_hash=record.eval.science_hash,
        spec_hash=record.eval.spec_hash,
        manifest_hashes=dict(record.eval.manifest_hashes),
        dataset_pii_policies=policies,
        adaptation_set_hash=record.eval.adaptation_set_hash,
        research_claim_allowed=research_allowed,
        claim_eligibility=_claim_eligibility(
            record,
            research_claim_allowed=research_allowed,
            gate_verdict=gate_verdict,
            protocol_count_for_experiment=protocol_count_for_experiment,
            seed_count_for_experiment=seed_count_for_experiment,
            policies=policies,
        ),
        threshold=DashboardThreshold(
            rule=threshold.spec.rule,
            fitted_on=threshold.fitted_on,
            tau=threshold.tau,
            dev_n_bona_fide=threshold.dev_n_bona_fide,
            dev_n_attack=threshold.dev_n_attack,
        ),
        metrics=DashboardMetrics(
            apcer=metrics.apcer,
            bpcer=metrics.bpcer,
            acer=metrics.acer,
            hter=metrics.hter,
            auc=metrics.auc,
            tau=metrics.tau,
        ),
        per_attack=_per_attack(record, loaded_regression_check),
        tags=_safe_tags(record, root),
        artifacts=_safe_artifacts(record),
    )


def export_dashboard_bundle(
    records: Sequence[RunRecord],
    *,
    repo_root: Path | None = None,
    generated_at: str | None = None,
) -> DashboardBundle:
    """Create a dashboard bundle from report run records."""
    protocol_counts: dict[str, int] = {}
    seed_counts: dict[str, int] = {}
    for exp_id in sorted({record.eval.experiment_id for record in records}):
        exp_records = [record for record in records if record.eval.experiment_id == exp_id]
        protocol_counts[exp_id] = len({record.eval.protocol_hash for record in exp_records})
        seed_counts[exp_id] = len({record.eval.seed for record in exp_records})

    runs = [
        dashboard_run_from_record(
            record,
            protocol_count_for_experiment=protocol_counts.get(record.eval.experiment_id, 0),
            seed_count_for_experiment=seed_counts.get(record.eval.experiment_id, 0),
            repo_root=repo_root,
        )
        for record in records
    ]
    return DashboardBundle(generated_at=generated_at or _utc_now(), runs=runs)


def load_dashboard_records(
    experiment_ids: Sequence[str],
    *,
    include_smoke: bool,
    tracker: MlflowTracker,
) -> list[RunRecord]:
    """Load reportable records for dashboard export from MLflow."""
    records: list[RunRecord] = []
    for experiment_id in experiment_ids:
        records.extend(load_runs(experiment_id, include_smoke=include_smoke, tracker=tracker))
    return sorted(
        records, key=lambda item: (item.eval.experiment_id, item.eval.seed, item.mlflow_run_id)
    )


def write_dashboard_bundle(bundle: DashboardBundle, output: Path | str) -> Path:
    """Write dashboard JSON with stable ordering and no local absolute paths."""
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = bundle.model_dump(mode="json")
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    if is_sensitive_text(text, paths.repo_root()):
        raise ValueError("dashboard export would leak local paths or raw data references")
    out.write_text(text, encoding="utf-8", newline="\n")
    return out
