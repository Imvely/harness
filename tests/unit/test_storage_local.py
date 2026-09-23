"""The filesystem backend, which also stands in for every mount (NFS, SMB, sshfs)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pad_research.data.storage.base import (
    StorageError,
    StorageNotFoundError,
    StorageUnavailableError,
)
from pad_research.data.storage.local import LocalStorage


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "ds" / "clip").mkdir(parents=True)
    (tmp_path / "ds" / "a.avi").write_bytes(b"video")
    for name in ("frame_1.png", "frame_2.png", "frame_10.png", "notes.txt"):
        (tmp_path / "ds" / "clip" / name).write_bytes(b"x")
    return tmp_path


def test_a_real_file_is_offered_as_a_path_not_as_bytes(root: Path) -> None:
    # This is the whole reason local_path exists: a decoder given a path streams the file,
    # while one given bytes holds the entire video in every worker's memory.
    backend = LocalStorage(root)
    assert backend.local_path("ds/a.avi") == root / "ds" / "a.avi"
    assert backend.read_bytes("ds/a.avi") == b"video"


def test_children_come_back_in_temporal_order_with_their_full_relative_path(root: Path) -> None:
    assert LocalStorage(root).list_children("ds/clip") == [
        "ds/clip/frame_1.png",
        "ds/clip/frame_2.png",
        "ds/clip/frame_10.png",
        "ds/clip/notes.txt",
    ]


def test_directories_and_files_are_distinguished(root: Path) -> None:
    backend = LocalStorage(root)
    assert backend.is_dir("ds/clip")
    assert not backend.is_dir("ds/a.avi")
    assert backend.exists("ds/a.avi")
    assert not backend.exists("ds/missing.avi")


def test_a_missing_object_is_not_found(root: Path) -> None:
    with pytest.raises(StorageNotFoundError):
        LocalStorage(root).read_bytes("ds/missing.avi")
    with pytest.raises(StorageNotFoundError):
        LocalStorage(root).list_children("ds/missing")


def test_a_path_that_would_escape_the_root_is_refused(root: Path) -> None:
    # The dataset root is the security boundary for face data; ManifestRecord validates this
    # too, but a backend is also reachable from the CLI and from adapters under development.
    with pytest.raises(StorageError):
        LocalStorage(root).read_bytes("../../etc/passwd")


def test_a_missing_root_is_reported_without_naming_it(tmp_path: Path) -> None:
    with pytest.raises(StorageUnavailableError) as excinfo:
        LocalStorage(tmp_path / "absent", require_root=True)
    message = str(excinfo.value)
    assert "PAD_DATA_ROOT" in message
    assert str(tmp_path) not in message  # contract section 34: no paths in messages


def test_describe_carries_no_location(root: Path) -> None:
    described = LocalStorage(root).describe()
    assert described == {"storage_kind": "local"}
