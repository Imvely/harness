"""Toy-vector tests for pad_research.metrics.pad_metrics (contract §14)."""

from __future__ import annotations

import numpy as np
import pytest

from pad_research import conventions
from pad_research.metrics.pad_metrics import (
    EmptyPAIError,
    acer,
    apcer_max,
    apcer_per_pai,
    apcer_pooled,
    bpcer,
    bpcer_at_apcer,
    compute_pad_metrics,
    eer_threshold,
    hter,
    roc_auc,
)

ABS = 1e-12
TAU = 0.5
BONA = [0.1, 0.2, 0.3, 0.7]
PRINT = [0.9, 0.8, 0.4, 0.6]
REPLAY = [0.3, 0.2, 0.9, 0.95, 0.1]


def toy() -> tuple[np.ndarray, np.ndarray, list[str]]:
    score = np.array(BONA + PRINT + REPLAY)
    y = np.array([False] * 4 + [True] * 9)
    pai = ["none"] * 4 + ["print"] * 4 + ["replay_phone"] * 5
    return score, y, pai


def test_bpcer_toy() -> None:
    s, y, _ = toy()
    assert bpcer(s, y, TAU) == pytest.approx(0.25, abs=ABS)


def test_apcer_per_pai_toy() -> None:
    s, y, pai = toy()
    per = apcer_per_pai(s, y, pai, TAU)
    assert set(per) == {"print", "replay_phone"}
    assert per["print"] == pytest.approx(0.25, abs=ABS)
    assert per["replay_phone"] == pytest.approx(0.6, abs=ABS)


def test_apcer_max_toy() -> None:
    s, y, pai = toy()
    assert apcer_max(apcer_per_pai(s, y, pai, TAU)) == pytest.approx(0.6, abs=ABS)


def test_apcer_pooled_toy() -> None:
    s, y, _ = toy()
    assert apcer_pooled(s, y, TAU) == pytest.approx(4 / 9, abs=ABS)


def test_acer_iso_max_pai() -> None:
    s, y, pai = toy()
    a = apcer_max(apcer_per_pai(s, y, pai, TAU))
    assert acer(a, bpcer(s, y, TAU)) == pytest.approx(0.425, abs=ABS)


def test_hter_pooled() -> None:
    s, y, _ = toy()
    assert hter(apcer_pooled(s, y, TAU), bpcer(s, y, TAU)) == pytest.approx(
        (4 / 9 + 0.25) / 2, abs=ABS
    )


def test_acer_max_pai_vs_hter_pooled_differ() -> None:
    s, y, pai = toy()
    b = bpcer(s, y, TAU)
    a_iso = acer(apcer_max(apcer_per_pai(s, y, pai, TAU)), b)
    h = hter(apcer_pooled(s, y, TAU), b)
    assert a_iso == pytest.approx(0.425, abs=ABS)
    assert h == pytest.approx(0.3472222222222222, abs=1e-9)
    assert abs(a_iso - h) > 0.05


def test_bpcer_boundary_score_equal_threshold_is_spoof() -> None:
    assert bpcer(np.array([0.5]), np.array([False]), 0.5) == pytest.approx(1.0, abs=ABS)
    # attack exactly at tau is correctly rejected (not an APCER error)
    assert apcer_pooled(np.array([0.5]), np.array([True]), 0.5) == pytest.approx(0.0, abs=ABS)


def test_eer_threshold_separable() -> None:
    dev_s = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    dev_y = np.array([False] * 4 + [True] * 4)
    tau, eer = eer_threshold(dev_s, dev_y)
    assert tau == pytest.approx(0.6, abs=ABS)
    assert eer == pytest.approx(0.0, abs=ABS)
    test_s = np.array([0.1, 0.5, 0.65, 0.2, 0.55, 0.7, 0.9, 0.61])
    test_y = np.array([False] * 4 + [True] * 4)
    assert bpcer(test_s, test_y, tau) == pytest.approx(0.25, abs=ABS)
    assert apcer_pooled(test_s, test_y, tau) == pytest.approx(0.25, abs=ABS)
    assert hter(apcer_pooled(test_s, test_y, tau), bpcer(test_s, test_y, tau)) == pytest.approx(
        0.25, abs=ABS
    )


def test_eer_threshold_overlap() -> None:
    dev_s = np.array([0.2, 0.4, 0.6, 0.8, 0.3, 0.5, 0.7, 0.9])
    dev_y = np.array([False] * 4 + [True] * 4)
    tau, eer = eer_threshold(dev_s, dev_y)
    assert tau == pytest.approx(0.6, abs=ABS)
    assert eer == pytest.approx(0.5, abs=ABS)


def test_auc_perfect() -> None:
    s = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    y = np.array([False] * 4 + [True] * 4)
    assert roc_auc(s, y) == pytest.approx(1.0, abs=ABS)


def test_auc_partial() -> None:
    s = np.array([0.1, 0.5, 0.6, 0.7, 0.2, 0.3, 0.8, 0.9])
    y = np.array([False] * 4 + [True] * 4)
    assert roc_auc(s, y) == pytest.approx(0.625, abs=ABS)


