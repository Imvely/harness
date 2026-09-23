"""Seeding helpers. ``torch`` is imported lazily so validators stay torch free."""

from __future__ import annotations

import os
import random
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import torch


def seed_everything(seed: int, deterministic: bool = True) -> None:
    """Seed ``random``, ``numpy`` and ``torch`` (CPU and all CUDA devices).

    With ``deterministic=True`` also request deterministic algorithms (warn-only, so
    unsupported ops degrade to a warning instead of an error), disable cuDNN autotuning
    and set ``CUBLAS_WORKSPACE_CONFIG`` as required by the CUDA determinism docs.
    """
    import torch

    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    if deterministic:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.use_deterministic_algorithms(True, warn_only=True)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def make_generator(seed: int) -> torch.Generator:
    """Return a CPU ``torch.Generator`` seeded with ``seed`` (for samplers / DataLoader)."""
    import torch

    generator = torch.Generator()
    generator.manual_seed(seed)
    return generator


def worker_init_fn(worker_id: int) -> None:
    """DataLoader worker initializer deriving ``random``/``numpy`` seeds from torch's seed."""
    import torch

    worker_seed = (torch.initial_seed() + worker_id) % (2**32)
    random.seed(worker_seed)
    np.random.seed(worker_seed)
