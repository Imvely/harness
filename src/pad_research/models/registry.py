"""Model registry: build a :class:`PADModel` from a ``configs/model/*.yaml`` mapping."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pad_research.models.base import PADModel
from pad_research.models.frame.frame_baseline import TinyFrameBaseline
from pad_research.models.video.video_baseline import FrameEncoderTemporalTransformer

MODEL_FAMILIES: dict[str, type[PADModel]] = {
    "frame_baseline": TinyFrameBaseline,
    "video_baseline": FrameEncoderTemporalTransformer,
}


def build_model(model_cfg: Mapping[str, Any]) -> PADModel:
    """Instantiate ``model_cfg["net"]`` via Hydra and check it matches ``model_cfg["family"]``.

    ``hydra`` is imported lazily so validators can import the package without it.
    """
    from hydra.utils import instantiate

    net_cfg = model_cfg["net"]
    expected_family = model_cfg["family"]
    model = instantiate(net_cfg)
    if not isinstance(model, PADModel):
        raise TypeError(f"{net_cfg.get('_target_')!r} did not produce a PADModel: {type(model)!r}")
    if model.family != expected_family:
        raise ValueError(
            f"model family mismatch: config says {expected_family!r}, "
            f"instantiated {type(model).__name__} has family {model.family!r}"
        )
    return model
