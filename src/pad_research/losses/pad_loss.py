"""PAD loss and score functions.

Label/score convention (``pad_research.conventions``): spoof = 1, bona fide = 0,
``attack_score = sigmoid(logit) = P(spoof)``.

Extension point (contract §13): the conceptual total loss is
``L_total = L_pad + λ_da L_domain + λ_preserve L_spoof_preserve + λ_temp L_temporal``.
Only ``L_pad`` exists in Phase 0; the other terms are added as separate functions in
this module once the baseline experiments (§11) show they are needed, each with its own
ablation.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F  # noqa: N812
from torch import Tensor


def bce_pad_loss(logits: Tensor, labels: Tensor) -> Tensor:
    """Binary cross-entropy with logits; ``labels`` are ``{0, 1}`` with spoof = 1."""
    return F.binary_cross_entropy_with_logits(logits, labels.to(logits.dtype))


def attack_score(logits: Tensor) -> Tensor:
    """``P(spoof) = sigmoid(logit)``; higher = more spoof-like."""
    return torch.sigmoid(logits)
