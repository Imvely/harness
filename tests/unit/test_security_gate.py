"""Security regression gate (contract §14.3)."""

from __future__ import annotations

import pytest

from pad_research.errors import ProtocolMismatchError
from pad_research.metrics.pad_metrics import PadMetrics
from pad_research.metrics.security_gate import SecurityGateConfig, run_security_gate

HASH_A = "a" * 64
HASH_B = "b" * 64


def _metrics(per_pai: dict[str, float], bpcer: float, auc: float, n: int = 50) -> PadMetrics:
    a_max = max(per_pai.values())
    pooled = sum(per_pai.values()) / len(per_pai)
    return PadMetrics(
        tau=0.5,
        apcer_per_pai=per_pai,
        apcer_max=a_max,
        apcer_pooled=pooled,
        apcer=a_max,
        bpcer=bpcer,
        acer=(a_max + bpcer) / 2,
        hter=(pooled + bpcer) / 2,
        auc=auc,
        acer_policy="max_pai",
        n_bona_fide=100,
        n_attack_per_pai=dict.fromkeys(per_pai, n),
    )


def before(n: int = 50) -> PadMetrics:
    return _metrics({"print": 0.02, "replay_phone": 0.02}, bpcer=0.08, auc=0.95, n=n)


def after(replay: float = 0.15, n: int = 50, auc: float = 0.97) -> PadMetrics:
    return _metrics({"print": 0.02, "replay_phone": replay}, bpcer=0.02, auc=auc, n=n)


def test_gate_detects_replay_regression() -> None:
    res = run_security_gate(before(), after(), HASH_A, HASH_A, SecurityGateConfig())
    assert res.verdict == "security_regression"
    by_pai = {d.pai: d for d in res.per_pai}
    assert by_pai["replay_phone"].delta == pytest.approx(0.13, abs=1e-12)
    assert by_pai["replay_phone"].regressed is True
    assert by_pai["replay_phone"].n_attack == 50
    assert by_pai["print"].regressed is False
    assert res.bpcer_improved is True
    assert res.bpcer_delta == pytest.approx(-0.06, abs=1e-12)
    assert res.protocol_hash == HASH_A
    assert "replay_phone" in res.note and "0.02 -> 0.15" in res.note


def test_gate_within_tolerance_passes() -> None:
    res = run_security_gate(
        before(), after(replay=0.025), HASH_A, HASH_A, SecurityGateConfig(abs_tolerance=0.01)
    )
    assert res.verdict == "pass"
    assert all(not d.regressed for d in res.per_pai)


def test_gate_exact_tolerance_passes() -> None:
    res = run_security_gate(
        before(), after(replay=0.03), HASH_A, HASH_A, SecurityGateConfig(abs_tolerance=0.01)
    )
    assert res.verdict == "pass"
    res = run_security_gate(
        before(), after(replay=0.03 + 1e-6), HASH_A, HASH_A, SecurityGateConfig(abs_tolerance=0.01)
    )
    assert res.verdict == "security_regression"


def test_gate_relative_tolerance() -> None:
    cfg = SecurityGateConfig(abs_tolerance=0.0, rel_tolerance=1.0)  # tol = apcer_before = .02
    assert run_security_gate(before(), after(replay=0.04), HASH_A, HASH_A, cfg).verdict == "pass"
    assert (
        run_security_gate(before(), after(replay=0.041), HASH_A, HASH_A, cfg).verdict
        == "security_regression"
    )


def test_gate_insufficient_attack_samples_inconclusive() -> None:
    cfg = SecurityGateConfig(min_attack_samples_per_pai=20)
    res = run_security_gate(before(), after(replay=0.15, n=10), HASH_A, HASH_A, cfg)
    assert res.verdict == "inconclusive"
    by_pai = {d.pai: d for d in res.per_pai}
    assert by_pai["replay_phone"].regressed is True
    assert by_pai["replay_phone"].insufficient_support is True
    # no regression but too few samples -> still inconclusive
    res = run_security_gate(before(), after(replay=0.02, n=10), HASH_A, HASH_A, cfg)
    assert res.verdict == "inconclusive"


def test_gate_pai_missing_on_one_side_is_inconclusive() -> None:
    b = _metrics({"print": 0.02, "replay_phone": 0.02}, bpcer=0.08, auc=0.95)
    a = _metrics({"print": 0.02}, bpcer=0.02, auc=0.97)
    res = run_security_gate(b, a, HASH_A, HASH_A, SecurityGateConfig())
    assert res.verdict == "inconclusive"
    by_pai = {d.pai: d for d in res.per_pai}
    assert by_pai["replay_phone"].insufficient_support is True
    assert by_pai["replay_phone"].delta == 0.0
    assert by_pai["replay_phone"].n_attack == 0


def test_gate_refuses_protocol_hash_mismatch() -> None:
    with pytest.raises(ProtocolMismatchError):
        run_security_gate(before(), after(), HASH_A, HASH_B, SecurityGateConfig())


def test_gate_justified_mismatch_is_comparison_blocked() -> None:
    res = run_security_gate(
        before(),
        after(),
        HASH_A,
        HASH_B,
        SecurityGateConfig(),
        justify="exploratory only, protocol v2 adds a PAI",
        baseline_run_id="run123",
    )
    assert res.verdict == "comparison_blocked"
    assert res.per_pai == []
    assert res.protocol_hash is None
    assert res.baseline_run_id == "run123"
    assert "exploratory only" in res.note


def test_auc_improvement_does_not_change_verdict() -> None:
    res = run_security_gate(before(), after(auc=0.999), HASH_A, HASH_A, SecurityGateConfig())
    assert res.verdict == "security_regression"
    assert res.auc_after > res.auc_before
    assert res.bpcer_improved is True
    # and a worse AUC / worse BPCER with no APCER regression still passes
    worse = _metrics({"print": 0.02, "replay_phone": 0.02}, bpcer=0.2, auc=0.5)
    res = run_security_gate(before(), worse, HASH_A, HASH_A, SecurityGateConfig())
    assert res.verdict == "pass"
    assert res.bpcer_improved is False


def test_gate_result_serialises() -> None:
    res = run_security_gate(before(), after(), HASH_A, HASH_A, SecurityGateConfig())
    payload = res.model_dump(mode="json")
    assert payload["verdict"] == "security_regression"
    assert payload["per_pai"][0]["pai"] == "print"
