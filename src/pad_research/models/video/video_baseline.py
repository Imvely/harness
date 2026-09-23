"""Video baseline (contract §9.2 item 4): frame encoder -> temporal transformer -> head."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal

import torch
from torch import Tensor, nn

from pad_research.models.base import ModelOutput, PADModel
from pad_research.models.encoders import TinyCNN
from pad_research.models.heads import LinearHead

MAX_FRAMES = 64


class FrameEncoderTemporalTransformer(PADModel):
    """Shared :class:`TinyCNN` per frame + learned positional embedding + transformer.

    The temporal transformer, positional embedding and optional CLS token all belong to
    the *encoder* parameter group; the head is the :class:`LinearHead` only.
    """

    family = "video_baseline"

    def __init__(
        self,
        embed_dim: int = 64,
        width: int = 16,
        depth: int = 1,
        heads: int = 4,
        dropout: float = 0.0,
        pooling: Literal["mean", "cls"] = "mean",
    ) -> None:
        super().__init__()
        if pooling not in ("mean", "cls"):
            raise ValueError(f"pooling must be 'mean' or 'cls', got {pooling!r}")
        if embed_dim % heads != 0:
            raise ValueError(f"embed_dim={embed_dim} must be divisible by heads={heads}")
        self.embed_dim = embed_dim
        self.pooling = pooling
        self.frame_encoder = TinyCNN(width=width, embed_dim=embed_dim)
        self.pos_embedding = nn.Parameter(torch.zeros(1, MAX_FRAMES, embed_dim))
        nn.init.trunc_normal_(self.pos_embedding, std=0.02)
        if pooling == "cls":
            self.cls_token = nn.Parameter(torch.zeros(1, 1, embed_dim))
            nn.init.trunc_normal_(self.cls_token, std=0.02)
        layer = nn.TransformerEncoderLayer(
            d_model=embed_dim,
            nhead=heads,
            dim_feedforward=2 * embed_dim,
            dropout=dropout,
            batch_first=True,
            norm_first=True,
        )
        self.temporal = nn.TransformerEncoder(layer, num_layers=depth, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(embed_dim)
        self.head = LinearHead(embed_dim)

    def forward(self, clip: Tensor) -> ModelOutput:
        batch, frames = clip.shape[0], clip.shape[1]
        if frames > MAX_FRAMES:
            raise ValueError(f"clip has T={frames} frames; maximum supported is {MAX_FRAMES}")
        flat = clip.reshape(batch * frames, *clip.shape[2:])
        frame_emb = self.frame_encoder(flat).reshape(batch, frames, self.embed_dim)
        tokens = frame_emb + self.pos_embedding[:, :frames]
        if self.pooling == "cls":
            tokens = torch.cat([self.cls_token.expand(batch, -1, -1), tokens], dim=1)
        encoded = self.norm(self.temporal(tokens))
        clip_emb = encoded[:, 0] if self.pooling == "cls" else encoded.mean(dim=1)
        return ModelOutput(
            logits=self.head(clip_emb),
            clip_embedding=clip_emb,
            frame_embeddings=frame_emb,
        )

    def encoder_parameters(self) -> Iterator[nn.Parameter]:
        head_ids = {id(p) for p in self.head.parameters()}
        return (p for p in self.parameters() if id(p) not in head_ids)

    def head_parameters(self) -> Iterator[nn.Parameter]:
        return self.head.parameters()
