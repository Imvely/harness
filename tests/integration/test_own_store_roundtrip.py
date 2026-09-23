"""A store we build is a store the harness can read: build a tiny one and read it back.

This is the join between the two halves of ADR-016. The builder decides the keys; the LMDB
backend resolves a manifest ``relative_path`` into them. If the two ever disagree about the
separator or the index width, every clip silently becomes unreadable — a mismatch no unit test
on either side can see, so it is checked here on a real store.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pad_research.data.build_store import (
    build_records,
    estimate_bytes,
    plan_build,
    write_store,
)
from pad_research.data.manifest import Label, MediaType
from pad_research.data.sources.aihub_tree import scan_aihub_tree
from pad_research.data.storage.lmdb_store import LmdbStorage
from pad_research.data.storage.lmdb_writer import LmdbSink, LmdbWriteError, map_size_for

pytestmark = pytest.mark.integration

LAYOUT = {
    ("training", "0001", "SR305", "Light_01_High", "real_01"): 12,
    ("training", "0001", "SR305", "Light_01_High", "attack_01_print_eye_flat"): 3,
    ("validation", "0002", "SR305", "Light_03_Low", "real_01"): 2,
    ("validation", "0002", "SR305", "Light_03_Low", "attack_02_print_eye_curved"): 2,
}


def build_tree(root: Path) -> Path:
    for (purpose, subject, device, lighting, class_name), n_frames in LAYOUT.items():
        image_dir = root / purpose / subject / device / lighting / class_name / "color" / "image"
        image_dir.mkdir(parents=True)
        for index in range(1, n_frames + 1):
            (image_dir / f"{index}.jpg").write_bytes(f"{class_name}/{index}".encode())
    return root


@pytest.fixture
def source(tmp_path: Path) -> Path:
    pytest.importorskip("lmdb")
    return build_tree(tmp_path / "source")


def test_a_clip_reads_back_frame_by_frame_in_capture_order(source: Path, tmp_path: Path) -> None:
    plan = plan_build(scan_aihub_tree(source), "aihub115")
    store_path = tmp_path / "ours" / "aihub115.lmdb"
    with LmdbSink(store_path, map_size=map_size_for(estimate_bytes(plan, source))) as sink:
        records = write_store(plan, source, sink)
        n_written = sink.n_written
    assert n_written == plan.n_frames == 19

    storage = LmdbStorage(store_path, child_separator="/")
    try:
        long_clip = next(r for r in records if r.n_frames == 12)
        assert storage.is_dir(long_clip.relative_path)
        children = storage.list_children(long_clip.relative_path)
        assert len(children) == 12
        # Zero-padded, so the tenth frame does not sort before the second.
        assert [c.rsplit("/", 1)[-1] for c in children[:3]] == ["00000", "00001", "00002"]
        assert storage.read_bytes(children[0]) == b"real_01/1"
        assert storage.read_bytes(children[11]) == b"real_01/12"
        assert long_clip.media_type is MediaType.frames_dir
        assert long_clip.label is Label.bona_fide
    finally:
        storage.close()


def test_every_record_the_build_returns_resolves_in_the_store(source: Path, tmp_path: Path) -> None:
    plan = plan_build(scan_aihub_tree(source), "aihub115")
    store_path = tmp_path / "ours" / "aihub115.lmdb"
    with LmdbSink(store_path, map_size=map_size_for(estimate_bytes(plan, source))) as sink:
        records = write_store(plan, source, sink)

    storage = LmdbStorage(store_path, child_separator="/")
    try:
        for record in records:
            children = storage.list_children(record.relative_path)
            assert len(children) == record.n_frames
            assert all(storage.read_bytes(child) for child in children)
    finally:
        storage.close()


def test_a_second_build_into_the_same_store_is_refused(source: Path, tmp_path: Path) -> None:
    plan = plan_build(scan_aihub_tree(source), "aihub115")
    store_path = tmp_path / "ours" / "aihub115.lmdb"
    with LmdbSink(store_path, map_size=map_size_for(estimate_bytes(plan, source))) as sink:
        write_store(plan, source, sink)
    with pytest.raises(LmdbWriteError, match="already exists"):
        LmdbSink(store_path, map_size=map_size_for(1))


def test_the_same_key_twice_fails_the_write_instead_of_overwriting(
    source: Path, tmp_path: Path
) -> None:
    """The lab's build overwrote here and lost 79,091 frames. Ours stops."""
    store_path = tmp_path / "ours" / "dup.lmdb"
    sink = LmdbSink(store_path, map_size=map_size_for(1))
    try:
        sink.put("clip/00000", b"first")
        with pytest.raises(LmdbWriteError, match="already in the store"):
            sink.put("clip/00000", b"second")
    finally:
        sink.close()


def test_the_manifest_records_do_not_depend_on_the_store_being_written(source: Path) -> None:
    """Records come from the plan, so a manifest can be reviewed before any disk is spent."""
    plan = plan_build(scan_aihub_tree(source), "aihub115")
    assert [r.sample_id for r in build_records(plan)] == [p.sample_id for p in plan.kept]
