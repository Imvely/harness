"""Dataset manifest schema, hashing, validation and (de)serialization.

A manifest is a JSONL file (one :class:`ManifestRecord` per line, sorted by ``sample_id``)
plus a ``.meta.json`` sidecar (:class:`ManifestMeta`). Records store only paths relative to
the media root named by ``meta.root_env_var`` so the ``manifest_hash`` is machine
independent and can be logged as run provenance (research contract sections 15 and 17).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from re import fullmatch
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pad_research.paths import repo_root
from pad_research.utils.canonical_json import canonical_json, sha256_text
from pad_research.utils.git import git_state


class Label(StrEnum):
    bona_fide = "bona_fide"
    spoof = "spoof"


class PAI(StrEnum):
    """Presentation attack instrument. ``none`` is reserved for bona fide samples."""

    none = "none"
    print = "print"
    replay = "replay"
    replay_phone = "replay_phone"
    replay_tablet = "replay_tablet"
    replay_display = "replay_display"
    display = "display"
    mask_3d = "mask_3d"
    other = "other"


class Split(StrEnum):
    train = "train"
    dev = "dev"
    test = "test"


class MediaType(StrEnum):
    video = "video"
    frames_dir = "frames_dir"
    image = "image"
    npy_clip = "npy_clip"


#: Accepted file suffixes per media type (lower-case). ``frames_dir`` is a directory.
MEDIA_EXTENSIONS: dict[MediaType, tuple[str, ...]] = {
    MediaType.npy_clip: (".npy",),
    MediaType.image: (".jpg", ".jpeg", ".png", ".bmp"),
    MediaType.video: (".mp4", ".avi", ".mov", ".mkv", ".mpg", ".mpeg", ".webm"),
    MediaType.frames_dir: (),
}

_DATASET_ID_RE = r"[a-z0-9_]+"
_SAMPLE_ID_RE = r"[A-Za-z0-9_\-.]+"


class ManifestTamperedError(RuntimeError):
    """The manifest content does not match the hash recorded in its ``.meta.json``."""


class ManifestNotFoundError(FileNotFoundError):
    """No manifest with the requested ``dataset_id`` exists in the manifests directory."""


class ManifestValidationError(ValueError):
    """The record set violates manifest invariants (see :func:`validate_records`)."""


class ManifestRecord(BaseModel):
    """One sample (clip/image) of a dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    sample_id: str
    subject_id: str
    split: Split
    label: Label
    pai: PAI
    pai_detail: str | None = None
    relative_path: str
    media_type: MediaType
    fps: float | None = None
    n_frames: int | None = None
    width: int | None = None
    height: int | None = None
    capture_device: str | None = None
    session: str | None = None
    environment: str | None = None
    official_protocol: str | None = None
    extra: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("dataset_id", mode="before")
    @classmethod
    def _normalize_dataset_id(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip().lower()
            if not fullmatch(_DATASET_ID_RE, value):
                raise ValueError(f"dataset_id {value!r} must match ^{_DATASET_ID_RE}$")
        return value

    @field_validator("sample_id")
    @classmethod
    def _check_sample_id(cls, value: str) -> str:
        if not fullmatch(_SAMPLE_ID_RE, value):
            raise ValueError(f"sample_id {value!r} must match ^{_SAMPLE_ID_RE}$")
        return value

    @field_validator("subject_id")
    @classmethod
    def _check_subject_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("subject_id must not be empty")
        return value

    @field_validator("relative_path")
    @classmethod
    def _check_relative_path(cls, value: str) -> str:
        if not value:
            raise ValueError("relative_path must not be empty")
        if "\\" in value:
            raise ValueError("relative_path must use '/' separators")
        if value.startswith("/") or PurePosixPath(value).is_absolute():
            raise ValueError(f"relative_path {value!r} must be relative to the data root")
        if PureWindowsPath(value).is_absolute() or PureWindowsPath(value).drive:
            raise ValueError(f"relative_path {value!r} must not contain a drive letter")
        if ".." in PurePosixPath(value).parts:
            raise ValueError(f"relative_path {value!r} must not contain '..'")
        return value

    @model_validator(mode="after")
    def _check_label_pai(self) -> ManifestRecord:
        if (self.label == Label.bona_fide) != (self.pai == PAI.none):
            raise ValueError(
                f"label/pai inconsistency for sample {self.sample_id!r}: "
                f"label={self.label.value} pai={self.pai.value} "
                "(bona_fide <=> pai == none)"
            )
        return self


class ManifestMeta(BaseModel):
    """Sidecar metadata for one manifest."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    version: str
    adapter: str
    license: str
    pii_policy: Literal["synthetic", "internal_only", "licensed_research"]
    root_env_var: str = "PAD_DATA_ROOT"
    temporal_valid: bool
    manifest_hash: str
    n_records: int
    n_subjects: int
    splits: dict[str, dict[str, int]]
    pai_counts: dict[str, int]
    created_at: str
    generator_commit: str | None

    @property
    def research_grade(self) -> bool:
        """True for real (non-synthetic) datasets whose results may support claims."""
        return self.pii_policy != "synthetic"


class Manifest(BaseModel):
    """Loaded manifest: records plus metadata."""

    model_config = ConfigDict(extra="forbid")

    records: list[ManifestRecord]
    meta: ManifestMeta

    def by_split(self, split: Split | str) -> list[ManifestRecord]:
        split = Split(split)
        return [r for r in self.records if r.split == split]

    def subjects(self, split: Split | str | None = None) -> set[str]:
        records = self.records if split is None else self.by_split(split)
        return {r.subject_id for r in records}

    def sample_ids(self) -> set[str]:
        return {r.sample_id for r in self.records}


def _sorted(records: Sequence[ManifestRecord]) -> list[ManifestRecord]:
    return sorted(records, key=lambda r: r.sample_id)


def _record_line(record: ManifestRecord) -> str:
    return canonical_json(record.model_dump(mode="json"))


def manifest_hash(records: Sequence[ManifestRecord]) -> str:
    """Return the sha256 of the canonical JSONL rendering of ``records`` (sorted by sample_id)."""
    return sha256_text("\n".join(_record_line(r) for r in _sorted(records)))


def validate_records(records: Sequence[ManifestRecord]) -> list[str]:
    """Return human-readable invariant violations (empty list means valid).

    Checks: unique ``sample_id``; single ``dataset_id``; label/pai consistency (defensive,
    pydantic already enforces it); subject leakage (a subject in more than one split); file
    suffix compatible with ``media_type``.
    """
    errors: list[str] = []

    id_counts = Counter(r.sample_id for r in records)
    for sample_id, count in sorted(id_counts.items()):
        if count > 1:
            errors.append(f"duplicate sample_id {sample_id!r} appears {count} times")

    dataset_ids = sorted({r.dataset_id for r in records})
    if len(dataset_ids) > 1:
        errors.append(f"records mix dataset_ids {dataset_ids}")

    subject_splits: dict[str, set[str]] = defaultdict(set)
    for r in records:
        subject_splits[r.subject_id].add(r.split.value)
        if (r.label == Label.bona_fide) != (r.pai == PAI.none):
            errors.append(
                f"label/pai inconsistency for {r.sample_id!r}: {r.label.value}/{r.pai.value}"
            )
        allowed = MEDIA_EXTENSIONS.get(r.media_type, ())
        if allowed and not r.relative_path.lower().endswith(allowed):
            errors.append(
                f"relative_path {r.relative_path!r} of {r.sample_id!r} does not end with one of "
                f"{list(allowed)} required for media_type {r.media_type.value}"
            )
    for subject_id, splits in sorted(subject_splits.items()):
        if len(splits) > 1:
            errors.append(
                f"subject leakage: subject {subject_id!r} appears in splits {sorted(splits)}"
            )
    return errors


def _split_summary(records: Sequence[ManifestRecord]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for split in Split:
        rows = [r for r in records if r.split == split]
        summary[split.value] = {
            "n_records": len(rows),
            "n_subjects": len({r.subject_id for r in rows}),
            "n_bona_fide": sum(1 for r in rows if r.label == Label.bona_fide),
            "n_attack": sum(1 for r in rows if r.label == Label.spoof),
        }
    return summary


def _manifest_paths(dataset_id: str, manifests_dir: Path) -> tuple[Path, Path]:
    return manifests_dir / f"{dataset_id}.jsonl", manifests_dir / f"{dataset_id}.meta.json"


def _previous_generation(meta_path: Path, new_hash: str) -> tuple[str | None, str | None]:
    """Return ``(created_at, generator_commit)`` of a sidecar whose hash equals ``new_hash``.

    Re-running a builder over unchanged data then leaves the committed sidecar byte-identical
    (idempotent build) instead of churning the timestamp. The commit travels with the
    timestamp: keeping ``created_at`` while overwriting ``generator_commit`` would make the
    pair describe two different runs, and the sidecar would claim the records came from a
    commit that merely re-ran the builder. A previously missing commit (``null``) falls
    through so a later run can still supply real provenance.
    """
    if not meta_path.is_file():
        return None, None
    try:
        previous = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    if not isinstance(previous, dict) or previous.get("manifest_hash") != new_hash:
        return None, None
    created = previous.get("created_at")
    commit = previous.get("generator_commit")
    return (
        created if isinstance(created, str) else None,
        commit if isinstance(commit, str) and commit else None,
    )


def write_manifest(
    records: Sequence[ManifestRecord], meta_partial: dict[str, Any], out_dir: Path
) -> ManifestMeta:
    """Write ``<dataset_id>.jsonl`` and ``<dataset_id>.meta.json`` under ``out_dir``.

    ``meta_partial`` supplies the adapter-owned fields (``dataset_id``, ``version``,
    ``adapter``, ``license``, ``pii_policy``, ``temporal_valid`` and optionally
    ``root_env_var``); the derived fields are computed here.
    """
    if not records:
        raise ManifestValidationError("cannot write an empty manifest")
    problems = validate_records(records)
    if problems:
        raise ManifestValidationError("; ".join(problems))

    dataset_id = str(meta_partial["dataset_id"]).lower()
    record_ids = {r.dataset_id for r in records}
    if record_ids != {dataset_id}:
        raise ManifestValidationError(
            f"records carry dataset_id {sorted(record_ids)} but meta says {dataset_id!r}"
        )

    ordered = _sorted(records)
    digest = manifest_hash(ordered)
    jsonl_path, meta_path = _manifest_paths(dataset_id, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    previous_created_at, previous_commit = _previous_generation(meta_path, digest)
    created_at = previous_created_at or datetime.now(UTC).isoformat(timespec="seconds")
    generator_commit = previous_commit or git_state(repo_root()).sha
    meta = ManifestMeta(
        dataset_id=dataset_id,
        version=str(meta_partial["version"]),
        adapter=str(meta_partial["adapter"]),
        license=str(meta_partial["license"]),
        pii_policy=meta_partial["pii_policy"],
        root_env_var=str(meta_partial.get("root_env_var", "PAD_DATA_ROOT")),
        temporal_valid=bool(meta_partial["temporal_valid"]),
        manifest_hash=digest,
        n_records=len(ordered),
        n_subjects=len({r.subject_id for r in ordered}),
        splits=_split_summary(ordered),
        pai_counts=dict(sorted(Counter(r.pai.value for r in ordered).items())),
        created_at=created_at,
        generator_commit=generator_commit,
    )

    jsonl_text = "\n".join(_record_line(r) for r in ordered) + "\n"
    jsonl_path.write_text(jsonl_text, encoding="utf-8", newline="\n")
    meta_path.write_text(
        json.dumps(meta.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return meta


def load_manifest(dataset_id: str, manifests_dir: Path) -> Manifest:
    """Load and verify a manifest; raises :class:`ManifestTamperedError` on hash mismatch."""
    dataset_id = dataset_id.lower()
    jsonl_path, meta_path = _manifest_paths(dataset_id, manifests_dir)
    if not jsonl_path.is_file() or not meta_path.is_file():
        raise ManifestNotFoundError(
            f"manifest for dataset_id {dataset_id!r} not found under {manifests_dir} "
            f"(expected {jsonl_path.name} and {meta_path.name})"
        )
    meta = ManifestMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    records = [
        ManifestRecord.model_validate_json(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    digest = manifest_hash(records)
    if digest != meta.manifest_hash:
        raise ManifestTamperedError(
            f"manifest {dataset_id!r}: content hash {digest[:12]} != recorded "
            f"{meta.manifest_hash[:12]} (records or sidecar were modified)"
        )
    if meta.n_records != len(records):
        raise ManifestTamperedError(
            f"manifest {dataset_id!r}: {len(records)} records but meta says {meta.n_records}"
        )
    if meta.dataset_id != dataset_id:
        raise ManifestTamperedError(
            f"manifest file {dataset_id!r} carries meta.dataset_id {meta.dataset_id!r}"
        )
    return Manifest(records=records, meta=meta)


def resolve_path(record: ManifestRecord, root: Path) -> Path:
    """Return the absolute media path of ``record`` under the data ``root``."""
    return Path(root) / PurePosixPath(record.relative_path)
