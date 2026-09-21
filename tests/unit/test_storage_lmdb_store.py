"""The LMDB backend against a real store, including the frames_dir key-range shape."""

from __future__ import annotations

import pickle
from pathlib import Path

import lmdb
import pytest

from pad_research.data.storage.base import StorageNotFoundError, StorageUnavailableError
from pad_research.data.storage.lmdb_store import LmdbStorage


def _write_store(path: Path, entries: dict[str, bytes], *, subdir: bool = True) -> Path:
    env = lmdb.open(str(path), subdir=subdir, map_size=1 << 22)
    with env.begin(write=True) as txn:
        for key, value in entries.items():
            txn.put(key.encode("utf-8"), value)
    env.close()
    return path


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return _write_store(
        tmp_path / "ds.lmdb",
        {
            "ds/clip_a.avi": b"video-bytes",
            # A frames_dir in LMDB is a key range, and its frames are deliberately NOT
            # zero-padded here so the ordering rule is actually exercised.
            "ds/clip_b/1": b"f1",
            "ds/clip_b/2": b"f2",
            "ds/clip_b/10": b"f10",
            "ds/clip_c.avi": b"other",
        },
    )


def test_reads_a_value_by_its_manifest_relative_path(store: Path) -> None:
    backend = LmdbStorage(store)
    assert backend.read_bytes("ds/clip_a.avi") == b"video-bytes"
    backend.close()


def test_there_is_no_local_path_so_readers_fall_back_to_bytes(store: Path) -> None:
    # media.py branches on this: None means "decode from a BytesIO", which is what makes an
    # LMDB-backed video decodable at all.
    assert LmdbStorage(store).local_path("ds/clip_a.avi") is None


def test_a_missing_key_is_not_found_rather_than_empty(store: Path) -> None:
    backend = LmdbStorage(store)
    with pytest.raises(StorageNotFoundError):
        backend.read_bytes("ds/absent.avi")
    backend.close()


def test_frames_are_listed_in_temporal_order(store: Path) -> None:
    backend = LmdbStorage(store)
    assert backend.is_dir("ds/clip_b")
    assert backend.list_children("ds/clip_b") == ["ds/clip_b/1", "ds/clip_b/2", "ds/clip_b/10"]
    backend.close()


def test_a_key_range_scan_stops_at_the_prefix(store: Path) -> None:
    # LMDB keys are byte-ordered, so "ds/clip_b/..." and "ds/clip_c.avi" are adjacent. A scan
    # that forgot to stop would fold the next sample's video into this clip's frames.
    backend = LmdbStorage(store)
    assert "ds/clip_c.avi" not in backend.list_children("ds/clip_b")
    backend.close()


def test_a_value_key_is_not_a_directory(store: Path) -> None:
    backend = LmdbStorage(store)
    assert backend.exists("ds/clip_a.avi")
    assert not backend.is_dir("ds/clip_a.avi")
    with pytest.raises(StorageNotFoundError):
        backend.list_children("ds/clip_a.avi")
    backend.close()


def test_key_prefix_bridges_a_store_built_with_an_affix(tmp_path: Path) -> None:
    # The common real mismatch: the manifest says "clip_a.avi", the store was built with a
    # dataset prefix. Without the affix the read fails; with it the same manifest works.
    store = _write_store(tmp_path / "p.lmdb", {"oulu_npu/clip_a.avi": b"x"})
    assert LmdbStorage(store).exists("clip_a.avi") is False
    backend = LmdbStorage(store, key_prefix="oulu_npu/")
    assert backend.read_bytes("clip_a.avi") == b"x"
    backend.close()


def test_key_suffix_is_stripped_when_listing_children(tmp_path: Path) -> None:
    store = _write_store(tmp_path / "s.lmdb", {"c/1.jpg": b"a", "c/2.jpg": b"b"})
    backend = LmdbStorage(store, key_suffix=".jpg")
    # Children come back as manifest-style paths, so read_bytes can be called on them
    # directly; leaving the suffix on would double it to "c/1.jpg.jpg".
    assert backend.list_children("c") == ["c/1", "c/2"]
    assert backend.read_bytes(backend.list_children("c")[0]) == b"a"
    backend.close()


