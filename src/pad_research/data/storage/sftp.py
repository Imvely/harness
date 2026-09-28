"""SFTP backend: read a dataset that only exists on another machine.

**Prefer a mount.** ``sshfs`` (or NFS, or SMB) exposes the same remote directory to the
kernel, which then gives it a page cache, readahead and a real file descriptor that PyAV can
stream from. This class has none of that: every read is a round trip that pulls the whole
object into the worker's memory, and a 200 MB video is 200 MB of RSS per worker. It exists
because a mount is not always available — a shared server where nobody has FUSE permissions,
a quick look at a colleague's copy — and in those cases a slow read beats no read.

Credentials never appear in a config file. ``configs/storage/sftp.yaml`` holds a host, a port,
a username and the *name* of an environment variable; the value is read from the environment
at connect time and is never logged, never written to MLflow and never exported to the
dashboard. Key-based authentication through a running ssh-agent needs no secret at all and is
the default.

The connection is opened lazily and re-opened when the pid changes: an SSH transport carries
cipher state that two processes cannot share, so a channel inherited across a DataLoader's
``fork()`` corrupts both sides.
"""

from __future__ import annotations

import os
import stat as stat_module
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from pad_research.data.storage.base import (
    PerProcessResource,
    StorageNotFoundError,
    StorageUnavailableError,
    check_relative,
    sort_children,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import paramiko


class SftpStorage:
    """Serve manifest relative paths from a remote directory over SFTP."""

    kind = "sftp"

    def __init__(
        self,
        host: str,
        remote_root: str,
        *,
        port: int = 22,
        username: str | None = None,
        key_filename: str | None = None,
        password_env_var: str | None = None,
        known_hosts: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.host = host
        self.remote_root = PurePosixPath(remote_root)
        self.port = int(port)
        self.username = username
        self.key_filename = key_filename
        self.password_env_var = password_env_var
        self.known_hosts = known_hosts
        self.timeout = float(timeout)
        self._client: PerProcessResource[Any] = PerProcessResource()

    # -- connection -------------------------------------------------------------------

    def _connect(self) -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
        try:
            import paramiko
        except ImportError as exc:
            raise StorageUnavailableError(
                "the paramiko driver is not installed; install the optional extra with "
                "`uv sync --extra sftp`, or mount the remote directory and use the local backend"
            ) from exc

        client = paramiko.SSHClient()
        # An unknown host key is refused rather than trusted on first use: silently accepting
        # it would let anything that can answer on that address hand back face data.
        client.load_system_host_keys()
        if self.known_hosts:
            client.load_host_keys(str(Path(self.known_hosts).expanduser()))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())

        password = os.environ.get(self.password_env_var) if self.password_env_var else None
        if self.password_env_var and not password:
            raise StorageUnavailableError(
                f"environment variable {self.password_env_var} is empty; "
                "export it in the shell that launches the run"
            )
        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                key_filename=self.key_filename,
                password=password,
                timeout=self.timeout,
                allow_agent=True,
                look_for_keys=True,
            )
            return client, client.open_sftp()
        except Exception as exc:  # paramiko raises several unrelated exception types
            # Only the class name: paramiko's messages quote hosts, users and key paths.
            raise StorageUnavailableError(
                f"cannot open an SFTP connection: {type(exc).__name__} "
                "(check the host, the username and that your key is loaded)"
            ) from exc

    def _sftp(self) -> paramiko.SFTPClient:
        return self._client.get(self._connect)[1]

    def close(self) -> None:
        def _close(handle: tuple[Any, Any]) -> None:
            client, sftp = handle
            sftp.close()
            client.close()

        self._client.close(_close)

    # -- reads ------------------------------------------------------------------------

    def _remote(self, relative_path: str) -> str:
        return str(self.remote_root / check_relative(relative_path))

    def local_path(self, relative_path: str) -> Path | None:
        """Always ``None``: there is no local file, so decoders read bytes."""
        return None

    def read_bytes(self, relative_path: str) -> bytes:
        try:
            with self._sftp().open(self._remote(relative_path), "rb") as handle:
                # One large request instead of many small ones; without it paramiko issues a
                # 32 KiB round trip per chunk, which over a real network is the whole cost.
                handle.prefetch()
                return bytes(handle.read())
        except FileNotFoundError as exc:
            raise StorageNotFoundError(f"no remote object at {relative_path!r}") from exc
        except OSError as exc:
            raise StorageUnavailableError(
                f"cannot read {relative_path!r} over SFTP: {type(exc).__name__}"
            ) from exc

    def _stat(self, relative_path: str) -> Any | None:
        try:
            return self._sftp().stat(self._remote(relative_path))
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StorageUnavailableError(
                f"cannot stat {relative_path!r} over SFTP: {type(exc).__name__}"
            ) from exc

    def exists(self, relative_path: str) -> bool:
        return self._stat(relative_path) is not None

    def is_dir(self, relative_path: str) -> bool:
        info = self._stat(relative_path)
        return info is not None and stat_module.S_ISDIR(info.st_mode or 0)

    def list_children(self, relative_path: str) -> list[str]:
        base = relative_path.rstrip("/")
        try:
            entries = self._sftp().listdir_attr(self._remote(relative_path))
        except FileNotFoundError as exc:
            raise StorageNotFoundError(f"no remote directory at {relative_path!r}") from exc
        except OSError as exc:
            raise StorageUnavailableError(
                f"cannot list {relative_path!r} over SFTP: {type(exc).__name__}"
            ) from exc
        return sort_children(
            [
                f"{base}/{entry.filename}"
                for entry in entries
                if not stat_module.S_ISDIR(entry.st_mode or 0)
            ]
        )

    def describe(self) -> dict[str, str]:
        # Neither the host nor the remote root: both identify a machine and a user's data
        # location, and this dict is written to MLflow tags (contract section 34).
        return {"storage_kind": self.kind}
