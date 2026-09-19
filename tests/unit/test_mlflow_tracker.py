"""Unit tests for the MLflow tracker wrapper."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from pad_research.config.compose import compose_spec
from pad_research.experiments.status import RunStatus
from pad_research.metrics.pad_metrics import PadMetrics
from pad_research.protocols.validator import validate_protocol
from pad_research.tracking.env_snapshot import collect_env_snapshot
from pad_research.tracking.mlflow_tracker import MlflowTracker
from pad_research.tracking.tags import REQUIRED_TAGS

ROOT = Path(__file__).resolve().parents[2]


def _spec(exp_name: str = "syn_e01_frame_source_only"):
    _, spec = compose_spec([f"+exp={exp_name}"])
    return spec


def _pv(spec):
    pv = validate_protocol(
        spec.protocol, ROOT / spec.data.manifests_dir, frames=spec.model.input.frames
    )
    assert pv.ok, pv.issues
    return pv


def _env():
    return collect_env_snapshot(ROOT, with_torch=False)


def _metrics(**updates: object) -> PadMetrics:
    data = {
        "tau": 0.5,
        "apcer_per_pai": {"print": 0.25, "replay_phone": 0.5},
        "apcer_max": 0.5,
        "apcer_pooled": 0.4,
        "apcer": 0.5,
        "bpcer": 0.125,
        "acer": 0.3125,
        "hter": 0.2625,
        "auc": 0.75,
        "acer_policy": "max_pai",
        "n_bona_fide": 8,
        "n_attack_per_pai": {"print": 4, "replay_phone": 4},
    }
    data.update(updates)
    return PadMetrics.model_validate(data)


def _start_tracker(tmp_path: Path, exp_name: str = "syn_e01_frame_source_only"):
    spec = _spec(exp_name)
    tracker = MlflowTracker(spec.tracking, tmp_path)
    pv = _pv(spec)
    run_id = tracker.start_run(spec, pv, _env())
    return tracker, spec, pv, run_id


def test_start_run_logs_required_tags(tmp_path: Path) -> None:
    tracker, spec, pv, run_id = _start_tracker(tmp_path)
    import mlflow

    rows = mlflow.search_runs(search_all_experiments=True)
    assert rows["run_id"].tolist() == [run_id]
    row = rows.iloc[0]
    for tag in REQUIRED_TAGS:
        assert row[f"tags.{tag}"]
    assert row["tags.experiment_id"] == spec.experiment.id
    assert row["tags.protocol_hash"] == pv.protocol_hash
    assert row["tags.dataset_manifest_hash"] == ",".join(
        f"{dataset_id}:{manifest_hash[:12]}"
        for dataset_id, manifest_hash in sorted(pv.manifest_hashes.items())
    )
    assert row["tags.research_claim_allowed"] == "false"
    assert row["tags.status"] == "running"
    tracker.end_run(RunStatus.smoke_ok)


def test_start_run_rejects_missing_required_tag(tmp_path: Path) -> None:
    spec = _spec()
    tracker = MlflowTracker(spec.tracking, tmp_path)
    pv = _pv(spec).model_copy(update={"protocol_hash": ""})
    with pytest.raises(ValueError, match="missing required MLflow tags"):
        tracker.start_run(spec, pv, _env())


def test_log_metrics_requires_metric_fields_and_skips_non_finite(tmp_path: Path) -> None:
    tracker, _, _, run_id = _start_tracker(tmp_path)
    metrics = _metrics(auc=math.inf)
    tracker.log_metrics(metrics)
    tracker.end_run(RunStatus.smoke_ok)

    import mlflow

    run = mlflow.get_run(run_id)
    logged = run.data.metrics
    for key in ("apcer", "bpcer", "acer", "hter", "apcer_print", "apcer_max", "tau"):
        assert key in logged
    assert "auc" not in logged


def test_log_metrics_rejects_invalid_metric_object(tmp_path: Path) -> None:
    tracker, _, _, _ = _start_tracker(tmp_path)
    metrics = _metrics().model_copy()
    object.__setattr__(metrics, "apcer", None)
    with pytest.raises(ValueError, match="missing required MLflow metrics"):
        tracker.log_metrics(metrics)
    tracker.end_run(RunStatus.failed_training)


def test_log_epoch_logs_prefixed_dev_metrics(tmp_path: Path) -> None:
    tracker, _, _, run_id = _start_tracker(tmp_path)
    tracker.log_epoch(1, 0.25, _metrics())
    tracker.end_run(RunStatus.smoke_ok)

    import mlflow

    run = mlflow.get_run(run_id)
    assert run.data.metrics["train_loss"] == 0.25
    assert run.data.metrics["dev_apcer"] == 0.5


def test_find_baseline_searches_across_mlflow_experiments(tmp_path: Path) -> None:
    source = _spec("syn_e02_video_source_only")
    method = _spec("syn_e03_video_full_ft_bf_only")
    source_tracker = MlflowTracker(source.tracking, tmp_path)
    method_tracker = MlflowTracker(method.tracking, tmp_path)
    pv = _pv(source)

    source_run_id = source_tracker.start_run(source, pv, _env())
    source_tracker.log_artifact_json("eval_test.json", {"metrics": _metrics()})
    source_tracker.end_run(RunStatus.success)

    found = method_tracker.find_baseline(
        source.experiment.id, pv.protocol_hash, include_smoke=False
    )
    assert found is not None
    assert found.run_id == source_run_id
    assert found.protocol_hash == pv.protocol_hash
    assert found.metrics.apcer == 0.5


def test_find_baseline_can_include_smoke_runs(tmp_path: Path) -> None:
    spec = _spec("syn_e02_video_source_only")
    tracker = MlflowTracker(spec.tracking, tmp_path)
    pv = _pv(spec)
    run_id = tracker.start_run(spec, pv, _env())
    tracker.log_artifact_json("eval_test.json", {"metrics": _metrics(apcer=0.2, acer=0.1625)})
    tracker.end_run(RunStatus.smoke_ok)

    assert tracker.find_baseline(spec.experiment.id, pv.protocol_hash, include_smoke=False) is None
    found = tracker.find_baseline(spec.experiment.id, pv.protocol_hash, include_smoke=True)
    assert found is not None
    assert found.run_id == run_id
    assert found.metrics.apcer == 0.2
