"""ThresholdPolicy: dev-only fitting, fixed-after-dev application."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from pad_research.evaluation.scores import ScoreTable
from pad_research.metrics.threshold import (
    NotFittedError,
    ThresholdLeakageError,
    ThresholdPolicy,
    ThresholdSpec,
)


def _table(role: str, domain: str = "source") -> ScoreTable:
    score = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    y = np.array([False] * 4 + [True] * 4)
    pai = ["none"] * 4 + ["print", "print", "replay_phone", "replay_phone"]
    ids = [f"s{i}" for i in range(8)]
    return ScoreTable.from_arrays(role, domain, ids, ids, score, y, pai)  # type: ignore[arg-type]


def test_threshold_fit_on_test_raises() -> None:
    policy = ThresholdPolicy(spec=ThresholdSpec())
    with pytest.raises(ThresholdLeakageError):
        policy.fit(_table("test"))
    with pytest.raises(ThresholdLeakageError):
        policy.fit(_table("adapt"))
    assert policy.tau is None  # untouched


def test_apply_before_fit_raises() -> None:
    policy = ThresholdPolicy(spec=ThresholdSpec())
    assert not policy.is_fitted
    with pytest.raises(NotFittedError):
        policy.apply(np.array([0.5]))


def test_fit_records_dev_stats() -> None:
    policy = ThresholdPolicy(spec=ThresholdSpec(rule="eer"))
    fitted = policy.fit(_table("dev", "target"))
    assert fitted is not policy
    assert policy.tau is None
    assert fitted.tau == pytest.approx(0.6, abs=1e-12)
    assert fitted.dev_eer == pytest.approx(0.0, abs=1e-12)
    assert fitted.fitted_on == "target/dev"
    assert fitted.dev_n_bona_fide == 4
    assert fitted.dev_n_attack == 4
    assert fitted.spec == policy.spec
    decisions = fitted.apply(np.array([0.59, 0.6, 0.61]))
    assert decisions.dtype == np.bool_
    assert decisions.tolist() == [False, True, True]


def test_fit_bpcer_at_apcer_rule() -> None:
    policy = ThresholdPolicy(spec=ThresholdSpec(rule="bpcer_at_apcer", rule_param=0.1))
    fitted = policy.fit(_table("dev"))
    assert fitted.tau == pytest.approx(0.6, abs=1e-12)
    assert fitted.dev_eer is None
    assert fitted.fitted_on == "source/dev"


def test_bpcer_at_apcer_rule_requires_param() -> None:
    with pytest.raises(ValidationError):
        ThresholdSpec(rule="bpcer_at_apcer")
    with pytest.raises(ValidationError):
        ThresholdSpec(rule="bpcer_at_apcer", rule_param=0.0)
    with pytest.raises(ValidationError):
        ThresholdSpec(rule="bpcer_at_apcer", rule_param=1.5)
    spec = ThresholdSpec(rule="bpcer_at_apcer", rule_param=0.1)
    assert spec.rule_param == 0.1
    assert ThresholdSpec().rule == "eer"
