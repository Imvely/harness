"""Environment snapshot recorded with every run (contract §17).

Collected once per run and stored both as MLflow tags (subset) and as the
``env_snapshot.json`` artifact. torch is imported lazily so validators stay light.
"""

from __future__ import annotations

import datetime as _dt
import platform
import shutil
import socket
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pad_research.utils.git import git_state
from pad_research.utils.hashing import sha256_file


class EnvSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp_utc: str
    hostname: str
    platform: str
    python_version: str
    cpu_count: int
    git_sha: str | None
    git_dirty: bool
    git_branch: str | None
    untracked_count: int
    torch_version: str | None
    torch_build: str | None  # "cpu" | "cu130" | ... derived from torch.version.cuda
    cuda_available: bool
    cuda_version: str | None
    cudnn_version: int | None
    gpu_count: int
    gpu_names: list[str]
    driver_version: str | None
    lock_hash: str | None
    pad_research_version: str
    deterministic_algorithms: bool

    def as_tags(self) -> dict[str, str]:
        """Subset of fields suitable as MLflow tags (all strings)."""
        return {
            "git_sha": self.git_sha or "unknown",
            "git_dirty": str(self.git_dirty).lower(),
            "git_branch": self.git_branch or "unknown",
            "lock_hash": (self.lock_hash or "unknown")[:12],
            "torch_build": self.torch_build or "none",
        }


def _driver_version() -> str | None:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    line = out.stdout.strip().splitlines()
    return line[0].strip() if out.returncode == 0 and line else None


def _package_version() -> str:
    try:
        return metadata.version("pad-research")
    except metadata.PackageNotFoundError:
        return "0.0.0+uninstalled"


def collect_env_snapshot(repo_root: Path, *, with_torch: bool = True) -> EnvSnapshot:
    """Collect the reproducibility metadata for ``repo_root``.

    ``with_torch=False`` skips the torch import (used by validators and hooks).
    """
    gs = git_state(repo_root)
    lock = repo_root / "uv.lock"
    torch_version = torch_build = cuda_version = None
    cudnn_version = None
    cuda_available = False
    gpu_names: list[str] = []
    deterministic = False
    if with_torch:
        import torch

        torch_version = torch.__version__
        cuda_version = torch.version.cuda
        torch_build = f"cu{cuda_version.replace('.', '')}" if cuda_version else "cpu"
        cuda_available = bool(torch.cuda.is_available())
        if cuda_available:
            gpu_names = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
            cudnn_version = torch.backends.cudnn.version()
        deterministic = bool(torch.are_deterministic_algorithms_enabled())
    return EnvSnapshot(
        timestamp_utc=_dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds"),
        hostname=socket.gethostname(),
        platform=platform.platform(),
        python_version=sys.version.split()[0],
        cpu_count=__import__("os").cpu_count() or 1,
        git_sha=gs.sha,
        git_dirty=gs.dirty,
        git_branch=gs.branch,
        untracked_count=gs.untracked_count,
        torch_version=torch_version,
        torch_build=torch_build,
        cuda_available=cuda_available,
        cuda_version=cuda_version,
        cudnn_version=cudnn_version,
        gpu_count=len(gpu_names),
        gpu_names=gpu_names,
        driver_version=_driver_version() if cuda_available else None,
        lock_hash=sha256_file(lock) if lock.exists() else None,
        pad_research_version=_package_version(),
        deterministic_algorithms=deterministic,
    )
