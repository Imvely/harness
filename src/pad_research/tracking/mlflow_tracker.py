"""MLflow tracking adapter for PAD experiments.

The module does not import MLflow at import time. Validators and hooks must stay light and
must be importable without torch or MLflow. ``MlflowTracker.__init__`` sets the tracking
environment and imports MLflow lazily.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from pad_research import paths
from pad_research.config.schema import ExperimentSpec, TrackingSpec, science_hash, spec_hash
from pad_research.experiments.status import RunStatus
from pad_research.metrics.pad_metrics import PadMetrics
from pad_research.protocols.validator import ProtocolValidation
from pad_research.tracking import tags
from pad_research.tracking.env_snapshot import EnvSnapshot
from pad_research.utils.redaction import redact_tag_value


class BaselineRef(BaseModel):
    """Baseline run resolved from MLflow for security-regression comparison."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    metrics: PadMetrics
    protocol_hash: str


def _stringify(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _metric_name(prefix: str, key: str) -> str:
    if not prefix:
        return key
    if prefix.endswith(("_", "/")):
        return f"{prefix}{key}"
    return f"{prefix}_{key}"


def _jsonable(obj: object) -> object:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


class MlflowTracker:
    """Small MLflow wrapper with the tag and metric checks required by the contract."""

    def __init__(self, tracking: TrackingSpec, repo_root: Path) -> None:
        self.tracking = tracking
        self.repo_root = repo_root
        os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
        import mlflow

        self._mlflow = mlflow
        self.tracking_uri = tracking.tracking_uri or paths.default_tracking_uri()
        self._mlflow.set_tracking_uri(self.tracking_uri)

    def _experiment_id(self) -> str:
        existing = self._mlflow.get_experiment_by_name(self.tracking.mlflow_experiment)
        if existing is not None:
            return str(existing.experiment_id)
        artifact_root = (
            paths.artifact_root()
            if self.repo_root.resolve() == paths.repo_root().resolve()
            else self.repo_root / "mlruns_artifacts"
        )
        return str(
            self._mlflow.create_experiment(
                self.tracking.mlflow_experiment,
                artifact_location=str(artifact_root),
            )
        )

    def start_run(
        self,
        spec: ExperimentSpec,
        pv: ProtocolValidation,
        env: EnvSnapshot,
        *,
        adaptation_set_hash: str | None = None,
        run_name: str | None = None,
        model_init: str = "random",
        checkpoint_source: str = "none",
    ) -> str:
        """Start an MLflow run and log the mandatory provenance tags."""
        exp_id = self._experiment_id()
        active = self._mlflow.start_run(
            experiment_id=exp_id,
            run_name=run_name or self.tracking.run_name,
        )
        dataset_manifest_hash = ",".join(
            f"{dataset_id}:{manifest_hash[:12]}"
            for dataset_id, manifest_hash in sorted(pv.manifest_hashes.items())
        )
        tag_values: dict[str, str] = {
            "research_question": spec.experiment.research_question,
            "protocol_id": spec.protocol.protocol_id,
            "protocol_hash": pv.protocol_hash,
            "model_family": spec.model.family,
            "adaptation_method": spec.adaptation.method,
            "target_supervision": spec.protocol.target_adaptation.supervision,
            "dataset_manifest_hash": dataset_manifest_hash,
            "git_sha": env.git_sha or "unknown",
            "status": RunStatus.running.value,
            "experiment_id": spec.experiment.id,
            "science_hash": science_hash(spec),
            "spec_hash": spec_hash(spec),
            "execution_mode": spec.execution.mode,
            "seed": str(spec.training.seed),
            "parent_experiment_id": spec.experiment.parent_experiment_id or "none",
            "baseline_experiment_id": spec.evaluation.baseline_experiment_id or "none",
            "adaptation_set_hash": adaptation_set_hash or pv.adaptation_set_hash or "none",
            "threshold_source": spec.protocol.threshold.source,
            "threshold_rule": spec.protocol.threshold.rule,
            "research_claim_allowed": str(pv.research_claim_allowed).lower(),
            "checkpoint_source": checkpoint_source,
            "model_init": model_init,
            "remote_artifacts": str(
                self.tracking_uri.split(":", 1)[0].lower() not in ("", "file", "sqlite")
            ).lower(),
            **env.as_tags(),
        }
        tag_values = {
            key: redact_tag_value(value, self.repo_root) for key, value in tag_values.items()
        }
        tag_values.update(
            {
                tags.validate_key(k): redact_tag_value(v, self.repo_root)
                for k, v in self.tracking.extra_tags.items()
            }
        )
        missing = [name for name in tags.REQUIRED_TAGS if not tag_values.get(name)]
        if missing:
            self._mlflow.end_run(status="FAILED")
            raise ValueError(f"missing required MLflow tags: {missing}")
        for key in tag_values:
            tags.validate_key(key)
        self._mlflow.set_tags(tag_values)
        return str(active.info.run_id)

    def log_metrics(self, m: PadMetrics, *, prefix: str = "", step: int | None = None) -> None:
        """Log PAD metrics, skipping non-finite values."""
        values: dict[str, float | None] = {
            "apcer": m.apcer,
            "bpcer": m.bpcer,
            "acer": m.acer,
            "hter": m.hter,
            "auc": m.auc,
            "apcer_max": m.apcer_max,
            "apcer_pooled": m.apcer_pooled,
            "tau": m.tau,
            "bpcer_at_apcer_10": m.bpcer_at_apcer_10,
            "bpcer_at_apcer_1": m.bpcer_at_apcer_1,
        }
        for pai, value in sorted(m.apcer_per_pai.items()):
            values[tags.metric_key_for_pai(pai)] = value
        missing = [
            name for name in tags.REQUIRED_METRICS if name not in values or values[name] is None
        ]
        if missing:
            raise ValueError(f"missing required MLflow metrics: {missing}")
        for key, value in values.items():
            metric_key = tags.validate_key(_metric_name(prefix, key))
            if value is None or not math.isfinite(float(value)):
                continue
            self._mlflow.log_metric(metric_key, float(value), step=step)

    def log_epoch(self, epoch: int, train_loss: float, dev: PadMetrics | None) -> None:
        """Log one epoch loss and optional dev metrics."""
        if math.isfinite(float(train_loss)):
            self._mlflow.log_metric("train_loss", float(train_loss), step=epoch)
        if dev is not None:
            self.log_metrics(dev, prefix="dev", step=epoch)

    def log_artifact_json(self, name: str, obj: object) -> None:
        """Write ``obj`` as JSON and log it as an MLflow artifact."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(_jsonable(obj), ensure_ascii=True, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            artifact_parent = out.parent.relative_to(tmp)
            artifact_path = None if artifact_parent == Path(".") else str(artifact_parent)
            self._mlflow.log_artifact(str(out), artifact_path=artifact_path)

    def log_artifact_file(self, path: Path | str) -> None:
        """Log an existing file as an MLflow artifact."""
        self._mlflow.log_artifact(str(path))

    def log_figure(self, fig: Any, name: str) -> None:
        """Log a Matplotlib figure without importing Matplotlib here."""
        self._mlflow.log_figure(fig, name)

    def set_tag(self, key: str, value: object) -> None:
        """Set one validated MLflow tag on the active run."""
        self._mlflow.set_tag(
            tags.validate_key(key),
            redact_tag_value(_stringify(value), self.repo_root),
        )

    def find_baseline(
        self,
        experiment_id: str,
        protocol_hash: str,
        include_smoke: bool,
    ) -> BaselineRef | None:
        """Find the newest comparable baseline run and load its ``eval_test.json`` metrics."""
        filter_string = (
            f"tags.experiment_id = '{experiment_id}' and tags.protocol_hash = '{protocol_hash}'"
        )
        if not include_smoke:
            filter_string += " and tags.status = 'success'"
        runs = self._mlflow.search_runs(
            search_all_experiments=True,
            filter_string=filter_string,
            order_by=["attributes.start_time DESC"],
        )
        for _, row in runs.iterrows():
            run_id = str(row["run_id"])
            metrics = self._load_eval_metrics(run_id)
            if metrics is not None:
                return BaselineRef(run_id=run_id, metrics=metrics, protocol_hash=protocol_hash)
        return None

    def _load_eval_metrics(self, run_id: str) -> PadMetrics | None:
        import mlflow.artifacts as mlflow_artifacts

        try:
            obj = mlflow_artifacts.load_dict(f"runs:/{run_id}/eval_test.json")
        except Exception:
            return None
        payload = obj.get("metrics", obj) if isinstance(obj, dict) else obj
        try:
            return PadMetrics.model_validate(payload)
        except ValueError:
            return None

    def end_run(self, status: RunStatus) -> None:
        """Update the terminal status tag and end the active MLflow run."""
        self._mlflow.set_tag("status", status.value)
        self._mlflow.end_run()
