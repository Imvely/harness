"""Experiment report loading, aggregation and Markdown generation."""

from __future__ import annotations

import csv
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pad_research import paths
from pad_research.config.schema import ExperimentSpec
from pad_research.evaluation.evaluator import EvalResult
from pad_research.experiments.registry import Registry, RegistryRow
from pad_research.experiments.status import RunStatus
from pad_research.metrics.pad_metrics import PadMetrics
from pad_research.metrics.security_gate import SecurityGateResult, run_security_gate
from pad_research.protocols.compare import Comparability, assert_comparable
from pad_research.reporting.template import REPORT_TEMPLATE, SECTION44_HEADINGS
from pad_research.tracking.mlflow_tracker import MlflowTracker

OVERALL_METRICS = ("apcer", "bpcer", "acer", "hter", "auc")
REPORTABLE_FULL_STATUSES = (
    RunStatus.success,
    RunStatus.security_regression,
    RunStatus.inconclusive,
)


@dataclass(frozen=True)
class RunRecord:
    registry: RegistryRow
    eval: EvalResult
    spec: ExperimentSpec
    mlflow_run_id: str
    tags: dict[str, str]


@dataclass(frozen=True)
class ReportBundle:
    report_path: Path
    per_attack_csv: Path
    text: str
    gate: SecurityGateResult | None
    comparability: Comparability | None


def reportable_statuses(include_smoke: bool) -> set[RunStatus]:
    """Return terminal statuses eligible for report loading."""
    statuses: set[RunStatus] = set(REPORTABLE_FULL_STATUSES)
    if include_smoke:
        statuses.add(RunStatus.smoke_ok)
    return statuses


def _load_dict(run_id: str, artifact_path: str) -> dict[str, Any] | None:
    import mlflow.artifacts

    try:
        obj = mlflow.artifacts.load_dict(f"runs:/{run_id}/{artifact_path}")
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _load_text(run_id: str, artifact_path: str) -> str | None:
    import mlflow.artifacts

    try:
        local = Path(mlflow.artifacts.download_artifacts(f"runs:/{run_id}/{artifact_path}"))
    except Exception:
        return None
    return local.read_text(encoding="utf-8")


def _registry_fallback(
    run_id: str,
    item: MappingProxy,
    eval_result: EvalResult,
    status: RunStatus,
) -> RegistryRow:
    tags = item.tags
    git_sha = tags.get("git_sha")
    return RegistryRow(
        exp_id=eval_result.experiment_id,
        seed=eval_result.seed,
        mode=eval_result.mode,
        science_hash=eval_result.science_hash,
        spec_hash=eval_result.spec_hash,
        protocol_id=eval_result.protocol_id,
        protocol_hash=eval_result.protocol_hash,
        adaptation_set_hash=eval_result.adaptation_set_hash,
        mlflow_run_id=run_id,
        status=status,
        git_sha=None if git_sha in (None, "unknown") else git_sha,
        git_dirty=tags.get("git_dirty", "false").lower() == "true",
        started_at=str(item.raw.get("start_time", "")),
        finished_at=None,
        results_dir=None,
    )


@dataclass(frozen=True)
class MappingProxy:
    raw: dict[str, Any]
    tags: dict[str, str]


def _item_proxy(item: dict[str, Any]) -> MappingProxy:
    tags = {
        key.removeprefix("tags."): str(value)
        for key, value in item.items()
        if key.startswith("tags.") and value is not None
    }
    return MappingProxy(raw=item, tags=tags)


def _load_spec(run_id: str) -> ExperimentSpec | None:
    text = _load_text(run_id, "resolved_spec.yaml")
    if text is None:
        return None
    payload = yaml.safe_load(text)
    return ExperimentSpec.model_validate(payload)


