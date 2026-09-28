"""Load a :class:`ProtocolSpec` from ``configs/protocol/<name>.yaml`` or an explicit path."""

from __future__ import annotations

from pathlib import Path

import yaml

from pad_research import paths
from pad_research.protocols.schema import ProtocolSpec

_YAML_SUFFIXES = (".yaml", ".yml")


class ProtocolNotFoundError(FileNotFoundError):
    """No protocol YAML exists for the requested name or path."""


def resolve_protocol_path(name_or_path: str | Path, configs_dir: Path | None = None) -> Path:
    """Map a bare protocol name to ``<configs_dir>/protocol/<name>.yaml``; pass paths through."""
    candidate = Path(name_or_path)
    looks_like_path = (
        candidate.suffix.lower() in _YAML_SUFFIXES or len(candidate.parts) > 1 or candidate.exists()
    )
    if looks_like_path:
        return candidate
    base = configs_dir if configs_dir is not None else paths.configs_dir()
    return base / "protocol" / f"{candidate.name}.yaml"


def load_protocol(name_or_path: str | Path, configs_dir: Path | None = None) -> ProtocolSpec:
    """Parse and validate a protocol YAML.

    ``pydantic.ValidationError`` propagates unchanged so callers can map it to a schema
    error; a missing file raises :class:`ProtocolNotFoundError`.
    """
    path = resolve_protocol_path(name_or_path, configs_dir)
    if not path.is_file():
        raise ProtocolNotFoundError(f"protocol file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"protocol file {path} must contain a YAML mapping")
    return ProtocolSpec.model_validate(raw)
