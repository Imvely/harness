"""Answer one question before a run starts: can this machine actually read this dataset?

The failure this exists to prevent is a job that survives ``validate_spec``, queues on the
H100, and dies twenty minutes later on the first batch because one environment variable was
spelled differently in that shell. The checks run in dependency order and stop at the first
one that fails, so the message names the actual cause rather than its last symptom.

Nothing here decodes a whole clip into the report, and no message contains a path, a host or
a key: a diagnosis is printed to a terminal, may be pasted into an issue, and is subject to
the same rules as any other log (contract section 34).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from pad_research.data.manifest import Manifest, ManifestNotFoundError, MediaType, load_manifest
from pad_research.data.storage.base import StorageBackend, StorageError
from pad_research.data.storage.config import StorageConfig
from pad_research.data.storage.registry import build_storage

CheckStatus = Literal["pass", "fail", "skip"]

#: How many records a probe reads. Enough to catch a key-prefix mistake that happens to work
#: for the first sample, small enough that the command stays interactive over SFTP.
DEFAULT_PROBE = 5


class StorageCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: CheckStatus
    detail: str = ""
    #: What to do about it, in the imperative. Empty when the check passed.
    remedy: str = ""


class StorageDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    storage_kind: str
    dataset_id: str | None = None
    env_vars: list[str] = []
    n_probed: int = 0
    checks: list[StorageCheck] = []

    def failures(self) -> list[StorageCheck]:
        return [c for c in self.checks if c.status == "fail"]


def _probe_record(storage: StorageBackend, relative_path: str, media_type: MediaType) -> None:
    """Raise :class:`StorageError` unless ``relative_path`` can be reached and read."""
    if media_type == MediaType.frames_dir:
        children = storage.list_children(relative_path)
        if not children:
            raise StorageError(f"no children under {relative_path!r}")
        relative_path = children[0]
    local = storage.local_path(relative_path)
    if local is not None:
        if not local.is_file():
            raise StorageError(f"no file at {relative_path!r}")
        # One byte proves the permission bits and the mount, without pulling a video into RAM.
        with local.open("rb") as handle:
            handle.read(1)
        return
    if not storage.read_bytes(relative_path):
        raise StorageError(f"object at {relative_path!r} is empty")


def diagnose_storage(
    config: StorageConfig,
    *,
    manifests_dir: Path,
    dataset_id: str | None = None,
    probe: int = DEFAULT_PROBE,
) -> StorageDiagnosis:
    """Run the connection checks and return what a person needs to fix."""
    checks: list[StorageCheck] = []
    env_vars = config.env_vars()
    report = StorageDiagnosis(ok=False, storage_kind=config.kind, env_vars=env_vars)

    def finish(ok: bool) -> StorageDiagnosis:
        report.ok = ok
        report.checks = checks
        return report

    try:
        storage = build_storage(config, require_root=True)
    except StorageError as exc:
        checks.append(
            StorageCheck(
                name="BACKEND_REACHABLE",
                status="fail",
                detail=str(exc),
                remedy=(
                    f"set {', '.join(env_vars)} in this shell"
                    if env_vars
                    else "check the storage configuration"
                ),
            )
        )
        return finish(False)
    checks.append(StorageCheck(name="BACKEND_REACHABLE", status="pass"))

    if dataset_id is None:
        checks.append(
            StorageCheck(
                name="MANIFEST_READABLE",
                status="skip",
                detail="no dataset_id given, so no sample was read",
                remedy="re-run with --dataset-id <id> to prove the media is reachable",
            )
        )
        return finish(True)

    report.dataset_id = dataset_id
    try:
        manifest: Manifest = load_manifest(dataset_id, manifests_dir)
    except ManifestNotFoundError:
        checks.append(
            StorageCheck(
                name="MANIFEST_READABLE",
                status="fail",
                detail=f"no manifest for dataset_id {dataset_id!r}",
                remedy="build it with scripts/prepare_dataset.py --adapter <name>",
            )
        )
        return finish(False)
    except ValueError as exc:
        checks.append(
            StorageCheck(
                name="MANIFEST_READABLE",
                status="fail",
                detail=type(exc).__name__,
                remedy="rebuild the manifest; its content no longer matches its recorded hash",
            )
        )
        return finish(False)
    checks.append(
        StorageCheck(
            name="MANIFEST_READABLE",
            status="pass",
            detail=f"{manifest.meta.n_records} records, manifest_hash {manifest.meta.manifest_hash[:12]}",
        )
    )

    # Spread the probe across the manifest rather than taking the first N: records are sorted
    # by sample_id, so the first N are usually one subject in one split, and a layout mistake
    # that only affects attacks or only affects the test split would go unnoticed.
    records = manifest.records
    n = max(1, min(int(probe), len(records)))
    step = max(1, len(records) // n)
    sample = records[::step][:n]
    report.n_probed = len(sample)

    failures: list[str] = []
    for record in sample:
        try:
            _probe_record(storage, record.relative_path, record.media_type)
        except StorageError as exc:
            failures.append(f"{record.sample_id}: {exc}")
        except OSError as exc:
            failures.append(f"{record.sample_id}: {type(exc).__name__}")

    storage.close()
    if failures:
        checks.append(
            StorageCheck(
                name="MEDIA_READABLE",
                status="fail",
                detail=f"{len(failures)}/{len(sample)} probed samples unreachable; "
                + "; ".join(failures[:3]),
                remedy=(
                    "the backend is up but the manifest's relative_path values do not resolve "
                    "in it. For lmdb, check storage.key_prefix/key_suffix against the keys the "
                    "store was built with; for local, check that the root is the directory the "
                    "manifest paths are relative to"
                ),
            )
        )
        return finish(False)

    checks.append(
        StorageCheck(
            name="MEDIA_READABLE",
            status="pass",
            detail=f"{len(sample)} sampled records readable",
        )
    )
    return finish(True)


__all__ = ["DEFAULT_PROBE", "StorageCheck", "StorageDiagnosis", "diagnose_storage"]
