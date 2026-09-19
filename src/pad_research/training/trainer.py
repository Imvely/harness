"""Minimal supervised trainer used by source-only and adaptation runs."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

import torch
from torch import Tensor

from pad_research.adaptation.base import AdaptationStrategy
from pad_research.config.schema import ExperimentSpec, SmokeLimits
from pad_research.data.clip_dataset import ClipBatch
from pad_research.metrics.pad_metrics import PadMetrics
from pad_research.models.base import PADModel


class _Tracker(Protocol):
    def log_epoch(self, epoch: int, train_loss: float, dev: PadMetrics | None) -> None: ...


@dataclass(frozen=True)
class TrainResult:
    epochs_run: int
    steps: int
    train_curve: list[dict[str, float | int]]
    wall_clock_s: float


def _train_hparams(spec: ExperimentSpec, strategy: AdaptationStrategy) -> tuple[int, float]:
    if strategy.name == "none":
        return spec.training.epochs, spec.training.learning_rate
    return spec.adaptation.epochs, spec.adaptation.learning_rate


def _optimizer(
    spec: ExperimentSpec, params: list[torch.nn.Parameter], lr: float
) -> torch.optim.Optimizer:
    if spec.training.optimizer == "adamw":
        return torch.optim.AdamW(params, lr=lr, weight_decay=spec.training.weight_decay)
    if spec.training.optimizer == "sgd":
        return torch.optim.SGD(params, lr=lr, weight_decay=spec.training.weight_decay)
    raise ValueError(f"unknown optimizer {spec.training.optimizer!r}")


class Trainer:
    """Train ``model`` with ``strategy`` on ``loaders['train']``."""

    def __init__(
        self,
        model: PADModel,
        strategy: AdaptationStrategy,
        loaders: Mapping[str, Iterable[ClipBatch]],
        spec: ExperimentSpec,
        tracker: _Tracker | None,
        limits: SmokeLimits | None,
        device: torch.device,
    ) -> None:
        self.model = model
        self.strategy = strategy
        self.loaders = loaders
        self.spec = spec
        self.tracker = tracker
        self.limits = limits
        self.device = device

    def fit(self) -> TrainResult:
        """Run training and return the loss curve."""
        self.model.to(self.device)
        self.strategy.prepare(self.model)
        epochs, lr = _train_hparams(self.spec, self.strategy)
        if self.limits is not None:
            epochs = min(epochs, self.limits.max_epochs)
        trainable = self.strategy.trainable_parameters(self.model)
        if epochs > 0 and not trainable:
            raise RuntimeError("no trainable parameters")
        optimizer = _optimizer(self.spec, trainable, lr) if trainable else None
        train_loader = self.loaders["train"]
        start = time.perf_counter()
        steps = 0
        curve: list[dict[str, float | int]] = []

        for epoch in range(1, epochs + 1):
            self.model.train()
            epoch_loss = 0.0
            epoch_steps = 0
            for batch_index, batch in enumerate(train_loader, start=1):
                if self.limits is not None and batch_index > self.limits.max_batches:
                    break
                assert optimizer is not None
                clip = cast(Tensor, batch["clip"]).to(self.device, non_blocking=True)
                labels = cast(Tensor, batch["label"]).to(self.device, non_blocking=True).float()
                optimizer.zero_grad(set_to_none=True)
                output = self.model(clip)
                loss = self.strategy.loss(output, labels)
                loss.backward()
                optimizer.step()
                loss_value = float(loss.detach().cpu().item())
                epoch_loss += loss_value
                epoch_steps += 1
                steps += 1
            mean_loss = epoch_loss / max(epoch_steps, 1)
            curve.append({"epoch": epoch, "train_loss": mean_loss, "steps": epoch_steps})
            if self.tracker is not None:
                self.tracker.log_epoch(epoch, mean_loss, None)

        return TrainResult(
            epochs_run=epochs,
            steps=steps,
            train_curve=curve,
            wall_clock_s=time.perf_counter() - start,
        )
