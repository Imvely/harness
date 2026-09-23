"""Checkpoint I/O for Phase 0 runs.

Checkpoints contain only a tensor ``state_dict`` and JSON-compatible metadata.
They intentionally do not pickle Pydantic objects or strategy instances, so
``torch.load(..., weights_only=True)`` can read them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from torch import Tensor

from pad_research import paths
from pad_research.config.schema import ExperimentSpec, science_hash, spec_hash
from pad_research.metrics.threshold import ThresholdPolicy
from pad_research.models.base import PADModel
from pad_research.utils.git import git_state


@dataclass(frozen=True)
class Checkpoint:
    state_dict: dict[str, Tensor]
    meta: dict[str, Any]
    spec: ExperimentSpec
    threshold: ThresholdPolicy | None
    protocol_hash: str
    science_hash: str
    git_sha: str | None
    strategy_state: dict[str, Any]


def _state_dict_cpu(model: PADModel) -> dict[str, Tensor]:
    return {key: value.detach().cpu() for key, value in model.state_dict().items()}


def save_checkpoint(
    path: Path | str,
    model: PADModel,
    spec: ExperimentSpec,
    threshold: ThresholdPolicy | None,
    protocol_hash: str,
    strategy_state: dict[str, Any],
) -> Path:
    """Save a state-dict plus JSON-compatible metadata checkpoint."""
    import torch

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {
        "spec": spec.model_dump(mode="json"),
        "threshold": threshold.model_dump(mode="json") if threshold is not None else None,
        "protocol_hash": protocol_hash,
        "science_hash": science_hash(spec),
        "spec_hash": spec_hash(spec),
        "git_sha": git_state(paths.repo_root()).sha,
        "strategy_state": strategy_state,
        "format_version": 1,
    }
    torch.save({"state_dict": _state_dict_cpu(model), "meta": meta}, out)
    return out


def load_checkpoint(path: Path | str) -> Checkpoint:
    """Load a checkpoint with ``weights_only=True`` and validate its metadata."""
    import torch

    src = Path(path)
    payload = torch.load(src, map_location="cpu", weights_only=True)
    if not isinstance(payload, dict):
        raise ValueError(f"checkpoint payload must be a dict, got {type(payload)!r}")
    state = payload.get("state_dict")
    meta = payload.get("meta")
    if not isinstance(state, dict) or not isinstance(meta, dict):
        raise ValueError("checkpoint must contain 'state_dict' and 'meta' dictionaries")
    if meta.get("format_version") != 1:
        raise ValueError(f"unsupported checkpoint format_version: {meta.get('format_version')!r}")
    spec = ExperimentSpec.model_validate(meta["spec"])
    threshold_payload = meta.get("threshold")
    threshold = (
        ThresholdPolicy.model_validate(threshold_payload) if threshold_payload is not None else None
    )
    strategy_state = meta.get("strategy_state", {})
    if not isinstance(strategy_state, dict):
        raise ValueError("checkpoint meta.strategy_state must be a dict")
    return Checkpoint(
        state_dict={str(key): value for key, value in state.items()},
        meta=meta,
        spec=spec,
        threshold=threshold,
        protocol_hash=str(meta["protocol_hash"]),
        science_hash=str(meta["science_hash"]),
        git_sha=meta.get("git_sha"),
        strategy_state=strategy_state,
    )
