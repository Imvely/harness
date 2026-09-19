"""Unit tests for frame sampling, clip loading and protocol split construction."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest

from pad_research.config.compose import compose_spec
from pad_research.data.clip_dataset import ClipDataset, collate, read_clip
from pad_research.data.manifest import PAI, Label, ManifestRecord, MediaType, Split, load_manifest
from pad_research.data.sampling import sample_frame_indices
from pad_research.data.splits import build_splits
from pad_research.protocols.adaptation_set import select_adaptation_set

ROOT = Path(__file__).resolve().parents[2]


def _record(path: str, *, media_type: MediaType = MediaType.npy_clip) -> ManifestRecord:
    return ManifestRecord(
        dataset_id="synthetic_a",
        sample_id="sample_001",
        subject_id="subject_001",
        split=Split.train,
        label=Label.bona_fide,
        pai=PAI.none,
        relative_path=path,
        media_type=media_type,
        n_frames=4,
        width=2,
        height=2,
    )


def test_sample_frame_indices_center_and_repeat_padding() -> None:
    rng = random.Random(1)
    assert sample_frame_indices(5, 1, "uniform", rng) == [2]
    assert sample_frame_indices(3, 5, "consecutive", rng) == [0, 1, 2, 2, 2]


def test_sample_frame_indices_random_crop_uses_rng() -> None:
    first = sample_frame_indices(10, 4, "random_crop", random.Random(7))
    second = sample_frame_indices(10, 4, "random_crop", random.Random(7))
    assert first == second
    assert len(first) == 4


def test_read_clip_and_dataset_contract(tmp_path: Path) -> None:
    clip = np.arange(4 * 2 * 2 * 3, dtype=np.uint8).reshape(4, 2, 2, 3)
    path = tmp_path / "synthetic_a" / "sample_001.npy"
    path.parent.mkdir()
    np.save(path, clip)
    record = _record("synthetic_a/sample_001.npy")

    loaded = read_clip(record, tmp_path)
    assert loaded.shape == (4, 3, 2, 2)
    assert loaded.dtype == np.float32
    assert float(loaded.min()) >= 0.0
    assert float(loaded.max()) <= 1.0

    dataset = ClipDataset([record], tmp_path, 2, "uniform", (2, 2), train=False, seed=0)
    item = dataset[0]
    assert item["clip"].shape == (2, 3, 2, 2)
    assert item["label"] == 0
    batch = collate([item])
    assert batch["clip"].shape == (1, 2, 3, 2, 2)
    assert batch["label"].tolist() == [0]


def test_read_clip_rejects_phase1_media(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="Phase 1"):
        read_clip(_record("synthetic_a/sample_001.png", media_type=MediaType.image), tmp_path)


def test_build_splits_uses_protocol_adaptation_set() -> None:
    _, spec = compose_spec(["+exp=syn_e02_video_source_only"])
    manifests = {
        "synthetic_a": load_manifest("synthetic_a", ROOT / "data" / "manifests"),
        "synthetic_b": load_manifest("synthetic_b", ROOT / "data" / "manifests"),
    }
    selection = select_adaptation_set(spec.protocol, manifests["synthetic_b"])
    splits = build_splits(spec.protocol, manifests, selection)
    assert len(splits.source_train) > 0
    assert len(splits.source_dev) > 0
    assert len(splits.target_dev) > 0
    assert len(splits.target_test) > 0
    assert len(splits.adaptation) == spec.protocol.target_adaptation.total_samples
    assert {r.sample_id for r in splits.adaptation}.isdisjoint(
        {r.sample_id for r in splits.target_test}
    )