def test_a_single_file_store_opens_without_configuration(tmp_path: Path) -> None:
    # An LMDB is either a directory (data.mdb + lock.mdb) or one .mdb file. Which one it is,
    # is a property of the store, not a choice the user should have to declare.
    store = _write_store(tmp_path / "single.mdb", {"a": b"1"}, subdir=False)
    assert store.is_file()
    backend = LmdbStorage(store)
    assert backend.read_bytes("a") == b"1"
    backend.close()


def test_a_missing_store_names_the_setting_rather_than_a_path(tmp_path: Path) -> None:
    backend = LmdbStorage(tmp_path / "absent.lmdb")
    with pytest.raises(StorageUnavailableError) as excinfo:
        backend.read_bytes("a")
    message = str(excinfo.value)
    assert "storage.path" in message
    assert str(tmp_path) not in message  # contract section 34: no paths in messages


def test_the_backend_survives_pickling(store: Path) -> None:
    # Spawned DataLoader workers unpickle the dataset, and the dataset holds the backend.
    backend = LmdbStorage(store)
    backend.read_bytes("ds/clip_a.avi")
    restored = pickle.loads(pickle.dumps(backend))
    assert restored.read_bytes("ds/clip_a.avi") == b"video-bytes"
    restored.close()
    backend.close()


def _read_in_child(backend: LmdbStorage, queue: object) -> None:
    try:
        queue.put(("ok", backend.read_bytes("ds/clip_a.avi")))  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - reported to the parent instead
        queue.put(("err", f"{type(exc).__name__}: {exc}"))  # type: ignore[attr-defined]


def test_forked_workers_read_while_the_parent_still_holds_the_store(store: Path) -> None:
    """A DataLoader with num_workers > 0 forks, and this is where LMDB goes wrong.

    py-lmdb allows one open per path per process and keeps a process-global registry to
    enforce it. That registry is inherited across fork(), so a worker that simply re-opens is
    told "The environment is already open in this process" — naming the parent's handle, which
    it must not use. Every multi-worker LMDB run fails on the first batch without the detach
    step, and the parent has to keep working afterwards.
    """
    import multiprocessing as mp

    context = mp.get_context("fork")
    backend = LmdbStorage(store)
    assert backend.read_bytes("ds/clip_a.avi") == b"video-bytes"  # parent opens first

    results = []
    for _ in range(3):
        queue: mp.Queue = context.Queue()  # type: ignore[type-arg]
        process = context.Process(target=_read_in_child, args=(backend, queue))
        process.start()
        results.append(queue.get(timeout=30))
        process.join(timeout=30)

    assert results == [("ok", b"video-bytes")] * 3
    assert backend.read_bytes("ds/clip_a.avi") == b"video-bytes"  # parent unharmed
    backend.close()


def test_a_write_locked_store_refuses_to_be_inherited_instead_of_corrupting(store: Path) -> None:
    # With lock=True there IS a shared reader table, so closing the inherited environment
    # could release a slot the parent holds. Better a message naming the two settings that
    # fix it than a parent whose reads quietly go wrong.
    import multiprocessing as mp

    context = mp.get_context("fork")
    backend = LmdbStorage(store, lock=True)
    backend.read_bytes("ds/clip_a.avi")

    queue: mp.Queue = context.Queue()  # type: ignore[type-arg]
    process = context.Process(target=_read_in_child, args=(backend, queue))
    process.start()
    status, detail = queue.get(timeout=30)
    process.join(timeout=30)

    assert status == "err"
    assert "lock: false" in detail and "num_workers" in detail
    backend.close()


def test_two_backends_for_one_store_share_an_environment(store: Path) -> None:
    # One ClipDataset per split is normal, and py-lmdb would refuse the second open. Sharing
    # is also what LMDB wants: the mapping is read-only and thread-safe.
    first, second = LmdbStorage(store), LmdbStorage(store)
    assert first.read_bytes("ds/clip_a.avi") == second.read_bytes("ds/clip_a.avi")
    first.close()


def test_describe_carries_no_location(store: Path) -> None:
    described = LmdbStorage(store).describe()
    assert described["storage_kind"] == "lmdb"
    assert not any(str(store) in v for v in described.values())
