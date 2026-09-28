"""Tests for the shared train/adapt/evaluate runtime helpers."""

from __future__ import annotations

from pathlib import Path

from pad_research.config.compose import compose_spec
from pad_research.training.pipeline import effective_limits, eval_loader_budget

ROOT = Path(__file__).resolve().parents[2]


def _spec(*overrides: str):
    _, spec = compose_spec(
        ["+exp=syn_e02_video_source_only", *overrides], config_dir=ROOT / "configs"
    )
    return spec


def test_effective_limits_only_apply_to_smoke_mode() -> None:
    assert effective_limits(_spec()) is not None
    full = _spec("execution.mode=full", "execution.allow_full_gpu_run=true")
    assert effective_limits(full) is None


def test_full_mode_evaluation_is_unbounded_at_the_configured_batch_size() -> None:
    spec = _spec("execution.mode=full", "execution.allow_full_gpu_run=true")
    batch_size, max_batches = eval_loader_budget(spec, effective_limits(spec))
    assert batch_size == spec.training.batch_size
    assert max_batches is None


def test_smoke_evaluation_budget_is_linear_in_max_eval_batches() -> None:
    # Widening the batch by max_eval_batches while also capping the batch count made the
    # budget quadratic, so a smoke evaluation could read a full split's worth of samples.
    spec = _spec()
    limits = effective_limits(spec)
    assert limits is not None
    batch_size, max_batches = eval_loader_budget(spec, limits)
    assert batch_size == spec.training.batch_size
    assert max_batches == limits.max_eval_batches
    assert batch_size * max_batches == spec.training.batch_size * limits.max_eval_batches
