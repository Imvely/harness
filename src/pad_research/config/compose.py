"""Hydra <-> ExperimentSpec bridge (compose API for validators/tests, cfg for @hydra.main)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hydra import compose, initialize_config_dir
from hydra.core.global_hydra import GlobalHydra
from omegaconf import DictConfig, OmegaConf

from pad_research import paths
from pad_research.config.schema import ExperimentSpec

_EXCLUDED_TOP_LEVEL = {"hydra"}


def cfg_to_spec_dict(cfg: DictConfig) -> dict[str, Any]:
    raw = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
    if not isinstance(raw, dict):
        raise TypeError("composed config must be a mapping")
    return {str(k): v for k, v in raw.items() if str(k) not in _EXCLUDED_TOP_LEVEL}


def spec_from_cfg(cfg: DictConfig) -> ExperimentSpec:
    return ExperimentSpec.model_validate(cfg_to_spec_dict(cfg))


def compose_spec(
    overrides: list[str],
    *,
    config_name: str = "config",
    config_dir: Path | None = None,
    extra_config_dir: Path | None = None,
) -> tuple[DictConfig, ExperimentSpec]:
    """Compose ``configs/`` (+ optional extra search path) with ``overrides`` and validate."""
    base = (config_dir or paths.configs_dir()).resolve()
    ov = list(overrides)
    if extra_config_dir is not None:
        ov.append(f"hydra.searchpath=[file://{extra_config_dir.resolve()}]")
    GlobalHydra.instance().clear()
    with initialize_config_dir(version_base="1.3", config_dir=str(base)):
        cfg = compose(config_name=config_name, overrides=ov)
    return cfg, spec_from_cfg(cfg)


def task_overrides() -> list[str]:
    """Command-line overrides of the current ``@hydra.main`` process ([] outside)."""
    from hydra.core.hydra_config import HydraConfig

    try:
        return list(HydraConfig.get().overrides.task)
    except ValueError:
        return []


def config_sources() -> list[str]:
    """``file://`` config sources of the current ``@hydra.main`` process ([] outside)."""
    from hydra.core.hydra_config import HydraConfig

    try:
        srcs = HydraConfig.get().runtime.config_sources
    except ValueError:
        return []
    return [str(s.path) for s in srcs if str(s.schema) == "file"]


def exp_name_from_overrides(overrides: list[str]) -> str | None:
    for tok in overrides:
        t = tok.lstrip("+~")
        if t.startswith("exp="):
            return t.split("=", 1)[1].strip("'\"")
    return None
