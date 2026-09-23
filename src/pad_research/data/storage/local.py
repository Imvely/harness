"""Filesystem backend: an ordinary directory tree under one root.

This is the backend every other one is measured against, and it covers far more than "the
data is on this laptop". Anything the operating system has already made to look like a
directory reaches the harness through this class with no code of its own: an NFS or SMB
share, a FUSE mount made with ``sshfs``, a bind-mounted volume inside a container. Mounting
is why :mod:`pad_research.data.storage.sftp` is a fallback rather than the recommended way
to read a remote dataset — the kernel's page cache and readahead beat anything this
repository could implement over a single SSH channel, and no credential ever enters a config
file here.
"""

from __future__ import annotations

from pathlib import Path

from pad_research.data.storage.base import (
    StorageNotFoundError,
    StorageUnavailableError,
    check_relative,
    sort_children,
)


class LocalStorage:
    """Serve ``<root>/<relative_path>`` from the local filesystem."""

    kind = "local"

    def __init__(self, root: Path | str, *, require_root: bool = False) -> None:
        self.root = Path(root).expanduser()
        if require_root and not self.root.is_dir():
            # The path itself is not in the message: it may name a user's home directory
            # and this text reaches logs and the registry (contract section 34).
            raise StorageUnavailableError(
                "storage root is not an existing directory "
                "(check PAD_DATA_ROOT, or the mount that should provide it)"
            )

    def _resolve(self, relative_path: str) -> Path:
        return self.root / check_relative(relative_path)

    def local_path(self, relative_path: str) -> Path | None:
        return self._resolve(relative_path)

    def read_bytes(self, relative_path: str) -> bytes:
        path = self._resolve(relative_path)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageNotFoundError(f"no object at {relative_path!r}") from exc
        except OSError as exc:
            raise StorageUnavailableError(f"cannot read {relative_path!r}: {exc.strerror}") from exc

    def exists(self, relative_path: str) -> bool:
        return self._resolve(relative_path).exists()

    def is_dir(self, relative_path: str) -> bool:
        return self._resolve(relative_path).is_dir()

    def list_children(self, relative_path: str) -> list[str]:
        directory = self._resolve(relative_path)
        if not directory.is_dir():
            raise StorageNotFoundError(f"no directory at {relative_path!r}")
        base = relative_path.rstrip("/")
        return sort_children([f"{base}/{p.name}" for p in directory.iterdir() if p.is_file()])

    def describe(self) -> dict[str, str]:
        # The root is deliberately absent: it is a local absolute path.
        return {"storage_kind": self.kind}

    def close(self) -> None:
        return None
