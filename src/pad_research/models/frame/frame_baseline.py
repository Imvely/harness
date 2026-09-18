"""Frame-level baseline (contract §9.1): per-frame logits averaged over the clip."""

from __future__ import annotations

from collections.abc import Iterator

from torch import Tensor, nn

from pad_research.models.base import ModelOutput, PADModel
from pad_research.models.encoders import TinyCNN
from pad_research.models.heads import LinearHead


class TinyFrameBaseline(PADModel):
    """Shared :class:`TinyCNN` per frame, :class:`LinearHead` per frame, mean over ``T``.

    With ``T=1`` (the default frame config) this is a plain image classifier; with
    ``T>1`` it is the "no temporal modelling" control for the video baseline.
    """

    family = "frame_baseline"

    def __init__(self, embed_dim: int = 64, width: int = 16) -> None:
        super().__init__()
        self.embed_dim = embed_dim
        self.encoder = TinyCNN(width=width, embed_dim=embed_dim)
        self.head = LinearHead(embed_dim)

    def forward(self, clip: Tensor) -> ModelOutput:
        batch, frames = clip.shape[0], clip.shape[1]
        flat = clip.reshape(batch * frames, *clip.shape[2:])
        frame_emb = self.encoder(flat).reshape(batch, frames, self.embed_dim)
        frame_logits = self.head(frame_emb.reshape(batch * frames, self.embed_dim))
        logits = frame_logits.reshape(batch, frames).mean(dim=1)
        return ModelOutput(
            logits=logits,
            clip_embedding=frame_emb.mean(dim=1),
            frame_embeddings=frame_emb,
        )

    def encoder_parameters(self) -> Iterator[nn.Parameter]:
        return self.encoder.parameters()

    def head_parameters(self) -> Iterator[nn.Parameter]:
        return self.head.parameters()
