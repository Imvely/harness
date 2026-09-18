from __future__ import annotations

from pathlib import Path

import pytest

from pad_research.tracking.env_snapshot import EnvSnapshot, collect_env_snapshot
from pad_research.tracking.tags import (
    REQUIRED_METRICS,
    REQUIRED_TAGS,
    metric_key_for_pai,
    validate_key,
)
from pad_research.utils.hashing import sha256_file


def test_snapshot_fields_present(repo_root: Path) -> None:
    snap = collect_env_snapshot(repo_root, with_torch=False)
    assert snap.python_version.startswith("3.")
    assert snap.git_sha is not None and len(snap.git_sha) == 40
    assert snap.torch_version is None and snap.cuda_available is False
    assert set(snap.as_tags()) == {"git_sha", "git_dirty", "git_branch", "lock_hash", "torch_build"}


def test_lock_hash_matches_file(repo_root: Path) -> None:
    snap = collect_env_snapshot(repo_root, with_torch=False)
    assert snap.lock_hash == sha256_file(repo_root / "uv.lock")


def test_snapshot_is_consistent_with_installed_torch(repo_root: Path) -> None:
    """Environment-agnostic: holds on the CPU sandbox and on the H100 server alike."""
    torch = pytest.importorskip("torch")
    snap = collect_env_snapshot(repo_root, with_torch=True)
    assert snap.torch_version == torch.__version__
    assert snap.cuda_available == torch.cuda.is_available()
    assert snap.gpu_count == len(snap.gpu_names)
    assert (snap.driver_version is None) == (not snap.cuda_available) or snap.cuda_available
    expected_build = f"cu{torch.version.cuda.replace('.', '')}" if torch.version.cuda else "cpu"
    assert snap.torch_build == expected_build
    assert EnvSnapshot.model_validate(snap.model_dump()) == snap


def test_required_tag_and_metric_names_are_valid_keys() -> None:
    for name in REQUIRED_TAGS + REQUIRED_METRICS:
        assert validate_key(name) == name
    assert metric_key_for_pai("replay_phone") == "apcer_replay_phone"
    with pytest.raises(ValueError):
        validate_key("bad key!")
