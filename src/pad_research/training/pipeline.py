"""Shared runtime helpers for the Phase 0 train/adapt/evaluate scripts."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import yaml
from torch.utils.data import DataLoader

from pad_research import paths
from pad_research.config.schema import ExperimentSpec, SmokeLimits, science_hash, spec_hash
from pad_research.data.clip_dataset import ClipBatch, ClipDataset, collate
from pad_research.data.manifest import Manifest, ManifestRecord, load_manifest
from pad_research.data.splits import ProtocolSplits, build_splits
from pad_research.experiments.gate import GpuInfo
from pad_research.experiments.registry import RegistryRow, utc_now
from pad_research.experiments.status import RunStatus
from pad_research.protocols.adaptation_set import (
    AdaptationSelection,
    materialize_adaptation_set,
    select_adaptation_set,
)
from pad_research.protocols.validator import ProtocolValidation
from pad_research.utils.git import GitState
from pad_research.utils.seed import make_generator, worker_init_fn


def effective_limits(spec: ExperimentSpec) -> SmokeLimits | None:
    """Return smoke limits only when the execution mode is ``smoke``."""
    return spec.execution.smoke if spec.execution.mode == "smoke" else None


def eval_loader_budget(spec: ExperimentSpec, limits: SmokeLimits | None) -> tuple[int, int | None]:
    """Return ``(batch_size, max_batches)`` for the dev/test evaluation loaders.

    A smoke evaluation reads at most ``batch_size * max_eval_batches`` samples per split.
    The scripts used to widen the batch by ``max_eval_batches`` *and* still stop after
    ``max_eval_batches`` batches, so the real budget was ``batch_size * max_eval_batches ** 2``:
    at the schema ceiling (batch 8, cap 20) that is 3200 samples, and a 'smoke' evaluation
    silently becomes a full one, which is what ``SmokeLimits`` exists to prevent. Keep the
    batch at its configured size and let the batch cap alone do the limiting, so the budget
    is linear in ``max_eval_batches`` and an experiment that needs the whole split says so by
    raising that one number.
    """
    if limits is None:
        return spec.training.batch_size, None
    return spec.training.batch_size, limits.max_eval_batches


def load_protocol_manifests(spec: ExperimentSpec, manifests_dir: Path) -> dict[str, Manifest]:
    """Load every source and target manifest referenced by ``spec.protocol``."""
    dataset_ids = [*spec.protocol.source_datasets, *spec.protocol.target_dataset]
    return {dataset_id: load_manifest(dataset_id, manifests_dir) for dataset_id in dataset_ids}


def select_and_materialize_adaptation(
    spec: ExperimentSpec,
    manifests: Mapping[str, Manifest],
    manifests_dir: Path,
) -> tuple[AdaptationSelection | None, Path | None]:
    """Select and write the protocol adaptation set when the protocol enables one."""
    if not spec.protocol.target_adaptation.enabled:
        return None, None
    if len(spec.protocol.target_dataset) != 1:
        raise ValueError("Phase 0 supports a single target dataset for adaptation")
    target = manifests[spec.protocol.target_dataset[0]]
    selection = select_adaptation_set(spec.protocol, target)
    path = materialize_adaptation_set(selection, manifests_dir / "adaptation", target)
    return selection, path


def protocol_splits(
    spec: ExperimentSpec,
    manifests: Mapping[str, Manifest],
    selection: AdaptationSelection | None,
) -> ProtocolSplits:
    """Build splits for ``spec`` from loaded manifests and an optional adaptation set."""
    return build_splits(spec.protocol, manifests, selection)


def make_loader(
    records: Sequence[ManifestRecord],
    spec: ExperimentSpec,
    *,
    data_root: Path,
    batch_size: int,
    train: bool,
    seed_offset: int = 0,
    drop_last: bool | None = None,
    shuffle: bool | None = None,
) -> DataLoader[ClipBatch]:
    """Create a deterministic DataLoader for manifest records."""
    dataset = ClipDataset(
        records,
        data_root,
        frames=spec.model.input.frames,
        sampling=spec.model.input.frame_sampling,
        image_size=spec.model.input.image_size,
        train=train,
        seed=spec.training.seed + seed_offset,
    )
    do_shuffle = train if shuffle is None else shuffle
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=do_shuffle,
        drop_last=(spec.data.loader.drop_last if drop_last is None else drop_last),
        num_workers=spec.data.loader.num_workers,
        pin_memory=spec.data.loader.pin_memory,
        collate_fn=collate,
        generator=make_generator(spec.training.seed + seed_offset) if do_shuffle else None,
        worker_init_fn=worker_init_fn if spec.data.loader.num_workers else None,
    )
    return cast(DataLoader[ClipBatch], loader)


def run_output_dir() -> Path:
    """Return Hydra's output directory, or the default output root outside Hydra."""
    try:
        from hydra.core.hydra_config import HydraConfig

        return Path(str(HydraConfig.get().runtime.output_dir))
    except ValueError:
        return paths.output_root()


