"""Frame encoders (one image ``(3, H, W)`` -> one embedding ``(D,)``)."""

from __future__ import annotations

from torch import Tensor, nn


def _block(in_ch: int, out_ch: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1, bias=False),
        nn.GroupNorm(num_groups=min(4, out_ch), num_channels=out_ch),
        nn.ReLU(inplace=True),
        nn.MaxPool2d(kernel_size=2),
    )


class TinyCNN(nn.Module):
    """Three conv blocks + global average pooling + linear projection.

    GroupNorm is used instead of BatchNorm on purpose: batch size 1 works in train mode
    and freezing the encoder (``HeadOnly``) needs no BN-eval special case, because the
    normalisation has no running statistics.
    """

    def __init__(self, width: int = 16, embed_dim: int = 64) -> None:
        super().__init__()
        self.width = width
        self.embed_dim = embed_dim
        self.features = nn.Sequential(
            _block(3, width),
            _block(width, width * 2),
            _block(width * 2, width * 4),
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.proj = nn.Linear(width * 4, embed_dim)

    def forward(self, frames: Tensor) -> Tensor:
        """``(N, 3, H, W)`` -> ``(N, D)``."""
        feats = self.pool(self.features(frames)).flatten(1)
        return self.proj(feats)
