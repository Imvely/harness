"""Dataset adapter interface and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pad_research.data.manifest import ManifestRecord


class DatasetAdapter(ABC):
    """Turns a dataset on disk (or a generator) into a list of :class:`ManifestRecord`.

    Subclasses set the class attributes and implement :meth:`build`. ``build`` may write
    media under ``root/<dataset_id>/`` (the synthetic adapter does); real-dataset adapters
    only read the data root and never copy face data anywhere (contract section 34).
    """

    adapter_name: str = "base"
    dataset_id: str
    version: str
    license: str
    pii_policy: str
    temporal_valid: bool = True

    @abstractmethod
    def build(self, root: Path) -> list[ManifestRecord]:
        """Return the records for this dataset with paths relative to ``root``."""

    def meta_partial(self) -> dict[str, Any]:
        """Adapter-owned part of :class:`~pad_research.data.manifest.ManifestMeta`."""
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "adapter": self.adapter_name,
            "license": self.license,
            "pii_policy": self.pii_policy,
            "temporal_valid": self.temporal_valid,
        }


def _make_synthetic(**kwargs: Any) -> DatasetAdapter:
    from pad_research.data.adapters.synthetic import SyntheticAdapter

    return SyntheticAdapter(**kwargs)


#: Registered adapter factories keyed by CLI name. Real datasets are added here in Phase 1.
ADAPTERS: dict[str, Callable[..., DatasetAdapter]] = {"synthetic": _make_synthetic}


def get_adapter(name: str, **kwargs: Any) -> DatasetAdapter:
    """Instantiate the adapter registered under ``name`` with ``kwargs``."""
    try:
        factory = ADAPTERS[name]
    except KeyError:
        raise KeyError(f"unknown adapter {name!r}; known: {sorted(ADAPTERS)}") from None
    return factory(**kwargs)
