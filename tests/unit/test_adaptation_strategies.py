"""Unit tests for adaptation strategies (freezing, parameter selection, loss, factory)."""

from __future__ import annotations

import copy

import pytest
import torch
import torch.nn.functional as F  # noqa: N812

from pad_research.adaptation.base import AdaptationStrategy
from pad_research.adaptation.strategies import (
    FullFinetune,
    HeadOnly,
    NoAdaptation,
    build_strategy,
)
from pad_research.models.frame.frame_baseline import TinyFrameBaseline
from pad_research.models.video.video_baseline import FrameEncoderTemporalTransformer

torch.set_num_threads(1)


def _step(model: TinyFrameBaseline, strategy: AdaptationStrategy) -> None:
    opt = torch.optim.SGD(strategy.trainable_parameters(model), lr=0.1)
    clip = torch.rand(2, 1, 3, 32, 32)
    labels = torch.tensor([0.0, 0.0])
    loss = strategy.loss(model(clip), labels)
    opt.zero_grad()
    loss.backward()
    opt.step()


def test_head_only_freezes_encoder() -> None:
    torch.manual_seed(0)
    model = TinyFrameBaseline()
    strategy = HeadOnly()
    strategy.prepare(model)
    assert all(not p.requires_grad for p in model.encoder_parameters())
    assert all(p.requires_grad for p in model.head_parameters())
    trainable = strategy.trainable_parameters(model)
    assert {id(p) for p in trainable} == {id(p) for p in model.head_parameters()}
    before_enc = copy.deepcopy(model.encoder.state_dict())
    before_head = copy.deepcopy(model.head.state_dict())
    _step(model, strategy)
    for key, value in model.encoder.state_dict().items():
        assert torch.equal(value, before_enc[key]), key
    assert any(
        not torch.equal(value, before_head[key]) for key, value in model.head.state_dict().items()
    )
    assert strategy.state() == {"name": "head_only"}


def test_head_only_video_model_freezes_temporal_transformer() -> None:
    model = FrameEncoderTemporalTransformer()
    HeadOnly().prepare(model)
    assert not model.pos_embedding.requires_grad
    assert all(not p.requires_grad for p in model.temporal.parameters())
    assert all(p.requires_grad for p in model.head.parameters())


def test_full_finetune_all_trainable() -> None:
    model = TinyFrameBaseline()
    HeadOnly().prepare(model)  # freeze first, FullFinetune must undo it
    strategy = FullFinetune()
    strategy.prepare(model)
    assert all(p.requires_grad for p in model.parameters())
    assert len(strategy.trainable_parameters(model)) == len(list(model.parameters()))
    assert strategy.name == "full_finetune"


def test_none_strategy_bce() -> None:
    torch.manual_seed(0)
    model = TinyFrameBaseline().eval()
    strategy = NoAdaptation()
    assert strategy.name == "none"
    clip = torch.rand(4, 1, 3, 32, 32)
    labels = torch.tensor([0.0, 1.0, 1.0, 0.0])
    out = model(clip)
    expected = F.binary_cross_entropy_with_logits(out.logits, labels)
    torch.testing.assert_close(strategy.loss(out, labels), expected)
    torch.testing.assert_close(strategy.score(out), torch.sigmoid(out.logits))


@pytest.mark.parametrize("method", ["prototype", "spoof_preserve"])
def test_prototype_raises_not_implemented(method: str) -> None:
    with pytest.raises(NotImplementedError, match="Phase"):
        build_strategy({"method": method, "enabled": True})


@pytest.mark.parametrize(
    ("method", "cls"),
    [("none", NoAdaptation), ("full_finetune", FullFinetune), ("head_only", HeadOnly)],
)
def test_build_strategy_maps_names(method: str, cls: type) -> None:
    strategy = build_strategy({"method": method})
    assert isinstance(strategy, cls)
    assert isinstance(strategy, AdaptationStrategy)
    assert strategy.name == method


def test_build_strategy_unknown_method() -> None:
    with pytest.raises(KeyError, match="unknown adaptation method"):
        build_strategy({"method": "does_not_exist"})
