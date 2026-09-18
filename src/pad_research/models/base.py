"""Model shape contract shared by frame and video PAD models.

Every model consumes a float32 clip ``(B, T, 3, H, W)`` in ``[0, 1]`` and returns a
:class:`ModelOutput`. Frame models treat ``T`` as extra batch samples; video models
consume the temporal axis. Callers never need to know which family they hold.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

from torch import Tensor, nn


@dataclass
class ModelOutput:
    """Output of a :class:`PADModel` forward pass.

    Attributes:
        logits: ``(B,)`` spoof logits (``sigmoid(logit) = P(spoof)``, see ``conventions``).
        clip_embedding: ``(B, D)`` clip-level embedding (prototype extension point, §12.2).
        frame_embeddings: ``(B, T, D)`` per-frame embeddings or ``None`` if unavailable.
    """

    logits: Tensor
    clip_embedding: Tensor
    frame_embeddings: Tensor | None


class PADModel(nn.Module):
    """Abstract PAD model: clip in, :class:`ModelOutput` out.

    Subclasses must partition their parameters into *encoder* and *head* so adaptation
    strategies (contract §10, §12.1) can freeze one side without knowing the architecture.
    """

    family: str
    embed_dim: int

    @abstractmethod
    def forward(self, clip: Tensor) -> ModelOutput:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Run the model on ``clip`` of shape ``(B, T, 3, H, W)`` (float32 in ``[0, 1]``)."""

    @abstractmethod
    def encoder_parameters(self) -> Iterator[nn.Parameter]:
        """Parameters of the representation part (everything except the head)."""

    @abstractmethod
    def head_parameters(self) -> Iterator[nn.Parameter]:
        """Parameters of the classifier head only."""

    def embed(self, clip: Tensor) -> Tensor:
        """Return the ``(B, D)`` clip embedding (Phase 5 prototype extension point)."""
        return self(clip).clip_embedding

    def set_encoder_trainable(self, flag: bool) -> None:
        """Set ``requires_grad`` on every encoder parameter (head is left untouched)."""
        for param in self.encoder_parameters():
            param.requires_grad_(flag)

    def __call__(self, clip: Tensor) -> ModelOutput:
        return super().__call__(clip)
