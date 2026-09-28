"""Unit tests for the model layer (shape contract, parameter partition, registry)."""

from __future__ import annotations

from pathlib import Path

import pytest
import torch
import yaml

from pad_research.models.base import ModelOutput, PADModel
from pad_research.models.frame.frame_baseline import TinyFrameBaseline
from pad_research.models.registry import MODEL_FAMILIES, build_model
from pad_research.models.video.video_baseline import FrameEncoderTemporalTransformer
from pad_research.paths import configs_dir

torch.set_num_threads(1)


def _clip(batch: int, frames: int, size: int = 32) -> torch.Tensor:
    return torch.rand(batch, frames, 3, size, size)


def test_frame_baseline_forward_shape_T1() -> None:
    torch.manual_seed(0)
    model = TinyFrameBaseline(embed_dim=64, width=16)
    out = model(_clip(2, 1))
    assert isinstance(out, ModelOutput)
    assert out.logits.shape == (2,)
    assert out.clip_embedding.shape == (2, 64)
    assert out.frame_embeddings is not None
    assert out.frame_embeddings.shape == (2, 1, 64)


def test_frame_baseline_T8_mean_logits() -> None:
    torch.manual_seed(0)
    model = TinyFrameBaseline().eval()
    clip = _clip(2, 8)
    out = model(clip)
    with torch.no_grad():
        per_frame = torch.stack(
            [model.head(model.encoder(clip[:, t])) for t in range(8)], dim=1
        )  # (B, T)
        expected = per_frame.mean(dim=1)
    assert out.logits.shape == (2,)
    torch.testing.assert_close(out.logits, expected)
    assert out.frame_embeddings is not None
    torch.testing.assert_close(out.clip_embedding, out.frame_embeddings.mean(dim=1))


def test_video_baseline_shape() -> None:
    torch.manual_seed(0)
    model = FrameEncoderTemporalTransformer(embed_dim=64, width=16, depth=1, heads=4)
    out = model(_clip(3, 8))
    assert out.logits.shape == (3,)
    assert out.clip_embedding.shape == (3, 64)
    assert out.frame_embeddings is not None
    assert out.frame_embeddings.shape == (3, 8, 64)


@pytest.mark.parametrize("pooling", ["mean", "cls"])
def test_video_baseline_batch_independence(pooling: str) -> None:
    torch.manual_seed(0)
    model = FrameEncoderTemporalTransformer(pooling=pooling).eval()  # type: ignore[arg-type]
    clip = _clip(3, 8)
    with torch.no_grad():
        ref = model(clip).logits
        changed = clip.clone()
        changed[2] = torch.rand_like(changed[2])
        alt = model(changed).logits
    torch.testing.assert_close(alt[:2], ref[:2])
    assert not torch.allclose(alt[2], ref[2])


def test_frame_baseline_batch_size_one_train_mode() -> None:
    torch.manual_seed(0)
    model = TinyFrameBaseline().train()
    out = model(_clip(1, 1))
    assert out.logits.shape == (1,)
    out.logits.sum().backward()


def test_registry_instantiate_from_yaml() -> None:
    torch.manual_seed(0)
    model_dir = Path(configs_dir()) / "model"
    paths = sorted(model_dir.glob("*.yaml"))
    assert paths, f"no model configs in {model_dir}"
    for path in paths:
        cfg = yaml.safe_load(path.read_text())
        model = build_model(cfg)
        assert isinstance(model, PADModel)
        assert model.family == cfg["family"]
        assert isinstance(model, MODEL_FAMILIES[cfg["family"]])
        frames = int(cfg["input"]["frames"])
        h, w = cfg["input"]["image_size"]
        out = model(torch.rand(2, frames, 3, h, w))
        assert out.logits.shape == (2,)


def test_registry_rejects_family_mismatch() -> None:
    cfg = {
        "family": "video_baseline",
        "net": {"_target_": "pad_research.models.frame.frame_baseline.TinyFrameBaseline"},
    }
    with pytest.raises(ValueError, match="family mismatch"):
        build_model(cfg)


@pytest.mark.parametrize("factory", [TinyFrameBaseline, FrameEncoderTemporalTransformer])
def test_encoder_head_parameter_partition(factory: type[PADModel]) -> None:
    model = factory()
    enc = {id(p) for p in model.encoder_parameters()}
    head = {id(p) for p in model.head_parameters()}
    all_ids = {id(p) for p in model.parameters()}
    assert enc.isdisjoint(head)
    assert enc | head == all_ids
    assert head  # head is never empty


@pytest.mark.parametrize("factory", [TinyFrameBaseline, FrameEncoderTemporalTransformer])
def test_forward_is_deterministic_under_seed(factory: type[PADModel]) -> None:
    torch.manual_seed(1)
    model = factory().eval()
    clip = _clip(2, 4)
    with torch.no_grad():
        a = model(clip)
        b = model(clip)
    assert torch.equal(a.logits, b.logits)
    assert torch.equal(a.clip_embedding, b.clip_embedding)


def test_embed_matches_clip_embedding() -> None:
    torch.manual_seed(0)
    model = TinyFrameBaseline().eval()
    clip = _clip(2, 2)
    with torch.no_grad():
        torch.testing.assert_close(model.embed(clip), model(clip).clip_embedding)
