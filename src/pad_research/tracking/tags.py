"""MLflow tag / metric name registry (contract §21).

Every run MUST carry ``REQUIRED_TAGS`` and log ``REQUIRED_METRICS``; the tracker raises
``ValueError`` otherwise. Names follow MLflow's key rules (alphanumerics, ``_ - . / :``,
at most 250 characters).
"""

from __future__ import annotations

import re
from typing import Final

REQUIRED_TAGS: Final[tuple[str, ...]] = (
    "research_question",
    "protocol_id",
    "protocol_hash",
    "model_family",
    "adaptation_method",
    "target_supervision",
    "dataset_manifest_hash",
    "git_sha",
    "status",
)

EXTRA_TAGS: Final[tuple[str, ...]] = (
    "experiment_id",
    "science_hash",
    "spec_hash",
    "execution_mode",
    "seed",
    "git_dirty",
    "git_branch",
    "lock_hash",
    "torch_build",
    "parent_experiment_id",
    "baseline_experiment_id",
    "adaptation_set_hash",
    "threshold_source",
    "threshold_rule",
    "research_claim_allowed",
    "checkpoint_source",
    "model_init",
    "gate_verdict",
    "approved_by",
    "remote_artifacts",
)

REQUIRED_METRICS: Final[tuple[str, ...]] = ("apcer", "bpcer", "acer", "hter", "auc")

# Tag value domains (documented so reports can rely on them).
MODEL_INIT_VALUES: Final[tuple[str, ...]] = ("random", "checkpoint")
CHECKPOINT_SOURCE_NONE: Final[str] = (
    "none"  # else "mlflow:<run_id>/checkpoint.pt" or "file:<relative path>"
)

_KEY_RE = re.compile(r"^[/\w.\- :]{1,250}$")


def validate_key(name: str) -> str:
    """Return ``name`` if it is a valid MLflow metric/tag/param key, else raise ValueError."""
    if not _KEY_RE.match(name):
        raise ValueError(
            f"invalid MLflow key {name!r}: only alphanumerics, '_', '-', '.', ' ', ':' and '/'"
            " are allowed (max 250 chars)"
        )
    return name


def metric_key_for_pai(pai: str) -> str:
    """Metric name for a per-PAI APCER, e.g. ``apcer_replay_phone``."""
    return validate_key(f"apcer_{pai}")
