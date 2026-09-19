"""Torch dataset for manifest records that point to clips.

Phase 0 reads only ``npy_clip`` media. Other media types keep the manifest path
contract intact but deliberately raise ``NotImplementedError("Phase 1")`` until
real-video decoding is designed and tested.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

import numpy as np
import torch
import torch.nn.functional as F  # noqa: N812
from torch import Tensor
from torch.utils.data import Dataset

from pad_research.conventions import LABEL_BONA_FIDE, LABEL_SPOOF
from pad_research.data.manifest import Label, ManifestRecord, MediaType, resolve_path
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


def _to_tchw(arr: np.ndarray) -> np.ndarray:
    if arr.ndim != 4:
        raise ValueError(f"npy_clip must have 4 dimensions, got shape {arr.shape}")
    if arr.shape[-1] == 3:
        arr = np.transpose(arr, (0, 3, 1, 2))
    elif arr.shape[1] == 3:
        arr = arr
    else:
        raise ValueError(f"npy_clip must be [T,H,W,3] or [T,3,H,W], got shape {arr.shape}")
    arr = arr.astype(np.float32, copy=False)
    if arr.size and float(np.nanmax(arr)) > 1.0:
        arr = arr / 255.0
    return np.clip(arr, 0.0, 1.0).astype(np.float32, copy=False)


def read_clip(record: ManifestRecord, root: Path | str) -> np.ndarray:
    """Read a manifest record into ``float32 [T,3,H,W]`` in ``[0, 1]``.

    Only ``MediaType.npy_clip`` is implemented in Phase 0.
    """
    if record.media_type != MediaType.npy_clip:
        raise NotImplementedError("Phase 1")
    path = resolve_path(record, Path(root))
    if not path.is_file():
        raise FileNotFoundError(
            f"clip file not found for dataset_id={record.dataset_id} sample_id={record.sample_id}"
        )
    return _to_tchw(np.load(path, allow_pickle=False))


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
        clip_np = read_clip(record, self.root)
        rng = random.Random(self.seed + index + (10_000_000 if self.train else 0))
        indices = sample_frame_indices(clip_np.shape[0], self.frames, self.sampling, rng)
        clip = torch.from_numpy(clip_np[indices]).to(dtype=torch.float32)
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