def load_runs(
    experiment_id: str,
    *,
    include_smoke: bool,
    tracker: MlflowTracker,
) -> list[RunRecord]:
    """Load reportable runs for one experiment from MLflow artifacts."""
    allowed = reportable_statuses(include_smoke)
    runs = tracker._mlflow.search_runs(  # pyright: ignore[reportPrivateUsage]
        search_all_experiments=True,
        filter_string=f"tags.experiment_id = '{experiment_id}'",
        order_by=["attributes.start_time ASC"],
    )
    registry_by_run: dict[str, RegistryRow] = {}
    for row in Registry().rows():
        if row.mlflow_run_id is not None:
            registry_by_run[row.mlflow_run_id] = row

    records: list[RunRecord] = []
    for item in runs.to_dict(orient="records"):
        proxy = _item_proxy({str(k): v for k, v in item.items()})
        run_id = str(proxy.raw["run_id"])
        status_value = proxy.tags.get("status", "")
        try:
            status = RunStatus(status_value)
        except ValueError:
            continue
        if status not in allowed:
            continue
        eval_payload = _load_dict(run_id, "eval_test.json")
        spec = _load_spec(run_id)
        if eval_payload is None or spec is None:
            continue
        eval_result = EvalResult.model_validate(eval_payload)
        registry = registry_by_run.get(
            run_id,
            _registry_fallback(run_id, proxy, eval_result, status),
        )
        records.append(
            RunRecord(
                registry=registry,
                eval=eval_result,
                spec=spec,
                mlflow_run_id=run_id,
                tags=proxy.tags,
            )
        )
    return sorted(records, key=lambda r: (r.eval.seed, r.mlflow_run_id))


def _require_runs(runs: Sequence[RunRecord], name: str) -> None:
    if not runs:
        raise ValueError(f"{name} run list is empty")


def _one_protocol_hash(runs: Sequence[RunRecord], name: str) -> str:
    values = sorted({r.eval.protocol_hash for r in runs})
    if len(values) != 1:
        raise ValueError(f"{name} contains multiple protocol hashes: {values}")
    return values[0]


def _mean(values: Sequence[float]) -> float:
    return float(statistics.fmean(values))


def _std(values: Sequence[float]) -> float:
    return float(statistics.stdev(values)) if len(values) > 1 else 0.0


