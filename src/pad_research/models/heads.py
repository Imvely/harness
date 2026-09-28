"""Classifier heads mapping an embedding ``(N, D)`` to a spoof logit ``(N,)``."""

from __future__ import annotations

from torch import Tensor, nn


class LinearHead(nn.Module):
    """Single linear layer producing one spoof logit per embedding."""

    def __init__(self, embed_dim: int) -> None:
        super().__init__()
        self.fc = nn.Linear(embed_dim, 1)

    def forward(self, embedding: Tensor) -> Tensor:
        """``(N, D)`` -> ``(N,)`` logits."""
        return self.fc(embedding).squeeze(-1)
