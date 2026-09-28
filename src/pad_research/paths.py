"""Repository path resolution.

All locations are functions (not module constants) so that tests can monkeypatch the
environment variables that override them (``PAD_REPO_ROOT``, ``PAD_DATA_ROOT``,
``PAD_REGISTRY_PATH``, ``PAD_OUTPUT_ROOT``, ``MLFLOW_TRACKING_URI``).
"""

from __future__ import annotations

import os
from pathlib import Path


class DataRootNotConfiguredError(RuntimeError):
    """Raised when the data root environment variable is not set."""


def repo_root() -> Path:
    """Return the repository root (``PAD_REPO_ROOT`` or two levels above the package)."""
    env = os.environ.get("PAD_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def configs_dir() -> Path:
    """Return the Hydra config directory."""
    return repo_root() / "configs"


def manifests_dir() -> Path:
    """Return the directory holding committed dataset manifests."""
    return repo_root() / "data" / "manifests"


def specs_dir() -> Path:
    """Return the directory holding frozen experiment specs."""
    return repo_root() / "experiments" / "specs"


def registry_path() -> Path:
    """Return the local run registry path (``PAD_REGISTRY_PATH`` overrides)."""
    env = os.environ.get("PAD_REGISTRY_PATH")
    if env:
        return Path(env).expanduser()
    return repo_root() / "experiments" / "registry.jsonl"


def approvals_dir() -> Path:
    """Return the directory holding human approval tokens for full runs."""
    return repo_root() / "experiments" / "approvals"


def output_root() -> Path:
    """Return the run output root (``PAD_OUTPUT_ROOT`` overrides)."""
    env = os.environ.get("PAD_OUTPUT_ROOT")
    if env:
        return Path(env).expanduser()
    return repo_root() / "outputs"


def data_root(root_env_var: str = "PAD_DATA_ROOT") -> Path:
    """Return the media root named by ``root_env_var``.

    The variable is mandatory: manifests store only paths relative to this root so that
    manifest hashes stay machine independent (research contract section 34).
    """
    env = os.environ.get(root_env_var)
    if not env:
        raise DataRootNotConfiguredError(
            f"environment variable {root_env_var} is not set; it must point to the directory "
            "that contains the media referenced by the dataset manifests"
        )
    return Path(env).expanduser()


def default_tracking_uri() -> str:
    """Return the MLflow tracking URI (``MLFLOW_TRACKING_URI`` or a local sqlite file)."""
    env = os.environ.get("MLFLOW_TRACKING_URI")
    if env:
        return env
    return f"sqlite:///{repo_root()}/mlruns.db"


def artifact_root() -> Path:
    """Return the local MLflow artifact root."""
    return repo_root() / "mlruns_artifacts"
