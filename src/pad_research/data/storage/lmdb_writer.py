"""Write one LMDB store. The only place in this project that opens LMDB for writing.

Everything else that touches a store is read-only on purpose: :mod:`.lmdb_store` serves a
manifest out of one, and ``scripts/inspect_lmdb_layout.py`` cannot write at all. A build needs a
writer, and keeping it alone in its own module makes that boundary visible in an import list.

The write flags, and why each one:

``readonly=False``, ``lock=True``
    A writer needs the lock table: it is what keeps a second writer out.
``map_size``
    LMDB reserves the address space up front and fails with ``MDB_MAP_FULL`` when a write no
    longer fits. The size is a sparse reservation, not disk that is used, so the builder passes
    the measured frame total plus headroom rather than a guess (ADR-016 names capacity first).
``sync=True``, ``writemap=False``
    The default durability. A build runs once on a shared filesystem where ``writemap`` is the
    documented way to corrupt a store if the mapping is sparse-file backed.

Two refusals are deliberate:

* **An existing store is not reopened.** A second build into the same directory would append to
  whatever is there, and the result would carry frames from two selection rules with no way to
  tell them apart. The path must not exist.
* **A key is never overwritten.** ``put(..., overwrite=False)`` and the error that follows are
  the last line of the same defence the builder starts with, since a silent overwrite is what
  cost Replay-Attack 79,091 frames (ADR-013).
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Any

#: Frames per transaction. One transaction per frame would fsync millions of times; one for the
#: whole build would hold every page in memory. A few thousand is the usual middle.
DEFAULT_BATCH = 2000
#: Headroom over the measured payload: LMDB stores keys and B+tree pages besides the values.
MAP_SIZE_HEADROOM = 1.25
MIN_MAP_SIZE = 64 * 1024 * 1024


class LmdbWriteError(RuntimeError):
    """The store cannot be written: it exists, a key repeats, or the map is full."""


def map_size_for(payload_bytes: int, *, headroom: float = MAP_SIZE_HEADROOM) -> int:
    """Address space to reserve for a payload of ``payload_bytes``."""
    if payload_bytes < 0:
        raise ValueError("payload_bytes must not be negative")
    return max(MIN_MAP_SIZE, int(payload_bytes * headroom))


class LmdbSink:
    """A :class:`~pad_research.data.build_store.FrameSink` that writes frames into a new LMDB."""

    def __init__(
        self,
        path: Path | str,
        *,
        map_size: int,
        batch_size: int = DEFAULT_BATCH,
        key_encoding: str = "utf-8",
    ) -> None:
        self.path = Path(path).expanduser()
        if self.path.exists():
            raise LmdbWriteError(
                f"{self.path} already exists; a build writes a new store so two selection "
                "rules can never end up mixed in one. Move or remove it first."
            )
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self.map_size = int(map_size)
        self.batch_size = int(batch_size)
        self.key_encoding = key_encoding
        self.n_written = 0
        self._env: Any = None
        self._txn: Any = None
        self._pending = 0

    # -- lifecycle ---------------------------------------------------------------------

    def _environment(self) -> Any:
        if self._env is None:
            try:
                import lmdb
            except ImportError as exc:  # pragma: no cover - exercised only without the extra
                raise LmdbWriteError(
                    "the lmdb driver is not installed; run `uv sync` (lmdb is a dependency)"
                ) from exc
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._env = lmdb.open(
                str(self.path),
                subdir=True,
                readonly=False,
                lock=True,
                map_size=self.map_size,
                writemap=False,
                sync=True,
                meminit=False,
                max_dbs=0,
            )
        return self._env

    def _transaction(self) -> Any:
        if self._txn is None:
            self._txn = self._environment().begin(write=True)
        return self._txn

    def _commit(self) -> None:
        if self._txn is not None:
            self._txn.commit()
            self._txn = None
            self._pending = 0

    # -- writing -----------------------------------------------------------------------

    def put(self, key: str, value: bytes) -> None:
        """Store one frame. Raises rather than overwriting a key that is already there."""
        encoded = key.encode(self.key_encoding)
        try:
            stored = self._transaction().put(encoded, value, overwrite=False)
        except Exception as exc:  # lmdb.MapFullError and friends
            self._abort()
            raise LmdbWriteError(
                f"cannot write key {key!r}: {type(exc).__name__}. If the map is full, rebuild "
                "with a larger map_size (the payload estimate was too low)."
            ) from exc
        if not stored:
            self._abort()
            raise LmdbWriteError(
                f"key {key!r} is already in the store; refusing to overwrite it "
                "(this is what silently dropped 79,091 frames in the lab's store)"
            )
        self.n_written += 1
        self._pending += 1
        if self._pending >= self.batch_size:
            self._commit()

    def _abort(self) -> None:
        if self._txn is not None:
            self._txn.abort()
            self._txn = None
            self._pending = 0

    def close(self) -> None:
        """Commit what is pending and close the environment. Safe to call twice."""
        self._commit()
        if self._env is not None:
            self._env.sync(True)
            self._env.close()
            self._env = None

    # -- context manager ---------------------------------------------------------------

    def __enter__(self) -> LmdbSink:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self._abort()
            if self._env is not None:
                self._env.close()
                self._env = None
            return
        self.close()


__all__ = [
    "DEFAULT_BATCH",
    "MAP_SIZE_HEADROOM",
    "MIN_MAP_SIZE",
    "LmdbSink",
    "LmdbWriteError",
    "map_size_for",
]
