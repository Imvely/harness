"""Evaluation helpers: score collection, PAD metrics, latency and ROC plots."""

from __future__ import annotations

import time
from collections.abc import Iterable
from pathlib import Path
from typing import cast

import numpy as np
import torch
from pydantic import BaseModel, ConfigDict
from torch import Tensor

from pad_research.adaptation.base import AdaptationStrategy
from pad_research.config.schema import ExperimentSpec, science_hash, spec_hash
from pad_research.data.clip_dataset import ClipBatch
from pad_research.evaluation.scores import Domain, Role, ScoreTable
from pad_research.experiments.status import RunStatus
from pad_research.metrics.pad_metrics import PadMetrics, compute_pad_metrics
from pad_research.metrics.threshold import NotFittedError, ThresholdPolicy
from pad_research.models.base import PADModel
from pad_research.protocols.validator import ProtocolValidation


class LatencyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ms_per_clip: float
    fps_equiv: float
    conditions: dict[str, str | int | float | bool]
    peak_memory_mb: float | None = None
    smoke: bool = False


class EvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    science_hash: str
    spec_hash: str
    protocol_id: str
    protocol_hash: str
    manifest_hashes: dict[str, str]
    adaptation_set_hash: str | None
    seed: int
    mode: str
    domain: Domain
    role: Role
    metrics: PadMetrics
    threshold: ThresholdPolicy
    n_test: int
    latency: LatencyResult | None = None
    status: RunStatus


def collect_scores(
    model: PADModel,
    strategy: AdaptationStrategy,
    loader: Iterable[ClipBatch],
    device: torch.device,
    max_batches: int | None,
    role: Role,
    domain: Domain,
) -> ScoreTable:
    """Collect attack scores for ``loader`` without fitting a threshold."""
    model.eval()
    scores: list[float] = []
    labels: list[bool] = []
    pais: list[str] = []
    sample_ids: list[str] = []
    subject_ids: list[str] = []
    with torch.no_grad():
        for batch_index, batch in enumerate(loader, start=1):
            if max_batches is not None and batch_index > max_batches:
                break
            clip = cast(Tensor, batch["clip"]).to(device, non_blocking=True)
            label_tensor = cast(Tensor, batch["label"]).detach().cpu().to(dtype=torch.long)
            output = model(clip)
            score = strategy.score(output).detach().cpu().to(dtype=torch.float64).numpy()
            scores.extend(float(x) for x in score.ravel().tolist())
            labels.extend(bool(int(x)) for x in label_tensor.numpy().ravel().tolist())
            pais.extend(str(x) for x in batch["pai"])
            sample_ids.extend(str(x) for x in batch["sample_id"])
            subject_ids.extend(str(x) for x in batch["subject_id"])
    return ScoreTable.from_arrays(role, domain, sample_ids, subject_ids, scores, labels, pais)


def evaluate(
    score_table: ScoreTable,
    threshold: ThresholdPolicy,
    spec: ExperimentSpec,
    protocol_validation: ProtocolValidation,
    *,
    latency: LatencyResult | None = None,
    status: RunStatus = RunStatus.running,
) -> EvalResult:
    """Compute PAD metrics for ``score_table`` with a fixed fitted threshold."""
    if threshold.tau is None:
        raise NotFittedError("evaluate requires a fitted ThresholdPolicy")
    score, y_attack, pai = score_table.to_numpy()
    metrics = compute_pad_metrics(
        score,
        y_attack,
        pai,
        threshold.tau,
        acer_policy=spec.protocol.acer_policy,
    )
    return EvalResult(
        experiment_id=spec.experiment.id,
        science_hash=science_hash(spec),
        spec_hash=spec_hash(spec),
        protocol_id=spec.protocol.protocol_id,
        protocol_hash=protocol_validation.protocol_hash,
        manifest_hashes=protocol_validation.manifest_hashes,
        adaptation_set_hash=protocol_validation.adaptation_set_hash,
        seed=spec.training.seed,
        mode=spec.execution.mode,
        domain=score_table.domain,
        role=score_table.role,
        metrics=metrics,
        threshold=threshold,
        n_test=score_table.n,
        latency=latency,
        status=status,
    )


def measure_latency(
    model: PADModel,
    clip_shape: tuple[int, int, int, int],
    device: torch.device,
    warmup: int,
    repetitions: int,
    batch_size: int,
    *,
    smoke: bool = False,
) -> LatencyResult:
    """Measure average forward-pass latency per clip.

    Preprocessing and face detection are not included.
    """
    if repetitions < 1:
        raise ValueError("repetitions must be >= 1")
    model.eval()
    model.to(device)
    clip = torch.zeros((batch_size, *clip_shape), dtype=torch.float32, device=device)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    with torch.no_grad():
        for _ in range(warmup):
            _ = model(clip)
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        start = time.perf_counter()
        for _ in range(repetitions):
            _ = model(clip)
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        elapsed_s = time.perf_counter() - start
    ms_per_clip = elapsed_s / (repetitions * batch_size) * 1000.0
    peak = (
        float(torch.cuda.max_memory_allocated(device) / (1024 * 1024))
        if device.type == "cuda"
        else None
    )
    return LatencyResult(
        ms_per_clip=ms_per_clip,
        fps_equiv=1000.0 / ms_per_clip if ms_per_clip > 0 else float("inf"),
        conditions={
            "clip_length": clip_shape[0],
            "resolution": f"{clip_shape[2]}x{clip_shape[3]}",
            "includes_preprocessing": False,
            "includes_face_detector": False,
            "batch_size": batch_size,
            "device": str(device),
            "warmup": warmup,
            "repetitions": repetitions,
            "smoke": smoke,
        },
        peak_memory_mb=peak,
        smoke=smoke,
    )


def roc_png(scores: ScoreTable, path: Path | str) -> Path:
    """Write a ROC curve PNG for ``scores`` and return the output path."""
    from matplotlib import pyplot as plt
    from sklearn.metrics import auc, roc_curve

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    score, y_attack, _ = scores.to_numpy()
    fpr, tpr, _ = roc_curve(y_attack.astype(int), score, drop_intermediate=False)
    roc_auc = auc(fpr, tpr)
    fig, ax = plt.subplots(figsize=(4, 4), dpi=120)
    ax.plot(fpr, tpr, label=f"AUC={roc_auc:.3f}")
    ax.plot(np.asarray([0.0, 1.0]), np.asarray([0.0, 1.0]), linestyle="--", color="0.5")
    ax.set_xlabel("FPR")
    ax.set_ylabel("TPR")
    ax.set_title("ROC")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out
