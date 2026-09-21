"""LMDB backend: one memory-mapped key/value file instead of millions of small files.

Face PAD datasets are pathological for a filesystem. A few thousand clips become a few
million extracted frames, and a training epoch then issues a few million ``open``/``stat``
pairs; on a network filesystem the metadata round-trips dominate and the GPU starves. Packing
the same bytes into an LMDB turns that into one memory-mapped file with a B+tree index, so a
read is a page fault rather than a syscall storm.

The manifest still owns the naming. A record's ``relative_path`` *is* the LMDB key (after the
optional ``key_prefix``/``key_suffix``), so every layout an LMDB might use is already
expressible through ``media_type`` and needs no extra configuration:

==================================  ==========================  ===============================
LMDB holds                          ``media_type``              ``relative_path`` is
==================================  ==========================  ===============================
one encoded video per sample        ``video``                   the key
one JPEG/PNG per frame              ``frames_dir``              the key *prefix* of the frames
one still per sample                ``image``                   the key
a serialized ``.npy`` clip          ``npy_clip``                the key
==================================  ==========================  ===============================

Opening is deferred until the first read and redone whenever the pid changes, because
py-lmdb's documentation states plainly that "LMDB environments must not be used across a
``fork()`` call" and a DataLoader worker is exactly that.

Getting that right takes more than reopening, because py-lmdb also keeps a **process-global
registry** of open environments and refuses a second open of the same path with *"The
environment is already open in this process"*. Two things follow, and :data:`_ENVIRONMENTS`
handles both:

* The registry is inherited across ``fork()``. A worker that just reopens is refused, because
  as far as py-lmdb can tell the environment is already open — in the parent. The worker has
  to close the inherited object first, which clears the entry. With ``lock=False`` that is
  sound: there is no reader lock table, so the close frees only the child's own mapping and
  descriptors and the parent keeps reading. With ``lock=True`` a reader slot in ``lock.mdb``
  *is* shared and the close could release one the parent still holds, so that combination is
  refused with an explanation rather than silently corrupting the parent's view.
* Within one process, two :class:`LmdbStorage` objects for the same store (one per split, say)
  would be a second open. Caching by path makes them share one environment, which is what LMDB
  wants anyway — the mapping is read-only and thread-safe.

Read flags, and why each one:

``readonly=True``
    The harness never writes a dataset.
``lock=False``
    Skips the reader lock table entirely. It removes the two failure modes that bite a
    multi-worker job — a read-only mount where ``lock.mdb`` cannot be created, and reader-slot
    exhaustion when many workers attach — at the cost of being correct only while no process
    is *writing* the database. Building a dataset LMDB is a one-off, so that holds here;
    ``lock: true`` is available in the config for a store someone is still filling.
``readahead=False``
    Random access over a store larger than RAM. Readahead would page in neighbours that the
    sampler is not going to ask for and evict pages it is.
``meminit=False``
    Saves zeroing pages the reader immediately overwrites.
``max_spare_txns=0``
    Recommended by py-lmdb when the process may fork: a cached read-only transaction holds a
    reader slot that a forked child inherits and cannot clean up.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from pad_research.data.storage.base import (
    StorageNotFoundError,
    StorageUnavailableError,
    check_relative,
    sort_children,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import lmdb


class _OpenEnv(NamedTuple):
    pid: int
    flags: tuple[bool, bool, int]
    env: Any


#: Open environments in THIS process, keyed by resolved store path. See the module docstring:
#: py-lmdb allows one open per path per process, and the registry that enforces it survives a
#: fork. Never read directly — go through :func:`_environment_for`.
_ENVIRONMENTS: dict[str, _OpenEnv] = {}


def _environment_for(
    key: str,
    flags: tuple[bool, bool, int],
    opener: Callable[[], Any],
    *,
    lock: bool,
) -> Any:
    """Return this process's environment for ``key``, opening or re-opening as needed."""
    pid = os.getpid()
    current = _ENVIRONMENTS.get(key)
    if current is not None:
        if current.pid == pid:
            if current.flags != flags:
                raise StorageUnavailableError(
                    "this LMDB store is already open in this process with different read "
                    "options; use one storage config per store (lock/readahead/max_readers)"
                )
            return current.env
        # Inherited from a parent across fork(). Clearing py-lmdb's registry entry is the only
        # way this process may open its own, and it is only safe without the reader lock table.
        if lock:
            raise StorageUnavailableError(
                "an LMDB store opened with lock: true cannot be inherited by a DataLoader "
                "worker. Set storage.lock: false (correct for a store nobody is writing) or "
                "training.num_workers: 0"
            )
        current.env.close()
        del _ENVIRONMENTS[key]
    env = opener()
    _ENVIRONMENTS[key] = _OpenEnv(pid=pid, flags=flags, env=env)
    return env


