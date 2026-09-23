"""Unit tests for contract §44 experiment reports."""

from __future__ import annotations

from pathlib import Path

import pytest

from pad_research.config.compose import compose_spec
from pad_research.evaluation.evaluator import EvalResult
from pad_research.experiments.registry import RegistryRow, utc_now
from pad_research.experiments.status import RunStatus
from pad_research.metrics.pad_metrics import PadMetrics
from pad_research.metrics.threshold import ThresholdPolicy
from pad_research.protocols.hashing import protocol_hash
from pad_research.reporting.report import RunRecord, generate_report, reportable_statuses
from pad_research.reporting.template import SECTION44_HEADINGS

ROOT = Path(__file__).resolve().parents[2]


def _spec():
    _, spec = compose_spec(["+exp=syn_e03_video_full_ft_bf_only"], config_dir=ROOT / "configs")
    return spec


def _metrics(apcer: float = 0.25) -> PadMetrics:
    return PadMetrics(
        tau=0.5,
        apcer_per_pai={"print": apcer, "replay_phone": apcer + 0.1},
        apcer_max=apcer + 0.1,
        apcer_pooled=apcer,
        apcer=apcer + 0.1,
        bpcer=0.125,
        acer=(apcer + 0.1 + 0.125) / 2.0,
        hter=(apcer + 0.125) / 2.0,
        auc=0.75,
        acer_policy="max_pai",
        n_bona_fide=8,
        n_attack_per_pai={"print": 4, "replay_phone": 4},
    )


def _run(
    *,
    run_id: str = "a" * 32,
    seed: int = 1,
    status: RunStatus = RunStatus.smoke_ok,
    mode: str = "smoke",
    apcer: float = 0.25,
    hash_value: str | None = None,
    research_claim_allowed: bool = False,
) -> RunRecord:
    spec = _spec()
    ph = hash_value or protocol_hash(spec.protocol)
    metrics = _metrics(apcer)
    threshold = ThresholdPolicy(
        spec=spec.protocol.threshold,
        tau=0.5,
        fitted_on="source/dev",
        dev_n_bona_fide=8,
        dev_n_attack=8,
        dev_eer=0.25,
    )
    eval_result = EvalResult(
        experiment_id=spec.experiment.id,
        science_hash="c" * 64,
        spec_hash="d" * 64,
        protocol_id=spec.protocol.protocol_id,
        protocol_hash=ph,
        manifest_hashes={"synthetic_a": "a" * 64, "synthetic_b": "b" * 64},
        adaptation_set_hash="e" * 64,
        seed=seed,
        mode=mode,
        domain="target",
        role="test",
        metrics=metrics,
        threshold=threshold,
        n_test=16,
        latency=None,
        status=status,
    )
    now = utc_now()
    registry = RegistryRow(
        exp_id=spec.experiment.id,
        seed=seed,
        mode=mode,
        science_hash="c" * 64,
        spec_hash="d" * 64,
        protocol_id=spec.protocol.protocol_id,
        protocol_hash=ph,
        adaptation_set_hash="e" * 64,
        mlflow_run_id=run_id,
        status=status,
        git_sha="f" * 40,
        git_dirty=False,
        started_at=now,
        finished_at=now,
        results_dir=None,
    )
    return RunRecord(
        registry=registry,
        eval=eval_result,
        spec=spec,
        mlflow_run_id=run_id,
        tags={"research_claim_allowed": str(research_claim_allowed).lower()},
    )


def _report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *runs: RunRecord):
    monkeypatch.setenv("PAD_REPO_ROOT", str(tmp_path))
    return generate_report(list(runs), None, tmp_path / "report.md", justify=None)


def test_report_contains_all_section44_headings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _report(tmp_path, monkeypatch, _run())
    for heading in SECTION44_HEADINGS:
        assert heading in bundle.text
    assert bundle.report_path.is_file()
    assert bundle.per_attack_csv.is_file()


def test_report_excludes_smoke_runs_by_default() -> None:
    assert RunStatus.smoke_ok not in reportable_statuses(include_smoke=False)
    assert RunStatus.smoke_ok in reportable_statuses(include_smoke=True)


def test_report_single_seed_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _report(tmp_path, monkeypatch, _run())
    assert "seed가 3개 미만" in bundle.text


def test_report_synthetic_banner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _report(tmp_path, monkeypatch, _run(research_claim_allowed=False))
    assert "SYNTHETIC SANITY — NOT A RESEARCH RESULT" in bundle.text


def test_report_blocks_protocol_mismatch_without_justify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAD_REPO_ROOT", str(tmp_path))
    baseline = _run(run_id="b" * 32, hash_value="b" * 64)
    method = _run(run_id="c" * 32, hash_value="c" * 64)
    with pytest.raises(RuntimeError, match="protocol hash mismatch"):
        generate_report([method], [baseline], tmp_path / "report.md", justify=None)


def test_report_justify_banner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAD_REPO_ROOT", str(tmp_path))
    baseline = _run(run_id="b" * 32, hash_value="b" * 64)
    method = _run(run_id="c" * 32, hash_value="c" * 64)
    bundle = generate_report(
        [method],
        [baseline],
        tmp_path / "report.md",
        justify="ablation: adaptation enabled",
    )
    assert "NOT DIRECTLY COMPARABLE: ablation: adaptation enabled" in bundle.text
    assert bundle.gate is not None
    assert bundle.gate.verdict == "comparison_blocked"