def _optional_mean(values: Iterable[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return _mean(present) if present else None


def aggregate_metrics(runs: Sequence[RunRecord]) -> PadMetrics:
    """Aggregate run metrics by arithmetic mean for reporting."""
    _require_runs(runs, "aggregate")
    metrics = [r.eval.metrics for r in runs]
    pai_keys = sorted({pai for m in metrics for pai in m.apcer_per_pai})
    per_pai = {
        pai: _mean([m.apcer_per_pai[pai] for m in metrics if pai in m.apcer_per_pai])
        for pai in pai_keys
    }
    n_attack_per_pai = {
        pai: min((m.n_attack_per_pai.get(pai, 0) for m in metrics), default=0) for pai in pai_keys
    }
    return PadMetrics(
        tau=_mean([m.tau for m in metrics]),
        apcer_per_pai=per_pai,
        apcer_max=_mean([m.apcer_max for m in metrics]),
        apcer_pooled=_mean([m.apcer_pooled for m in metrics]),
        apcer=_mean([m.apcer for m in metrics]),
        bpcer=_mean([m.bpcer for m in metrics]),
        acer=_mean([m.acer for m in metrics]),
        hter=_mean([m.hter for m in metrics]),
        auc=_mean([m.auc for m in metrics]),
        acer_policy=metrics[0].acer_policy,
        n_bona_fide=min(m.n_bona_fide for m in metrics),
        n_attack_per_pai=n_attack_per_pai,
        bpcer_at_apcer_10=_optional_mean(m.bpcer_at_apcer_10 for m in metrics),
        bpcer_at_apcer_1=_optional_mean(m.bpcer_at_apcer_1 for m in metrics),
    )


def _metric_stats(runs: Sequence[RunRecord]) -> dict[str, tuple[float, float]]:
    return {
        key: (
            _mean([float(getattr(r.eval.metrics, key)) for r in runs]),
            _std([float(getattr(r.eval.metrics, key)) for r in runs]),
        )
        for key in OVERALL_METRICS
    }


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.6f}"


def _fmt_mean_std(stats: tuple[float, float] | None) -> str:
    if stats is None:
        return "—"
    return f"{stats[0]:.6f} ± {stats[1]:.6f}"


def _overall_table(
    method: Sequence[RunRecord],
    baseline: Sequence[RunRecord] | None,
) -> str:
    method_stats = _metric_stats(method)
    baseline_stats = _metric_stats(baseline) if baseline else None
    lines = ["| Metric | Baseline | Method | Delta |", "|---|---:|---:|---:|"]
    for key in OVERALL_METRICS:
        b = baseline_stats[key] if baseline_stats else None
        m = method_stats[key]
        delta = None if b is None else m[0] - b[0]
        lines.append(f"| {key.upper()} | {_fmt_mean_std(b)} | {_fmt_mean_std(m)} | {_fmt(delta)} |")
    return "\n".join(lines)


def _per_attack_rows(
    method_mean: PadMetrics,
    baseline_mean: PadMetrics | None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pai in sorted(
        set(method_mean.apcer_per_pai) | set(baseline_mean.apcer_per_pai if baseline_mean else [])
    ):
        method_value = method_mean.apcer_per_pai.get(pai)
        baseline_value = baseline_mean.apcer_per_pai.get(pai) if baseline_mean else None
        delta = (
            None
            if method_value is None or baseline_value is None
            else method_value - baseline_value
        )
        rows.append(
            {
                "attack": pai,
                "apcer_baseline": _fmt(baseline_value),
                "apcer_method": _fmt(method_value),
                "delta": _fmt(delta),
                "n_attack_method": str(method_mean.n_attack_per_pai.get(pai, 0)),
            }
        )
    return rows


def _per_attack_table(rows: Sequence[dict[str, str]]) -> str:
    lines = [
        "| Attack | APCER Baseline | APCER Method | Delta | n_attack(method) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {attack} | {apcer_baseline} | {apcer_method} | {delta} | {n_attack_method} |".format(
                **row
            )
        )
    return "\n".join(lines)


def _write_per_attack_csv(path: Path, rows: Sequence[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "attack",
                "apcer_baseline",
                "apcer_method",
                "delta",
                "n_attack_method",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _protocol_block(run: RunRecord) -> str:
    spec = run.spec
    p = spec.protocol
    return "\n".join(
        [
            f"- Source: {', '.join(p.source_datasets)}",
            f"- Target: {', '.join(p.target_dataset) if p.target_dataset else 'source'}",
            f"- Adaptation data: {p.target_adaptation.supervision}, total_samples={p.target_adaptation.total_samples}",
            f"- Test split: {p.target_test.split.value}",
            f"- Attack types: {', '.join(a.value for a in p.attack_types)}",
            f"- Threshold rule: {p.threshold.rule}, dev_domain={p.threshold.dev_domain}",
            f"- Protocol hash: {run.eval.protocol_hash}",
            "- Manifest hashes: "
            + ", ".join(f"{k}:{v[:12]}" for k, v in sorted(run.eval.manifest_hashes.items())),
        ]
    )


def _model_block(run: RunRecord) -> str:
    spec = run.spec
    return "\n".join(
        [
            f"- Family: {spec.model.family}",
            f"- Frames: {spec.model.input.frames}",
            f"- Sampling: {spec.model.input.frame_sampling}",
            f"- Image size: {spec.model.input.image_size[0]}x{spec.model.input.image_size[1]}",
            f"- Adaptation method: {spec.adaptation.method}",
        ]
    )


def _training_block(runs: Sequence[RunRecord]) -> str:
    seeds = ", ".join(str(r.eval.seed) for r in runs)
    spec = runs[0].spec
    return "\n".join(
        [
            f"- Seeds: {seeds}",
            f"- Mode values: {', '.join(sorted({r.eval.mode for r in runs}))}",
            f"- Optimizer: {spec.training.optimizer}",
            f"- Epochs: training={spec.training.epochs}, adaptation={spec.adaptation.epochs}",
            f"- Threshold policy: {spec.protocol.threshold.policy}, rule={spec.protocol.threshold.rule}",
        ]
    )


def _security_block(gate: SecurityGateResult | None) -> str:
    if gate is None:
        return "기준 실행이 없어서 security regression gate를 계산하지 않았다."
    lines = [f"- Verdict: `{gate.verdict}`", f"- Note: {gate.note}"]
    if gate.per_pai:
        lines.append("")
        lines.append("| Attack | APCER before | APCER after | Delta | n_attack | Flag |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for row in gate.per_pai:
            flags = []
            if row.regressed:
                flags.append("regressed")
            if row.insufficient_support:
                flags.append("insufficient_support")
            lines.append(
                f"| {row.pai} | {_fmt(row.apcer_before)} | {_fmt(row.apcer_after)} | "
                f"{_fmt(row.delta)} | {row.n_attack} | {', '.join(flags) or '—'} |"
            )
    return "\n".join(lines)


def _seed_variance(method: Sequence[RunRecord], baseline: Sequence[RunRecord] | None) -> str:
    lines = [
        "| Group | Run ID | Seed | Mode | APCER | BPCER | ACER | HTER | AUC |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for group, runs in (("baseline", baseline or []), ("method", method)):
        for run in runs:
            m = run.eval.metrics
            lines.append(
                f"| {group} | `{run.mlflow_run_id}` | {run.eval.seed} | {run.eval.mode} | "
                f"{_fmt(m.apcer)} | {_fmt(m.bpcer)} | {_fmt(m.acer)} | {_fmt(m.hter)} | "
                f"{_fmt(m.auc)} |"
            )
    return "\n".join(lines)


def _mlflow_runs(method: Sequence[RunRecord], baseline: Sequence[RunRecord] | None) -> str:
    lines = ["| Group | Run ID | Status | Mode |", "|---|---|---|---|"]
    for group, runs in (("baseline", baseline or []), ("method", method)):
        for run in runs:
            lines.append(
                f"| {group} | `{run.mlflow_run_id}` | {run.registry.status.value} | {run.eval.mode} |"
            )
    return "\n".join(lines)


def _git_commit(method: Sequence[RunRecord], baseline: Sequence[RunRecord] | None) -> str:
    lines = ["| Group | Run ID | Git SHA | Dirty |", "|---|---|---|---|"]
    for group, runs in (("baseline", baseline or []), ("method", method)):
        for run in runs:
            lines.append(
                f"| {group} | `{run.mlflow_run_id}` | {run.registry.git_sha or 'unknown'} | "
                f"{str(run.registry.git_dirty).lower()} |"
            )
    return "\n".join(lines)


def _research_allowed(runs: Sequence[RunRecord]) -> bool:
    return all(r.tags.get("research_claim_allowed", "true").lower() == "true" for r in runs)


def _does_not_prove(
    method: Sequence[RunRecord],
    baseline: Sequence[RunRecord] | None,
    gate: SecurityGateResult | None,
    comparability: Comparability | None,
) -> str:
    items: list[str] = []
    all_runs = [*method, *(baseline or [])]
    if len(method) < 3 or (baseline is not None and len(baseline) < 3):
        items.append("seed가 3개 미만이므로 seed variance 결론을 주장하지 않는다.")
    if not _research_allowed(all_runs):
        items.append("합성 데이터 sanity 실행이므로 연구 결과를 뒷받침하지 않는다.")
    if gate is not None and any(row.insufficient_support for row in gate.per_pai):
        items.append("일부 PAI의 공격 표본 수가 부족하므로 해당 PAI 결론을 주장하지 않는다.")
    if comparability == Comparability.justified_diff:
        items.append("protocol hash가 다르므로 직접 비교 가능한 결과로 주장하지 않는다.")
    if any(r.eval.mode == "smoke" for r in all_runs):
        items.append("smoke run이 포함되어 있으므로 성능 수치로 주장하지 않는다.")
    if baseline is None:
        items.append("기준 실행이 없으므로 방법 간 차이를 주장하지 않는다.")
    return "\n".join(f"- {item}" for item in items) if items else "- 자동 제한 항목 없음."


def _interpretation(method: Sequence[RunRecord], baseline: Sequence[RunRecord] | None) -> str:
    spec = method[0].spec
    dataset = ",".join(spec.protocol.source_datasets + spec.protocol.target_dataset)
    seeds = ", ".join(str(r.eval.seed) for r in method)
    baseline_text = "기준 실행 없이" if baseline is None else "기준 실행과 함께"
    return (
        f"{dataset} 데이터셋, {spec.protocol.protocol_id} protocol, seed {seeds}, "
        f"{', '.join(m.upper() for m in OVERALL_METRICS)} metric, "
        f"{spec.protocol.threshold.policy}/{spec.protocol.threshold.rule} threshold policy 조건에서 "
        f"{baseline_text} 관찰한 수치만 기록한다.\n\n"
        "TODO(reviewer): 실제 데이터와 충분한 seed 결과를 검토한 뒤 해석 문장을 작성한다."
    )


def _failure_analysis(gate: SecurityGateResult | None) -> str:
    if gate is None:
        return "자동 실패 분석 없음. 기준 실행이 없어서 gate verdict를 계산하지 않았다."
    if gate.verdict == "pass":
        return (
            "gate가 허용 범위 안의 per-PAI APCER 차이를 기록했다. 추가 해석은 reviewer가 작성한다."
        )
    return f"gate verdict `{gate.verdict}`에 따라 reviewer 검토가 필요하다."


def _banners(
    runs: Sequence[RunRecord],
    comparability: Comparability | None,
    justify: str | None,
) -> str:
    banners: list[str] = []
    if not _research_allowed(runs):
        banners.append("> SYNTHETIC SANITY — NOT A RESEARCH RESULT")
    if comparability == Comparability.justified_diff:
        banners.append(f"> NOT DIRECTLY COMPARABLE: {justify}")
    return "\n\n".join(banners) if banners else "_No report-level warnings._"


def _next_experiment(gate: SecurityGateResult | None) -> str:
    if gate is None:
        return "기준 실행을 같은 protocol hash로 먼저 수집한다."
    if gate.verdict in ("security_regression", "inconclusive", "comparison_blocked"):
        return "reviewer가 gate 세부 항목을 확인한 뒤 다음 ablation을 정한다."
    return "같은 protocol에서 seed 수를 늘리거나 다음 예정 ablation을 실행한다."


def generate_report(
    method_runs: list[RunRecord],
    baseline_runs: list[RunRecord] | None,
    out: Path,
    *,
    justify: str | None,
) -> ReportBundle:
    """Generate a contract §44 report and per-attack CSV."""
    _require_runs(method_runs, "method")
    method_hash = _one_protocol_hash(method_runs, "method")
    baseline_mean: PadMetrics | None = None
    gate: SecurityGateResult | None = None
    comparability: Comparability | None = None
    if baseline_runs:
        baseline_hash = _one_protocol_hash(baseline_runs, "baseline")
        comparability = assert_comparable(baseline_hash, method_hash, justify)
        baseline_mean = aggregate_metrics(baseline_runs)
    method_mean = aggregate_metrics(method_runs)
    if baseline_mean is not None and baseline_runs is not None:
        gate = run_security_gate(
            baseline_mean,
            method_mean,
            baseline_runs[0].eval.protocol_hash,
            method_runs[0].eval.protocol_hash,
            method_runs[0].spec.protocol.security_gate,
            justify=justify,
            baseline_run_id=",".join(r.mlflow_run_id for r in baseline_runs),
        )
    per_attack_rows = _per_attack_rows(method_mean, baseline_mean)
    report_path = Path(out)
    table_path = (
        paths.repo_root()
        / "artifacts"
        / "tables"
        / f"{method_runs[0].spec.experiment.id}_per_attack.csv"
    )
    _write_per_attack_csv(table_path, per_attack_rows)
    all_runs = [*method_runs, *(baseline_runs or [])]
    text = REPORT_TEMPLATE.substitute(
        banners=_banners(all_runs, comparability, justify),
        research_question=method_runs[0].spec.experiment.research_question,
        hypothesis=method_runs[0].spec.experiment.hypothesis or "_No hypothesis text._",
        protocol=_protocol_block(method_runs[0]),
        model=_model_block(method_runs[0]),
        training=_training_block(method_runs),
        overall_table=_overall_table(method_runs, baseline_runs),
        per_attack_table=_per_attack_table(per_attack_rows),
        security_regression=_security_block(gate),
        seed_variance=_seed_variance(method_runs, baseline_runs),
        failure_analysis=_failure_analysis(gate),
        interpretation=_interpretation(method_runs, baseline_runs),
        does_not_prove=_does_not_prove(method_runs, baseline_runs, gate, comparability),
        next_experiment=_next_experiment(gate),
        mlflow_runs=_mlflow_runs(method_runs, baseline_runs),
        git_commit=_git_commit(method_runs, baseline_runs),
    )
    for heading in SECTION44_HEADINGS:
        if heading not in text:
            raise ValueError(f"report template missing heading: {heading}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8", newline="\n")
    return ReportBundle(
        report_path=report_path,
        per_attack_csv=table_path,
        text=text,
        gate=gate,
        comparability=comparability,
    )
