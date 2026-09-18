"""Experiment specification (contract §16) validated by Pydantic after Hydra composition.

The spec IS the Hydra config: ``configs/exp/<name>.yaml`` (``+exp=<name>``) composes with the
``model/ data/ adaptation/ protocol/`` groups and ``configs/config.yaml``; the resolved
container is validated here.

Two hashes (ADR-005): ``science_hash`` excludes execution mode, tracking, checkpoint
sources and free text (``SCIENCE_EXCLUDE``) so smoke and full runs of one experiment share
it; ``spec_hash`` covers the whole resolved spec and identifies artifacts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pad_research.protocols.hashing import HASH_EXCLUDED
from pad_research.protocols.schema import ProtocolSpec
from pad_research.utils.canonical_json import canonical_json, sha256_text

ResearchQuestion = Literal["RQ1", "RQ2", "RQ3", "RQ4", "harness"]
ModelFamily = Literal["frame_baseline", "video_baseline"]
AdaptationMethod = Literal["none", "full_finetune", "head_only", "prototype", "spoof_preserve"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExperimentMeta(_Strict):
    id: str = Field(pattern=r"^exp_[a-z0-9_]+$")
    title: str
    hypothesis: str = ""
    research_question: ResearchQuestion = "harness"
    parent_experiment_id: str | None = None


class InputSpec(_Strict):
    modality: Literal["rgb"] = "rgb"
    frames: int = Field(ge=1, le=64)
    frame_sampling: Literal["uniform", "consecutive", "random_crop"] = "uniform"
    image_size: tuple[int, int]


class ModelSpec(_Strict):
    family: ModelFamily
    checkpoint: str | None = None
    input: InputSpec
    net: dict[str, Any]

    @field_validator("net")
    @classmethod
    def _net_has_target(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "_target_" not in v:
            raise ValueError("model.net must declare a Hydra _target_")
        return v


class LoaderSpec(_Strict):
    batch_size: int = Field(ge=1)
    num_workers: int = Field(default=0, ge=0)
    pin_memory: bool = False
    drop_last: bool = True


class DataSpec(_Strict):
    name: str
    manifests_dir: str = "data/manifests"
    root_env_var: str = "PAD_DATA_ROOT"
    source: list[str] | None = None  # optional §16 shape; must agree with the protocol
    target: list[str] | None = None
    loader: LoaderSpec
    transform: dict[str, Any] = Field(default_factory=dict)

    @field_validator("manifests_dir")
    @classmethod
    def _relative(cls, v: str) -> str:
        if v.startswith(("/", "~")) or ".." in v.split("/"):
            raise ValueError("data.manifests_dir must be a repo-relative path")
        return v


class AdaptationSpec(_Strict):
    enabled: bool
    method: AdaptationMethod
    implemented: bool = True
    source_run_id: str | None = None
    source_checkpoint: str | None = None
    epochs: int = Field(default=1, ge=0)
    learning_rate: float = Field(default=1e-4, ge=0)
    batch_size: int = Field(default=8, ge=1)


class TrainingSpec(_Strict):
    seed: int
    epochs: int = Field(ge=0)
    batch_size: int = Field(ge=1)
    learning_rate: float = Field(gt=0)
    weight_decay: float = Field(default=0.0, ge=0)
    optimizer: Literal["adamw", "sgd"] = "adamw"
    deterministic: bool = True
    device: Literal["auto", "cpu", "cuda"] = "auto"
    num_workers: int = Field(default=0, ge=0)
    checkpoint_selection: Literal["last", "best_dev_acer"] = "last"


class LatencySpec(_Strict):
    warmup: int = Field(default=2, ge=0)
    repetitions: int = Field(default=5, ge=1)
    batch_size: int = Field(default=1, ge=1)


class EvaluationSpec(_Strict):
    metrics: list[Literal["APCER", "BPCER", "ACER", "HTER", "AUC"]]
    per_attack_apcer: bool = True
    measure_latency: bool = True
    latency: LatencySpec = LatencySpec()
    baseline_experiment_id: str | None = None
    checkpoint: str | None = None


class SmokeLimits(_Strict):
    """Hard upper bounds keep a 'smoke' run from silently becoming a full run."""

    max_batches: int = Field(default=2, ge=1, le=20)
    max_epochs: int = Field(default=1, ge=1, le=1)
    max_eval_batches: int = Field(default=2, ge=1, le=20)
    latency_repetitions: int = Field(default=1, ge=1, le=3)


class ExecutionSpec(_Strict):
    mode: Literal["smoke", "full"] = "smoke"
    smoke_test_first: bool = True
    allow_full_gpu_run: bool = False
    allow_dirty_tree: bool = False
    require_gpu: bool = False
    expected_gpu: str | None = None
    smoke: SmokeLimits = SmokeLimits()


class TrackingSpec(_Strict):
    mlflow_experiment: str = Field(min_length=1)
    tracking_uri: str | None = None
    run_name: str | None = None
    log_checkpoint: bool = True
    extra_tags: dict[str, str] = Field(default_factory=dict)


class ExperimentSpec(_Strict):
    experiment: ExperimentMeta
    model: ModelSpec
    data: DataSpec
    adaptation: AdaptationSpec
    protocol: ProtocolSpec
    training: TrainingSpec
    evaluation: EvaluationSpec
    execution: ExecutionSpec = ExecutionSpec()
    tracking: TrackingSpec

    @model_validator(mode="after")
    def _cross_checks(self) -> ExperimentSpec:
        a, p, m, x = self.adaptation, self.protocol, self.model, self.execution
        if a.enabled and not p.target_adaptation.enabled:
            raise ValueError(
                "ADAPTATION_WITHOUT_PROTOCOL_BUDGET: adaptation.enabled requires "
                "protocol.target_adaptation.enabled (the protocol owns the adaptation budget)"
            )
        if (a.method == "none") != (not a.enabled):
            raise ValueError("ADAPTATION_METHOD_MISMATCH: method 'none' <=> enabled false")
        if a.enabled and not a.implemented:
            raise ValueError(
                f"NOT_IMPLEMENTED_IN_PHASE0: adaptation method {a.method!r} is registered "
                "but not implemented (contract §11: prove the problem with baselines first)"
            )
        if m.family == "video_baseline" and m.input.frames < 2:
            raise ValueError("VIDEO_NEEDS_FRAMES: video_baseline requires model.input.frames >= 2")
        if p.status == "draft" and x.mode != "smoke":
            raise ValueError(
                "DRAFT_PROTOCOL_SMOKE_ONLY: draft protocols may only run in smoke mode"
            )
        if x.mode == "full" and not x.allow_full_gpu_run:
            raise ValueError(
                "FULL_REQUIRES_ALLOW_FLAG: execution.mode=full needs allow_full_gpu_run"
            )
        if (
            self.data.source is not None
            and sorted(s.lower() for s in self.data.source) != p.source_datasets
        ):
            raise ValueError(
                "DATA_PROTOCOL_DATASET_MISMATCH: data.source != protocol.source_datasets"
            )
        if (
            self.data.target is not None
            and sorted(s.lower() for s in self.data.target) != p.target_dataset
        ):
            raise ValueError(
                "DATA_PROTOCOL_DATASET_MISMATCH: data.target != protocol.target_dataset"
            )
        if self.evaluation.checkpoint is not None and m.checkpoint is not None:
            raise ValueError("CHECKPOINT_AMBIGUOUS: set model.checkpoint or evaluation.checkpoint")
        return self


#: Fields excluded from ``science_hash`` (pydantic nested-exclude form).
SCIENCE_EXCLUDE: dict[str, Any] = {
    "execution": True,
    "tracking": True,
    "adaptation": {"source_run_id", "source_checkpoint"},
    "experiment": {"title", "hypothesis", "parent_experiment_id"},
    "protocol": set(HASH_EXCLUDED),
    "evaluation": {"baseline_experiment_id", "latency", "measure_latency", "checkpoint"},
    "training": {"device", "num_workers"},
}


def science_hash(spec: ExperimentSpec) -> str:
    return sha256_text(canonical_json(spec.model_dump(mode="json", exclude=SCIENCE_EXCLUDE)))


def spec_hash(spec: ExperimentSpec) -> str:
    return sha256_text(canonical_json(spec.model_dump(mode="json")))
