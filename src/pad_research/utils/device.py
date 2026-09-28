"""Device resolution. ``torch`` is imported lazily so validators stay torch free."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import torch

DeviceRequest = Literal["auto", "cpu", "cuda"]


def resolve_device(requested: DeviceRequest = "auto") -> torch.device:
    """Resolve ``requested`` to a concrete ``torch.device``.

    ``"auto"`` picks CUDA when available and CPU otherwise; ``"cuda"`` raises when no CUDA
    device is present instead of silently falling back (a silent fallback would invalidate
    timing and reproducibility records).
    """
    import torch

    if requested == "cpu":
        return torch.device("cpu")
    cuda_ok = torch.cuda.is_available()
    if requested == "cuda":
        if not cuda_ok:
            raise RuntimeError("device 'cuda' requested but torch.cuda.is_available() is False")
        return torch.device("cuda")
    if requested == "auto":
        return torch.device("cuda" if cuda_ok else "cpu")
    raise ValueError(f"unknown device request {requested!r}; expected 'auto', 'cpu' or 'cuda'")
