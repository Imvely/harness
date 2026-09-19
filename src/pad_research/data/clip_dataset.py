"""Torch dataset for manifest records that point to clips.

Decoding lives in :mod:`pad_research.data.media`, which handles every manifest media type.
This module owns only the sampling, resizing and batching contract.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

import torch
import torch.nn.functional as F  # noqa: N812
from torch import Tensor
from torch.utils.data import Dataset

from pad_research.conventions import LABEL_BONA_FIDE, LABEL_SPOOF
from pad_research.data.manifest import Label, ManifestRecord
from pad_research.data.media import probe_n_frames, read_frames
from pad_research.data.sampling import SamplingStrategy, sample_frame_indices


class ClipItem(TypedDict):
    clip: Tensor
    label: int
    pai: str
    sample_id: str
    subject_id: str


class ClipBatch(TypedDict):
    clip: Tensor
    label: Tensor
    pai: list[str]
    sample_id: list[str]
    subject_id: list[str]


def _resize_clip(clip: Tensor, image_size: tuple[int, int]) -> Tensor:
    if tuple(clip.shape[-2:]) == tuple(image_size):
        return clip
    return F.interpolate(
        clip,
        size=image_size,
        mode="bilinear",
        align_corners=False,
    )


def _label_int(label: Label) -> int:
    return LABEL_BONA_FIDE if label == Label.bona_fide else LABEL_SPOOF


class ClipDataset(Dataset[ClipItem]):
    """Map manifest records to model-ready clip tensors."""

    def __init__(
        self,
        records: Sequence[ManifestRecord],
        root: Path | str,
        frames: int,
        sampling: SamplingStrategy,
        image_size: tuple[int, int],
        train: bool,
        seed: int,
    ) -> None:
        self.records = list(records)
        self.root = root
        self.frames = int(frames)
        self.sampling: SamplingStrategy = sampling
        self.image_size: tuple[int, int] = (int(image_size[0]), int(image_size[1]))
        self.train = bool(train)
        self.seed = int(seed)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> ClipItem:
        record = self.records[index]
        # Probe first, then decode only the sampled positions: a real video record must never
        # be decoded in full just to keep `frames` of it (see pad_research.data.media).
        n_frames = probe_n_frames(record, self.root)
        rng = random.Random(self.seed + index + (10_000_000 if self.train else 0))
        indices = sample_frame_indices(n_frames, self.frames, self.sampling, rng)
        clip_np = read_frames(record, self.root, indices)
        clip = torch.from_numpy(clip_np).to(dtype=torch.float32)
        clip = _resize_clip(clip, self.image_size)
        return {
            "clip": clip,
            "label": _label_int(record.label),
            "pai": record.pai.value,
            "sample_id": record.sample_id,
            "subject_id": record.subject_id,
        }


def collate(items: Sequence[ClipItem]) -> ClipBatch:
    """Collate :class:`ClipItem` values into tensors plus aligned string columns."""
    if not items:
        raise ValueError("cannot collate an empty batch")
    return {
        "clip": torch.stack([item["clip"] for item in items], dim=0),
        "label": torch.as_tensor([item["label"] for item in items], dtype=torch.long),
        "pai": [item["pai"] for item in items],
        "sample_id": [item["sample_id"] for item in items],
        "subject_id": [item["subject_id"] for item in items],
    }
