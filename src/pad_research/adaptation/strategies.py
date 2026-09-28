"""Concrete adaptation strategies and the ``build_strategy`` factory."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from torch import nn

from pad_research.adaptation.base import AdaptationStrategy, BaseStrategy
from pad_research.models.base import PADModel


class NoAdaptation(BaseStrategy):
    """Baseline A (source only): plain supervised training, no adaptation."""

    name = "none"


class FullFinetune(BaseStrategy):
    """Baseline B: every layer trainable on target bona fide only."""

    name = "full_finetune"


class HeadOnly(BaseStrategy):
    """Baseline C / §12.1: encoder frozen, head only."""

    name = "head_only"

    def prepare(self, model: PADModel) -> None:
        model.set_encoder_trainable(False)
        for param in model.head_parameters():
            param.requires_grad_(True)

    def trainable_parameters(self, model: PADModel) -> list[nn.Parameter]:
        return [p for p in model.head_parameters() if p.requires_grad]


def _not_implemented(phase: str) -> Callable[[], AdaptationStrategy]:
    def factory() -> AdaptationStrategy:
        raise NotImplementedError(f"Phase {phase}: not implemented in Phase 0")

    return factory


STRATEGIES: dict[str, Callable[[], AdaptationStrategy]] = {
    "none": NoAdaptation,
    "full_finetune": FullFinetune,
    "head_only": HeadOnly,
    "prototype": _not_implemented("5"),
    "spoof_preserve": _not_implemented("6"),
}


def build_strategy(adaptation_cfg: Mapping[str, Any]) -> AdaptationStrategy:
    """Map ``adaptation_cfg["method"]`` to a strategy instance.

    Raises ``NotImplementedError`` for registered-but-unimplemented methods and
    ``KeyError`` for unknown names.
    """
    method = adaptation_cfg["method"]
    try:
        factory = STRATEGIES[method]
    except KeyError as exc:
        raise KeyError(
            f"unknown adaptation method {method!r}; known: {sorted(STRATEGIES)}"
        ) from exc
    return factory()
