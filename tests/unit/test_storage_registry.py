"""Building a backend from a config block, and the message when a variable is unset."""

from __future__ import annotations

from pathlib import Path

import pytest

from pad_research.data.storage.config import (
    LmdbStorageConfig,
    LocalStorageConfig,
    SftpStorageConfig,
)
from pad_research.data.storage.lmdb_store import LmdbStorage
from pad_research.data.storage.local import LocalStorage
from pad_research.data.storage.registry import (
    StorageEnvMissingError,
    as_storage,
    build_storage,
)


def test_a_local_backend_reads_its_root_from_the_named_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAD_DATA_ROOT", str(tmp_path))
    backend = build_storage(LocalStorageConfig())
    assert isinstance(backend, LocalStorage)
    assert backend.root == tmp_path


def test_an_unset_variable_is_named_in_the_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # The failure this prevents: a job that passes validation, queues on the GPU, and dies on
    # the first batch because one variable was spelled differently in that shell.
    monkeypatch.delenv("PAD_LMDB_PATH", raising=False)
    with pytest.raises(StorageEnvMissingError) as excinfo:
        build_storage(LmdbStorageConfig(kind="lmdb"))
    assert "PAD_LMDB_PATH" in str(excinfo.value)


def test_lmdb_key_affixes_reach_the_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAD_LMDB_PATH", str(tmp_path / "s.lmdb"))
    backend = build_storage(LmdbStorageConfig(kind="lmdb", key_prefix="oulu_npu/", lock=True))
    assert isinstance(backend, LmdbStorage)
    assert backend.key_prefix == "oulu_npu/"
    assert backend.lock is True


def test_sftp_reads_host_and_root_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("paramiko", reason="the sftp extra is optional")
    monkeypatch.setenv("PAD_SFTP_HOST", "gpu-node")
    monkeypatch.setenv("PAD_SFTP_ROOT", "/srv/datasets")
    monkeypatch.setenv("PAD_SFTP_USER", "researcher")
    backend = build_storage(SftpStorageConfig(kind="sftp"))
    assert backend.kind == "sftp"
    # Nothing is connected yet: the socket must not be opened before a fork.
    assert backend.describe() == {"storage_kind": "sftp"}


def test_a_plain_directory_still_works_as_a_source(tmp_path: Path) -> None:
    # Call sites that predate the storage layer (tests, read_clip, the synthetic adapter) pass
    # a root, and must keep working without a config block.
    assert isinstance(as_storage(tmp_path), LocalStorage)
    assert isinstance(as_storage(str(tmp_path)), LocalStorage)


def test_an_existing_backend_passes_through_unchanged(tmp_path: Path) -> None:
    backend = LocalStorage(tmp_path)
    assert as_storage(backend) is backend