def write_json(path: Path, obj: object) -> Path:
    """Write JSON with stable key ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _jsonable(obj)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def write_resolved_spec_to_run(path: Path, spec: ExperimentSpec) -> Path:
    """Write the resolved spec into a run directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# GENERATED by scripts/train.py or scripts/adapt.py - do not edit by hand.\n"
        f"# science_hash: {science_hash(spec)}\n"
        f"# spec_hash: {spec_hash(spec)}\n"
    )
    path.write_text(
        header + yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def write_train_curve_csv(path: Path, curve: list[dict[str, float | int]]) -> Path:
    """Write training curve rows to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["epoch", "train_loss", "steps"])
        writer.writeheader()
        writer.writerows(curve)
    return path


def registry_row(
    spec: ExperimentSpec,
    pv: ProtocolValidation,
    git: GitState,
    status: RunStatus,
    *,
    started_at: str,
    finished_at: str | None = None,
    results_dir: Path | None = None,
    mlflow_run_id: str | None = None,
    note: str | None = None,
    adaptation_set_hash: str | None = None,
) -> RegistryRow:
    """Create a registry row for the current run."""
    return RegistryRow(
        exp_id=spec.experiment.id,
        seed=spec.training.seed,
        mode=spec.execution.mode,
        science_hash=science_hash(spec),
        spec_hash=spec_hash(spec),
        protocol_id=spec.protocol.protocol_id,
        protocol_hash=pv.protocol_hash,
        adaptation_set_hash=adaptation_set_hash or pv.adaptation_set_hash,
        mlflow_run_id=mlflow_run_id,
        status=status,
        git_sha=git.sha,
        git_dirty=git.dirty,
        started_at=started_at,
        finished_at=finished_at,
        results_dir=str(results_dir) if results_dir is not None else None,
        note=note,
    )


def invalid_registry_row(
    exp_id: str,
    status: RunStatus,
    git: GitState,
    *,
    note: str,
) -> RegistryRow:
    """Create a best-effort registry row before a spec/protocol exists."""
    now = utc_now()
    return RegistryRow(
        exp_id=exp_id,
        seed=None,
        mode="unknown",
        science_hash=None,
        spec_hash=None,
        protocol_id=None,
        protocol_hash=None,
        adaptation_set_hash=None,
        mlflow_run_id=None,
        status=status,
        git_sha=git.sha,
        git_dirty=git.dirty,
        started_at=now,
        finished_at=now,
        results_dir=None,
        note=note,
    )


def torch_gpu_info() -> GpuInfo:
    """Return CUDA availability through torch for the in-process gate."""
    import torch

    available = bool(torch.cuda.is_available())
    names = (
        [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
        if available
        else []
    )
    return GpuInfo(cuda_available=available, gpu_names=names)


def terminal_status_for_pass(spec: ExperimentSpec) -> RunStatus:
    """Return the normal terminal status for a completed train/evaluate run."""
    return RunStatus.smoke_ok if spec.execution.mode == "smoke" else RunStatus.success


def _jsonable(obj: object) -> object:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")  # type: ignore[reportUnknownMemberType]
    if isinstance(obj, dict):
        return {str(key): _jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(value) for value in obj]
    return obj
