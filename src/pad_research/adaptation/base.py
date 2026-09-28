"""Adaptation strategy protocol (contract §10 baselines, §12 preservation ideas)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from torch import Tensor, nn

from pad_research.losses.pad_loss import attack_score, bce_pad_loss
from pad_research.models.base import ModelOutput, PADModel


@runtime_checkable
class AdaptationStrategy(Protocol):
    """What the trainer and evaluator need from an adaptation method."""

    name: str

    def prepare(self, model: PADModel) -> None:
        """Freeze / unfreeze parameters before training starts."""
        ...

    def trainable_parameters(self, model: PADModel) -> list[nn.Parameter]:
        """Parameters to hand to the optimizer."""
        ...

    def loss(self, output: ModelOutput, labels: Tensor) -> Tensor:
        """Training loss for one batch (``labels`` float ``{0, 1}``, spoof = 1)."""
        ...

    def score(self, output: ModelOutput) -> Tensor:
        """Attack score ``(B,)`` used for thresholding and metrics."""
        ...

    def state(self) -> dict[str, Any]:
        """JSON-able description saved with checkpoints."""
        ...


class BaseStrategy:
    """Defaults: every parameter trainable, BCE loss, sigmoid score."""

    name: str = "base"

    def prepare(self, model: PADModel) -> None:
        for param in model.parameters():
            param.requires_grad_(True)

    def trainable_parameters(self, model: PADModel) -> list[nn.Parameter]:
        return [p for p in model.parameters() if p.requires_grad]

    def loss(self, output: ModelOutput, labels: Tensor) -> Tensor:
        return bce_pad_loss(output.logits, labels)

    def score(self, output: ModelOutput) -> Tensor:
        return attack_score(output.logits)

    def state(self) -> dict[str, Any]:
        return {"name": self.name}