class LmdbStorage:
    """Serve manifest relative paths out of an LMDB environment."""

    kind = "lmdb"

    def __init__(
        self,
        path: Path | str,
        *,
        key_prefix: str = "",
        key_suffix: str = "",
        key_encoding: str = "utf-8",
        lock: bool = False,
        readahead: bool = False,
        max_readers: int = 2048,
    ) -> None:
        self.path = Path(path).expanduser()
        self.key_prefix = key_prefix
        self.key_suffix = key_suffix
        self.key_encoding = key_encoding
        self.lock = bool(lock)
        self.readahead = bool(readahead)
        self.max_readers = int(max_readers)
        # No handle is held on the instance: the environment lives in the module-level cache,
        # keyed by path. That is what lets two LmdbStorage objects for one store coexist, and
        # it makes the object picklable for spawned workers without any special casing.

    # -- environment ------------------------------------------------------------------

    def _open(self) -> lmdb.Environment:
        try:
            import lmdb
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise StorageUnavailableError(
                "the lmdb driver is not installed; run `uv sync` (lmdb is a project dependency)"
            ) from exc
        if not self.path.exists():
            raise StorageUnavailableError(
                "the LMDB store does not exist at the configured path "
                "(check storage.path and that the volume holding it is mounted)"
            )
        # A store is either a directory holding data.mdb/lock.mdb or a single .mdb file;
        # py-lmdb needs to be told which, and the filesystem already knows.
        subdir = self.path.is_dir()
        try:
            return lmdb.open(
                str(self.path),
                subdir=subdir,
                readonly=True,
                lock=self.lock,
                readahead=self.readahead,
                meminit=False,
                max_readers=self.max_readers,
                max_spare_txns=0,
            )
        except Exception as exc:  # lmdb.Error and OSError families
            raise StorageUnavailableError(
                f"cannot open the LMDB store: {type(exc).__name__}"
            ) from exc

    def _cache_key(self) -> str:
        # The absolute path, so two configs reaching one store through different relative
        # spellings still share an environment instead of colliding in py-lmdb's registry.
        try:
            return str(self.path.resolve())
        except OSError:  # pragma: no cover - unresolvable path fails later, with a message
            return str(self.path)

    def _environment(self) -> lmdb.Environment:
        return _environment_for(
            self._cache_key(),
            (self.lock, self.readahead, self.max_readers),
            self._open,
            lock=self.lock,
        )

    def close(self) -> None:
        """Close this process's environment for this store, if it opened one.

        The environment is shared by every :class:`LmdbStorage` pointing at the same store, so
        this closes it for all of them. That is why the trainer does not call it per split:
        it is for the diagnosis CLI and for tests, which finish with the store.
        """
        current = _ENVIRONMENTS.get(self._cache_key())
        if current is not None and current.pid == os.getpid():
            del _ENVIRONMENTS[self._cache_key()]
            current.env.close()

    # -- keys -------------------------------------------------------------------------

    def key_for(self, relative_path: str) -> bytes:
        """Return the LMDB key a manifest ``relative_path`` maps to."""
        value = f"{self.key_prefix}{check_relative(relative_path)}{self.key_suffix}"
        return value.encode(self.key_encoding)

    def _child_relative(self, key: bytes, prefix_len: int, base: str) -> str | None:
        """Turn a raw key back into a manifest-style relative path, or ``None`` if it is not one."""
        text = key.decode(self.key_encoding, errors="replace")
        if self.key_suffix and text.endswith(self.key_suffix):
            text = text[: -len(self.key_suffix)]
        tail = text[prefix_len:]
        return f"{base}/{tail}" if tail else None

    # -- reads ------------------------------------------------------------------------

    def local_path(self, relative_path: str) -> Path | None:
        """Always ``None``: the bytes live inside the store, not as a file of their own."""
        return None

    def read_bytes(self, relative_path: str) -> bytes:
        key = self.key_for(relative_path)
        with self._environment().begin(write=False, buffers=False) as txn:
            value = txn.get(key)
        if value is None:
            raise StorageNotFoundError(f"no LMDB key for {relative_path!r}")
        return bytes(value)

    def exists(self, relative_path: str) -> bool:
        with self._environment().begin(write=False, buffers=False) as txn:
            if txn.get(self.key_for(relative_path)) is not None:
                return True
        return self.is_dir(relative_path)

    def is_dir(self, relative_path: str) -> bool:
        """True when keys exist *below* ``relative_path`` — the LMDB shape of a frames_dir."""
        return bool(self._scan(relative_path, limit=1))

    def list_children(self, relative_path: str) -> list[str]:
        children = self._scan(relative_path, limit=None)
        if not children:
            raise StorageNotFoundError(f"no LMDB keys under {relative_path!r}")
        return sort_children(children)

    def _scan(self, relative_path: str, *, limit: int | None) -> list[str]:
        base = check_relative(relative_path).rstrip("/")
        raw_prefix = f"{self.key_prefix}{base}/"
        prefix = raw_prefix.encode(self.key_encoding)
        found: list[str] = []
        with self._environment().begin(write=False, buffers=False) as txn:
            cursor = txn.cursor()
            # LMDB keys are byte-ordered, so every key under a prefix is one contiguous range:
            # seek to the prefix and stop at the first key that no longer starts with it.
            if not cursor.set_range(prefix):
                return []
            for key in cursor.iternext(keys=True, values=False):
                if not bytes(key).startswith(prefix):
                    break
                child = self._child_relative(bytes(key), len(raw_prefix), base)
                if child is not None:
                    found.append(child)
                    if limit is not None and len(found) >= limit:
                        break
        return found

    def describe(self) -> dict[str, str]:
        # No path: an LMDB store lives at an absolute local path (contract section 34).
        return {"storage_kind": self.kind, "storage_lmdb_lock": str(self.lock).lower()}
