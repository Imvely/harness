"""Where the media bytes physically live, kept apart from what the manifest says they are.

A manifest record names a sample by ``dataset_id``/``sample_id`` and locates it with a
``relative_path`` (research contract section 34). That string is deliberately machine
independent so ``manifest_hash`` is the same everywhere. It says nothing about *how* the
bytes are reached: one lab member has an extracted directory tree, another has the same
dataset packed into an LMDB, a third reads it over SSH. A backend turns a
``relative_path`` into bytes; nothing else in the harness knows which one is in use.

Two rules keep that boundary honest.

*Locality is not science.* A backend never changes what is read, only where it is read
from, so :data:`pad_research.config.schema.SCIENCE_EXCLUDE` drops the storage block from
``science_hash``. Two machines reading the same dataset over different backends produce the
same ``science_hash`` and stay directly comparable (contract section 14.3). If storage
entered the hash, moving a dataset into LMDB would silently make every earlier run
incomparable.

*Handles do not survive a fork.* A DataLoader worker is a forked (or spawned) process. An
LMDB environment or an SSH channel opened in the parent and used in a child is undefined
behaviour, so backends open nothing in ``__init__``; they open lazily and re-open when the
pid changes (:class:`PerProcessResource`).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Generic, Protocol, TypeVar, runtime_checkable

_DIGITS = re.compile(r"(\d+)")


class StorageError(RuntimeError):
    """A backend could not serve a relative path."""


class StorageNotFoundError(StorageError, FileNotFoundError):
    """The relative path does not exist in this backend."""


class StorageUnavailableError(StorageError):
    """The backend itself cannot be reached (missing driver, dead connection, bad root)."""


def natural_key(name: str) -> tuple[object, ...]:
    """Sort ``frame_2`` before ``frame_10``.

    Lexicographic order puts ``frame_10`` first, which silently reorders a clip whenever a
    dataset does not zero-pad its frame numbers. Comparing digit runs as integers keeps the
    temporal order the dataset intended. Shared by every backend so a ``frames_dir`` yields
    the same order whether it is a directory, an LMDB key range or a remote listing.
    """
    return tuple(int(part) if part.isdigit() else part.lower() for part in _DIGITS.split(name))


def sort_children(paths: list[str]) -> list[str]:
    """Order child relative paths by their last segment, naturally."""
    return sorted(paths, key=lambda p: natural_key(p.rsplit("/", 1)[-1]))


@runtime_checkable
class StorageBackend(Protocol):
    """Read-only byte access to one dataset root.

    Implementations must be safe to construct in a parent process and use in a forked or
    spawned DataLoader worker (see the module docstring). They never write, never delete and
    never log a path (contract section 34).
    """

    kind: str

    def local_path(self, relative_path: str) -> Path | None:
        """Return a real filesystem path when one exists, else ``None``.

        A decoder that is handed a path can stream a 200 MB video off disk; one handed bytes
        must hold the whole file in the worker's memory. Backends that genuinely have a local
        file (a directory tree, an NFS or sshfs mount) return it; LMDB and SFTP return
        ``None`` and are read through :meth:`read_bytes`.
        """
        ...

    def read_bytes(self, relative_path: str) -> bytes:
        """Return the whole object at ``relative_path``."""
        ...

    def exists(self, relative_path: str) -> bool: ...

    def is_dir(self, relative_path: str) -> bool:
        """True when ``relative_path`` holds children rather than bytes (a ``frames_dir``)."""
        ...

    def list_children(self, relative_path: str) -> list[str]:
        """Return the child relative paths of a directory-like entry, naturally sorted."""
        ...

    def describe(self) -> dict[str, str]:
        """Return redaction-safe provenance for MLflow tags: no host, path or credential."""
        ...

    def close(self) -> None:
        """Release any handle held by the calling process. Safe to call more than once."""
        ...


_T = TypeVar("_T")


class PerProcessResource(Generic[_T]):
    """Hold a handle that must never cross a ``fork()``.

    py-lmdb's own documentation is explicit that "LMDB environments must not be used across
    a ``fork()`` call", and an SSH transport is in the same position: the child inherits a
    socket and a cipher state that two processes then corrupt between them. Torch's
    DataLoader forks on Linux by default and spawns on Windows and macOS, so a backend has to
    survive both.

    This holds the owning pid next to the handle. A child that inherited the attribute sees a
    pid mismatch and opens its own; it deliberately does **not** close the inherited one,
    because that handle belongs to the parent and closing it there would break the parent's
    connection. The inherited object is simply dropped, and the OS reclaims the child's copy
    when the worker exits.

    That is the right policy for a connection, which is why SFTP uses this class.
    :mod:`pad_research.data.storage.lmdb_store` needs a different one and does its own
    bookkeeping: py-lmdb keeps a *process-global* registry of open environments and refuses a
    second open of the same path, and that registry is inherited across ``fork()`` too.

    ``__getstate__`` drops the handle as well, so a spawned worker unpickles a closed
    resource rather than an unpicklable one.
    """

    def __init__(self) -> None:
        self._pid: int | None = None
        self._handle: _T | None = None

    def get(self, factory: Callable[[], _T]) -> _T:
        pid = os.getpid()
        if self._handle is None or self._pid != pid:
            self._handle = factory()
            self._pid = pid
        return self._handle

    def close(self, closer: Callable[[_T], None]) -> None:
        handle, pid = self._handle, self._pid
        self._handle, self._pid = None, None
        # Only the process that opened it may close it; see the class docstring.
        if handle is not None and pid == os.getpid():
            closer(handle)

    def __getstate__(self) -> dict[str, None]:
        return {"_pid": None, "_handle": None}

    def __setstate__(self, state: dict[str, None]) -> None:
        self._pid = None
        self._handle = None


def check_relative(relative_path: str) -> str:
    """Reject anything that could escape the dataset root.

    ``ManifestRecord`` already validates this when a manifest is built, but a backend is also
    reachable from the diagnosis CLI and from the adapter that is still being written, so the
    check is repeated where the bytes are actually fetched.
    """
    value = relative_path.strip()
    if not value:
        raise StorageError("relative_path must not be empty")
    if value.startswith("/") or "\\" in value or ".." in value.split("/"):
        raise StorageError(f"relative_path {value!r} must be relative, '/'-separated and '..'-free")
    return value


__all__ = [
    "PerProcessResource",
    "StorageBackend",
    "StorageError",
    "StorageNotFoundError",
    "StorageUnavailableError",
    "check_relative",
    "natural_key",
    "sort_children",
]
