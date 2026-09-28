"""Unit tests for the Phase 0 trainer, evaluator and checkpoint format."""

from __future__ import annotations

from pathlib import Path

import pytest
import torch

from pad_research.adaptation.strategies import NoAdaptation
from pad_research.config.compose import compose_spec
from pad_research.evaluation.evaluator import collect_scores, evaluate, measure_latency, roc_png
from pad_research.evaluation.scores import ScoreTable
from pad_research.experiments.status import RunStatus
from pad_research.metrics.threshold import ThresholdPolicy
from pad_research.models.registry import build_model
from pad_research.protocols.validator import validate_protocol
from pad_research.training.checkpoint import load_checkpoint, save_checkpoint
from pad_research.training.trainer import Trainer

ROOT = Path(__file__).resolve().parents[2]


def _spec():
    _, spec = compose_spec(["+exp=syn_e01_frame_source_only"])
    return spec


def _batch():
    return {
        "clip": torch.rand(4, 1, 3, 32, 32),
        "label": torch.tensor([0, 0, 1, 1], dtype=torch.long),
        "pai": ["none", "none", "print", "replay_phone"],
        "sample_id": ["b0", "b1", "a0", "a1"],
        "subject_id": ["s0", "s1", "s2", "s3"],
    }


def _fitted_threshold() -> ThresholdPolicy:
    dev = ScoreTable.from_arrays(
        "dev",
        "source",
        ["b0", "b1", "a0", "a1"],
        ["s0", "s1", "s2", "s3"],
        [0.1, 0.2, 0.8, 0.9],
        [False, False, True, True],
        ["none", "none", "print", "replay_phone"],
    )
    return ThresholdPolicy(spec=_spec().protocol.threshold).fit(dev)


def test_trainer_obeys_smoke_limits(torch_single_thread) -> None:
    spec = _spec()
    model = build_model(spec.model.model_dump(mode="python"))
    strategy = NoAdaptation()
    result = Trainer(
        model,
        strategy,
        {"train": [_batch(), _batch()]},
        spec,
        tracker=None,
        limits=spec.execution.smoke,
        device=torch.device("cpu"),
    ).fit()
    assert result.epochs_run == 1
    assert result.steps == spec.execution.smoke.max_batches
    assert result.train_curve[0]["steps"] == spec.execution.smoke.max_batches


def test_collect_scores_and_evaluate_result(torch_single_thread, tmp_path: Path) -> None:
    spec = _spec()
    pv = validate_protocol(spec.protocol, ROOT / spec.data.manifests_dir, frames=1)
    assert pv.ok
    model = build_model(spec.model.model_dump(mode="python"))
    strategy = NoAdaptation()
    table = collect_scores(
        model,
        strategy,
        [_batch()],
        torch.device("cpu"),
        max_batches=None,
        role="test",
        domain="target",
    )
    threshold = _fitted_threshold()
    result = evaluate(table, threshold, spec, pv, status=RunStatus.smoke_ok)
    assert result.n_test == 4
    assert result.metrics.tau == pytest.approx(threshold.tau)
    latency = measure_latency(model, (1, 3, 32, 32), torch.device("cpu"), 0, 1, 1, smoke=True)
    assert latency.smoke is True
    assert latency.ms_per_clip >= 0.0
    assert roc_png(table, tmp_path / "roc.png").is_file()


def test_checkpoint_uses_weights_only_compatible_payload(
    torch_single_thread, tmp_path: Path
) -> None:
    spec = _spec()
    model = build_model(spec.model.model_dump(mode="python"))
    threshold = _fitted_threshold()
    path = save_checkpoint(
        tmp_path / "checkpoint.pt",
        model,
        spec,
        threshold,
        "p" * 64,
        {"name": "none"},
    )
    raw = torch.load(path, map_location="cpu", weights_only=True)
    assert set(raw) == {"state_dict", "meta"}
    assert isinstance(raw["meta"]["spec"], dict)
    loaded = load_checkpoint(path)
    assert loaded.protocol_hash == "p" * 64
    assert loaded.threshold is not None
    assert loaded.threshold.tau == pytest.approx(threshold.tau)
