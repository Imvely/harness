"""Tests for the synthetic dataset adapter (determinism, splits, PAI coverage, clips)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from pad_research.data.adapters.base import ADAPTERS, get_adapter
from pad_research.data.adapters.synthetic import (
    SYN_DOMAINS,
    SyntheticAdapter,
    generate_clip,
)
from pad_research.data.manifest import (
    PAI,
    Label,
    ManifestRecord,
    MediaType,
    manifest_hash,
    resolve_path,
    validate_records,
    write_manifest,
)

SMALL = {"n_subjects": 5, "num_frames": 4, "size": (8, 8)}


def _build(root: Path, dataset_id: str = "synthetic_a") -> list[ManifestRecord]:
    return SyntheticAdapter(dataset_id, **SMALL).build(root)


def test_registry_exposes_synthetic() -> None:
    assert "synthetic" in ADAPTERS
    adapter = get_adapter("synthetic", dataset_id="synthetic_b", **SMALL)
    assert isinstance(adapter, SyntheticAdapter)
    assert adapter.subject_offset == 1000
    assert adapter.meta_partial()["pii_policy"] == "synthetic"
    assert adapter.meta_partial()["adapter"] == "synthetic"
    with pytest.raises(KeyError):
        get_adapter("does_not_exist")


def test_two_builds_are_byte_identical(tmp_path: Path) -> None:
    root1, root2 = tmp_path / "r1", tmp_path / "r2"
    records1, records2 = _build(root1), _build(root2)
    assert records1 == records2
    assert manifest_hash(records1) == manifest_hash(records2)
    for record in records1:
        p1, p2 = resolve_path(record, root1), resolve_path(record, root2)
        assert p1.read_bytes() == p2.read_bytes()
    meta1 = write_manifest(records1, SyntheticAdapter("synthetic_a", **SMALL).meta_partial(), root1)
    assert meta1.manifest_hash == manifest_hash(records2)


def test_rebuild_in_place_keeps_files(tmp_path: Path) -> None:
    records = _build(tmp_path)
    before = {r.sample_id: resolve_path(r, tmp_path).read_bytes() for r in records}
    _build(tmp_path)
    after = {r.sample_id: resolve_path(r, tmp_path).read_bytes() for r in records}
    assert before == after


def test_records_are_valid_and_subject_disjoint(tmp_path: Path) -> None:
    records = _build(tmp_path)
    assert validate_records(records) == []
    subjects = {
        split: {r.subject_id for r in records if r.split == split}
        for split in ("train", "dev", "test")
    }
    assert subjects["train"] & subjects["dev"] == set()
    assert subjects["train"] & subjects["test"] == set()
    assert subjects["dev"] & subjects["test"] == set()
    assert {len(s) for s in subjects.values()} == {3, 1}  # 3 / 1 / 1 subjects
    assert len(records) == 5 * 8


def test_default_split_sizes_and_pai_counts_per_split(tmp_path: Path) -> None:
    adapter = SyntheticAdapter("synthetic_a", num_frames=2, size=(4, 4))
    records = adapter.build(tmp_path)
    assert len(records) == 160
    n_subj = Counter()
    for r in records:
        n_subj[r.split.value] += 1
    assert n_subj == {"train": 96, "dev": 32, "test": 32}
    for split in ("train", "dev", "test"):
        counts = Counter(r.pai.value for r in records if r.split.value == split)
        n_subjects = len({r.subject_id for r in records if r.split.value == split})
        assert counts == {
            "none": 4 * n_subjects,
            "print": 2 * n_subjects,
            "replay_phone": n_subjects,
            "replay_tablet": n_subjects,
        }


def test_record_fields(tmp_path: Path) -> None:
    records = _build(tmp_path)
    first = records[0]
    assert first.sample_id == "synthetic_a_s000_c00_none"
    assert first.subject_id == "subj0000"
    assert first.relative_path == "synthetic_a/synthetic_a_s000_c00_none.npy"
    assert first.media_type is MediaType.npy_clip
    assert first.capture_device == "synthetic_cam_a"
    assert first.environment == "synthetic"
    assert (first.n_frames, first.height, first.width, first.fps) == (4, 8, 8, 30.0)
    spoof = [r for r in records if r.label is Label.spoof]
    assert all(r.pai is not PAI.none for r in spoof)
    assert all(r.sample_id.endswith(f"_{r.pai.value}") for r in records)
    assert {r.pai.value for r in spoof} == {"print", "replay_phone", "replay_tablet"}


def test_subject_ids_disjoint_across_domains(tmp_path: Path) -> None:
    a = {r.subject_id for r in _build(tmp_path / "a", "synthetic_a")}
    b = {r.subject_id for r in _build(tmp_path / "b", "synthetic_b")}
    assert a.isdisjoint(b)
    assert {r.capture_device for r in _build(tmp_path / "b", "synthetic_b")} == {"synthetic_cam_b"}


def test_clip_shape_dtype_and_determinism(tmp_path: Path) -> None:
    records = _build(tmp_path)
    for record in records[:8]:
        clip = np.load(resolve_path(record, tmp_path))
        assert clip.dtype == np.uint8
        assert clip.shape == (4, 8, 8, 3)
        regenerated = generate_clip(
            record.sample_id, record.pai, SYN_DOMAINS["synthetic_a"], 4, 8, 8
        )
        assert np.array_equal(clip, regenerated)


def test_clips_differ_by_pai_and_domain() -> None:
    dom_a, dom_b = SYN_DOMAINS["synthetic_a"], SYN_DOMAINS["synthetic_b"]
    bona = generate_clip("x", PAI.none, dom_a, 8, 16, 16)
    prnt = generate_clip("x", PAI.print, dom_a, 8, 16, 16)
    phone = generate_clip("x", PAI.replay_phone, dom_a, 8, 16, 16)
    tablet = generate_clip("x", PAI.replay_tablet, dom_a, 8, 16, 16)
    other_domain = generate_clip("x", PAI.none, dom_b, 8, 16, 16)
    assert not np.array_equal(bona, prnt)
    assert not np.array_equal(phone, tablet)
    assert not np.array_equal(bona, other_domain)
    # domain b is darker overall (brightness -0.15 after gain 1.3 on ~0.5 signals)
    assert other_domain.mean() != bona.mean()
    assert np.array_equal(bona, generate_clip("x", "none", dom_a, 8, 16, 16))


def test_unknown_dataset_id_needs_explicit_domain() -> None:
    with pytest.raises(ValueError):
        SyntheticAdapter("synthetic_c")
    adapter = SyntheticAdapter("synthetic_c", domain=SYN_DOMAINS["synthetic_a"], subject_offset=5)
    assert adapter.subject_offset == 5
