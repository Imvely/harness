"""Frame-index sampling for clip datasets.

The sampler is deterministic for ``uniform`` and ``consecutive`` policies. The
``random_crop`` policy uses the caller-provided RNG, which lets tests and
DataLoader workers control reproducibility explicitly.
"""

from __future__ import annotations

import random
from typing import Literal, Protocol

import numpy as np

SamplingStrategy = Literal["uniform", "consecutive", "random_crop"]


class _NumpyRng(Protocol):
    def integers(self, low: int, high: int | None = None) -> np.integer: ...


def _randint(rng: random.Random | _NumpyRng, low: int, high_inclusive: int) -> int:
    if isinstance(rng, random.Random):
        return rng.randint(low, high_inclusive)
    return int(rng.integers(low, high_inclusive + 1))


def _pad_last(indices: list[int], target: int) -> list[int]:
    if not indices:
        raise ValueError("cannot pad an empty index list")
    return [*indices, *([indices[-1]] * (target - len(indices)))]


def sample_frame_indices(
    n_frames: int,
    T: int,  # noqa: N803 - contract uses upper-case T for temporal length.
    strategy: SamplingStrategy,
    rng: random.Random | _NumpyRng,
) -> list[int]:
    """Return ``T`` frame indices for a clip with ``n_frames`` frames.

    ``T == 1`` always selects the central frame. When ``n_frames < T``, the
    available sequence is repeat-padded with the last valid frame.
    """
    if n_frames < 1:
        raise ValueError(f"n_frames must be >= 1, got {n_frames}")
    if T < 1:
        raise ValueError(f"T must be >= 1, got {T}")
    if strategy not in ("uniform", "consecutive", "random_crop"):
        raise ValueError(f"unknown frame sampling strategy: {strategy!r}")
    if T == 1:
        return [(n_frames - 1) // 2]

    take = min(n_frames, T)
    if strategy == "uniform":
        if take == 1:
            indices = [0]
        else:
            indices = np.linspace(0, n_frames - 1, num=take, dtype=np.float64)
            indices = [round(x) for x in indices.tolist()]
    else:
        max_start = max(0, n_frames - take)
        if strategy == "consecutive":
            start = max_start // 2
        else:
            start = _randint(rng, 0, max_start) if max_start > 0 else 0
        indices = list(range(start, start + take))

    if len(indices) < T:
        indices = _pad_last(indices, T)
    return indices
