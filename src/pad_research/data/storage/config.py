"""Declarative storage configuration (the ``storage:`` block of an experiment spec).

One rule shapes every field here: **a location is named by an environment variable, never
written down**. ``configs/storage/*.yaml`` is committed, and ``validate_spec --freeze`` copies
the resolved block into ``experiments/specs/<id>.resolved.yaml``, which is committed too. A
literal ``/mnt/nas/faces/oulu`` or ``gpu03.lab.internal`` in either of those is a machine path
or a hostname in a public git history, which contract section 34 forbids, and it is also what
makes a spec unusable on the next person's machine.

So the config carries *indirections* (``root_env_var: PAD_DATA_ROOT``) plus knobs that are
true everywhere (a key prefix, a port, whether the store is being written). The values live in
the shell that launches the run. That is the same contract ``PAD_DATA_ROOT`` has always had;
this module only extends it to LMDB and SFTP.

The three configs are a discriminated union on ``kind``, so an unknown backend name fails
during Hydra composition with a readable pydantic error instead of at the first batch.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

#: Environment variables a storage config may point at, for the diagnosis CLI and the UI.
StorageKind = Literal["local", "lmdb", "sftp"]


class _StorageBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def env_vars(self) -> list[str]:
        """Return the environment variables this config needs, in the order to set them."""
        names = [getattr(self, f) for f in type(self).model_fields if f.endswith("_env_var")]
        return [n for n in names if isinstance(n, str) and n]


class LocalStorageConfig(_StorageBase):
    """A directory tree: a local disk, an NFS/SMB share, or an sshfs/FUSE mount."""

    kind: Literal["local"] = "local"
    root_env_var: str = "PAD_DATA_ROOT"


class LmdbStorageConfig(_StorageBase):
    """An LMDB store whose keys are the manifest's ``relative_path`` values."""

    kind: Literal["lmdb"]
    path_env_var: str = "PAD_LMDB_PATH"
    #: Prepended to every manifest ``relative_path`` to form the key. Use it when the store
    #: was built with a prefix the manifest does not carry (``"oulu_npu/"``).
    key_prefix: str = ""
    #: Appended to every key, for stores that suffix their keys (``".jpg"``).
    key_suffix: str = ""
    key_encoding: str = "utf-8"
    #: Leave false for a finished store. Set true only while another process is writing it:
    #: it restores the reader lock table at the cost of needing a writable ``lock.mdb``.
    lock: bool = False
    readahead: bool = False
    max_readers: int = Field(default=2048, ge=1)


class SftpStorageConfig(_StorageBase):
    """A remote directory read over SSH. Prefer mounting it and using ``local``."""

    kind: Literal["sftp"]
    host_env_var: str = "PAD_SFTP_HOST"
    remote_root_env_var: str = "PAD_SFTP_ROOT"
    username_env_var: str = "PAD_SFTP_USER"
    #: Optional. Unset means key authentication through a running ssh-agent, which is the
    #: only form that leaves no secret anywhere for this process to mishandle.
    password_env_var: str | None = None
    key_filename_env_var: str | None = None
    known_hosts_env_var: str | None = None
    port: int = Field(default=22, ge=1, le=65535)
    timeout: float = Field(default=20.0, gt=0)


StorageConfig = Annotated[
    LocalStorageConfig | LmdbStorageConfig | SftpStorageConfig,
    Field(discriminator="kind"),
]

__all__ = [
    "LmdbStorageConfig",
    "LocalStorageConfig",
    "SftpStorageConfig",
    "StorageConfig",
    "StorageKind",
]