def test_auc_ties_half() -> None:
    s = np.full(8, 0.42)
    y = np.array([False] * 4 + [True] * 4)
    assert roc_auc(s, y) == pytest.approx(0.5, abs=ABS)


def test_empty_pai_raises() -> None:
    s = np.array([0.1, 0.2])
    y = np.array([False, False])
    with pytest.raises(EmptyPAIError):
        apcer_per_pai(s, y, ["none", "none"], TAU)
    with pytest.raises(EmptyPAIError):
        apcer_pooled(s, y, TAU)
    with pytest.raises(EmptyPAIError):
        apcer_max({})


def test_apcer_per_pai_omits_pai_without_attacks() -> None:
    s, y, pai = toy()
    pai = list(pai)
    pai[0] = "mask_3d"  # a bona-fide row labelled with a PAI name must not create a key
    per = apcer_per_pai(s, y, pai, TAU)
    assert "mask_3d" not in per
    assert "none" not in per


def test_label_convention_spoof_is_one() -> None:
    assert conventions.LABEL_SPOOF == 1
    assert conventions.LABEL_BONA_FIDE == 0
    assert conventions.decide_spoof(np.array([0.5, 0.49]), 0.5).tolist() == [True, False]


def test_bpcer_at_apcer_rule() -> None:
    # bona [0.1, 0.2, 0.3, 0.7], attack [0.3, 0.5, 0.9]
    # candidates (unique scores + inf): 0.1 0.2 0.3 0.5 0.7 0.9 inf
    # APCER(t)=mean(attack<t):  0   0   0   1/3 2/3 2/3 1
    # BPCER(t)=mean(bona>=t):   1  3/4 2/4 1/4 1/4  0   0
    s = np.array([0.1, 0.2, 0.3, 0.7, 0.3, 0.5, 0.9])
    y = np.array([False] * 4 + [True] * 3)
    # target 0: feasible {0.1,0.2,0.3}; lowest BPCER -> tau 0.3, BPCER 0.5
    tau, b = bpcer_at_apcer(s, y, 0.0)
    assert tau == pytest.approx(0.3, abs=ABS)
    assert b == pytest.approx(0.5, abs=ABS)
    # target 1/3: feasible up to 0.5 -> tau 0.5, BPCER 0.25
    tau, b = bpcer_at_apcer(s, y, 1 / 3)
    assert tau == pytest.approx(0.5, abs=ABS)
    assert b == pytest.approx(0.25, abs=ABS)
    # target 2/3: feasible {..., 0.7, 0.9}; 0.9 has lowest BPCER (0.0)
    tau, b = bpcer_at_apcer(s, y, 2 / 3)
    assert tau == pytest.approx(0.9, abs=ABS)
    assert b == pytest.approx(0.0, abs=ABS)
    # tie in BPCER -> smallest tau (lowest APCER): bona [0.1], attack [0.3, 0.5]; target 1
    # candidates 0.1 0.3 0.5 inf: APCER 0 0 .5 1; BPCER 1 0 0 0 -> tau 0.3
    tau, b = bpcer_at_apcer(np.array([0.1, 0.3, 0.5]), np.array([False, True, True]), 1.0)
    assert tau == pytest.approx(0.3, abs=ABS)
    assert b == pytest.approx(0.0, abs=ABS)
    # the chosen operating point really satisfies APCER <= target on the dev data
    tau, _ = bpcer_at_apcer(s, y, 0.1)
    assert apcer_pooled(s, y, tau) <= 0.1


def test_compute_pad_metrics_policy_pooled_vs_max() -> None:
    s, y, pai = toy()
    m_max = compute_pad_metrics(s, y, pai, TAU, acer_policy="max_pai")
    m_pool = compute_pad_metrics(s, y, pai, TAU, acer_policy="pooled")
    assert m_max.acer_policy == "max_pai"
    assert m_pool.acer_policy == "pooled"
    assert m_max.apcer == pytest.approx(0.6, abs=ABS)
    assert m_pool.apcer == pytest.approx(4 / 9, abs=ABS)
    assert m_max.acer == pytest.approx(0.425, abs=ABS)
    assert m_pool.acer == pytest.approx((4 / 9 + 0.25) / 2, abs=ABS)
    # hter is pooled regardless of policy; the other fields are identical
    assert m_max.hter == m_pool.hter == pytest.approx((4 / 9 + 0.25) / 2, abs=ABS)
    assert m_max.apcer_max == m_pool.apcer_max == pytest.approx(0.6, abs=ABS)
    assert m_max.apcer_pooled == m_pool.apcer_pooled == pytest.approx(4 / 9, abs=ABS)
    assert m_max.bpcer == pytest.approx(0.25, abs=ABS)
    assert m_max.tau == TAU
    assert m_max.n_bona_fide == 4
    assert m_max.n_attack_per_pai == {"print": 4, "replay_phone": 5}
    assert m_max.apcer_per_pai == {"print": pytest.approx(0.25), "replay_phone": pytest.approx(0.6)}
    assert 0.0 <= m_max.auc <= 1.0
    assert m_max.bpcer_at_apcer_10 is None
    assert m_max.bpcer_at_apcer_1 is None
    with pytest.raises(ValueError):
        compute_pad_metrics(s, y, pai, TAU, acer_policy="mean")  # type: ignore[arg-type]
