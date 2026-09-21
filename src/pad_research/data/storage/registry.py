"""Build a :class:`~pad_research.data.storage.base.StorageBackend` from a config block.

This is the one place that reads the environment variables a storage config names. Keeping it
in a single function means the diagnosis CLI, the trainer and the tests all fail the same way
when a variable is missing, and the message can name the variable instead of dying later with
a ``FileNotFoundError`` on a path nobody can see.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pad_research.data.storage.base import StorageBackend, StorageUnavailableError
from pad_research.data.storage.config import (
    LmdbStorageConfig,
    LocalStorageConfig,
    SftpStorageConfig,
    StorageConfig,
)
from pad_research.data.storage.local import LocalStorage


class StorageEnvMissingError(StorageUnavailableError):
    """A required environment variable is unset; its name is in the message."""


def _require_env(name: str, purpose: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise StorageEnvMissingError(
            f"environment variable {name} is not set; it must hold {purpose}. "
            f"Export it in the shell that launches the run (see scripts/check_storage.py)."
        )
    return value


def _optional_env(name: str | None) -> str | None:
    if not name:
        return None
    value = os.environ.get(name, "").strip()
    return value or None


def build_storage(config: StorageConfig | Any, *, require_root: bool = False) -> StorageBackend:
    """Return the backend ``config`` describes, reading its environment variables now.

    ``require_root`` makes a local backend verify that its root exists. The trainer leaves it
    false (a missing root surfaces per sample, with the sample id); the diagnosis CLI sets it
    so the first thing the user sees is the real problem.
    """
    if isinstance(config, LocalStorageConfig):
        return LocalStorage(
            _require_env(config.root_env_var, "the directory holding the dataset media"),
            require_root=require_root,
        )

    if isinstance(config, LmdbStorageConfig):
        # Imported here so that a machine without the driver can still compose and validate a
        # spec that happens to mention LMDB; the failure belongs at read time, with a message.
        from pad_research.data.storage.lmdb_store import LmdbStorage

        return LmdbStorage(
            Path(_require_env(config.path_env_var, "the LMDB store (a directory or a .mdb file)")),
            key_prefix=config.key_prefix,
            key_suffix=config.key_suffix,
            key_encoding=config.key_encoding,
            lock=config.lock,
            readahead=config.readahead,
            max_readers=config.max_readers,
        )

    if isinstance(config, SftpStorageConfig):
        from pad_research.data.storage.sftp import SftpStorage

        return SftpStorage(
            host=_require_env(config.host_env_var, "the SSH host serving the dataset"),
            remote_root=_require_env(config.remote_root_env_var, "the remote dataset directory"),
            username=_optional_env(config.username_env_var),
            port=config.port,
            key_filename=_optional_env(config.key_filename_env_var),
            password_env_var=config.password_env_var,
            known_hosts=_optional_env(config.known_hosts_env_var),
            timeout=config.timeout,
        )

    raise StorageUnavailableError(f"unknown storage kind {getattr(config, 'kind', config)!r}")


def as_storage(source: StorageBackend | Path | str) -> StorageBackend:
    """Accept either a backend or a plain root path.

    Every reader in the harness takes one of these. Call sites that predate the storage layer
    (tests, the synthetic adapter, ``read_clip``) pass a directory and keep working; the
    trainer passes a configured backend.
    """
    if isinstance(source, Path | str):
        return LocalStorage(source)
    return source


__all__ = ["StorageEnvMissingError", "as_storage", "build_storage"]
