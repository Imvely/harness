"""Tests for dashboard JSON export contracts."""

from __future__ import annotations

import json
from pathlib import Path

from pad_research.config.compose import compose_spec
from pad_research.dashboard.export import export_dashboard_bundle, write_dashboard_bundle
from pad_research.data.manifest import PAI, Label, ManifestRecord, MediaType, Split, write_manifest
from pad_research.evaluation.evaluator import EvalResult
from pad_research.experiments.registry import RegistryRow
from pad_research.experiments.status import RunStatus
from pad_research.metrics.pad_metrics import PadMetrics
from pad_research.metrics.threshold import ThresholdPolicy
from pad_research.protocols.hashing import protocol_hash
from pad_research.reporting.report import RunRecord

ROOT = Path(__file__).resolve().parents[2]


def _records(dataset_id: str, subject_offset: int) -> list[ManifestRecord]:
    records: list[ManifestRecord] = []
    subject = subject_offset
    for split in (Split.train, Split.dev, Split.test):
        for _ in range(4):
            for clip, pai in enumerate((PAI.none, PAI.print, PAI.replay_phone, PAI.replay_tablet)):
                label = Label.bona_fide if pai == PAI.none else Label.spoof
                sample_id = f"{dataset_id}_s{subject:03d}_c{clip:02d}_{pai.value}"
                records.append(
                    ManifestRecord(
                        dataset_id=dataset_id,
                        sample_id=sample_id,
                        subject_id=f"{dataset_id}_subj{subject:03d}",
                        split=split,
                        label=label,
                        pai=pai,
                        relative_path=f"{dataset_id}/{sample_id}.npy",
                        media_type=MediaType.npy_clip,
                        n_frames=16,
                    )
                )
            subject += 1
    return records


def _write_manifests(repo: Path, *, pii_policy: str = "synthetic") -> None:
    manifests = repo / "data" / "manifests"
    for dataset_id, subject_offset in (("synthetic_a", 0), ("synthetic_b", 100)):
        write_manifest(
            _records(dataset_id, subject_offset),
            {
                "dataset_id": dataset_id,
                "version": "test",
                "adapter": "test",
                "license": "test",
                "pii_policy": pii_policy,
                "temporal_valid": True,
            },
            manifests,
        )


def _metrics() -> PadMetrics:
    return PadMetrics(
        tau=0.5,
        apcer_per_pai={"print": 0.125, "replay_phone": 0.25, "replay_tablet": 0.25},
        apcer_max=0.25,
        apcer_pooled=0.21,
        apcer=0.25,
        bpcer=0.125,
        acer=0.1875,
        hter=0.1675,
        auc=0.82,
        acer_policy="max_pai",
        n_bona_fide=8,
        n_attack_per_pai={"print": 4, "replay_phone": 4, "replay_tablet": 4},
    )


def _record(
    *,
    repo: Path,
    exp_name: str = "syn_e03_video_full_ft_bf_only",
    run_id: str = "a" * 32,
    seed: int = 1,
    mode: str = "full",
    status: RunStatus = RunStatus.success,
    hash_value: str | None = None,
    research_claim_allowed: bool = False,
) -> RunRecord:
    overrides = [f"+exp={exp_name}", f"training.seed={seed}"]
    if mode == "full":
        overrides += ["execution.mode=full", "execution.allow_full_gpu_run=true"]
    _, spec = compose_spec(overrides, config_dir=ROOT / "configs")
    ph = hash_value or protocol_hash(spec.protocol)
    threshold = ThresholdPolicy(
        spec=spec.protocol.threshold,
        tau=0.5,
        fitted_on="source/dev",
        dev_n_bona_fide=8,
        dev_n_attack=12,
        dev_eer=0.2,
    )
    eval_result = EvalResult(
        experiment_id=spec.experiment.id,
        science_hash="c" * 64,
        spec_hash="d" * 64,
        protocol_id=spec.protocol.protocol_id,
        protocol_hash=ph,
        manifest_hashes={"synthetic_a": "1" * 64, "synthetic_b": "2" * 64},
        adaptation_set_hash="e" * 64,
        seed=seed,
        mode=mode,
        domain="target",
        role="test",
        metrics=_metrics(),
        threshold=threshold,
        n_test=20,
        latency=None,
        status=status,
    )
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
        started_at="2026-09-18T00:00:00+00:00",
        finished_at="2026-09-18T00:01:00+00:00",
        results_dir=str(repo / "outputs" / run_id),
    )
    return RunRecord(
        registry=registry,
        eval=eval_result,
        spec=spec,
        mlflow_run_id=run_id,
        tags={"research_claim_allowed": str(research_claim_allowed).lower()},
    )


def test_dashboard_export_marks_synthetic_runs_not_claim_eligible(tmp_path: Path) -> None:
    _write_manifests(tmp_path, pii_policy="synthetic")
    records = [
        _record(repo=tmp_path, seed=seed, research_claim_allowed=False) for seed in (1, 2, 3)
    ]

    bundle = export_dashboard_bundle(
        records, repo_root=tmp_path, generated_at="2026-09-18T00:00:00+00:00"
    )

    assert len(bundle.runs) == 3
    run = bundle.runs[0]
    assert run.research_claim_allowed is False
    assert run.dataset_pii_policies == {"synthetic_a": "synthetic", "synthetic_b": "synthetic"}
    assert run.claim_eligibility.allowed is False
    assert "at least one dataset is synthetic" in run.claim_eligibility.reasons


def test_dashboard_export_records_mixed_protocol_as_claim_blocker(tmp_path: Path) -> None:
    _write_manifests(tmp_path, pii_policy="licensed_research")
    records = [
        _record(repo=tmp_path, seed=1, hash_value="a" * 64, research_claim_allowed=True),
        _record(repo=tmp_path, seed=2, hash_value="b" * 64, research_claim_allowed=True),
        _record(repo=tmp_path, seed=3, hash_value="b" * 64, research_claim_allowed=True),
    ]

    bundle = export_dashboard_bundle(records, repo_root=tmp_path)

    assert all(not run.claim_eligibility.single_protocol_in_experiment for run in bundle.runs)
    assert all(
        "experiment contains multiple protocol hashes" in run.claim_eligibility.reasons
        for run in bundle.runs
    )


def test_dashboard_json_does_not_leak_absolute_or_raw_paths(tmp_path: Path) -> None:
    _write_manifests(tmp_path, pii_policy="synthetic")
    bundle = export_dashboard_bundle([_record(repo=tmp_path)], repo_root=tmp_path)

    out = write_dashboard_bundle(bundle, tmp_path / "dashboard.json")
    text = out.read_text(encoding="utf-8")
    payload = json.loads(text)

    assert payload["schema_version"] == "pad-dashboard.v1"
    assert str(tmp_path) not in text
    assert "data/raw" not in text.replace("\\", "/")
    for run in payload["runs"]:
        for artifact in run["artifacts"]:
            assert not Path(artifact["relative_path"]).is_absolute()
            assert ".." not in artifact["relative_path"]


def test_dashboard_export_source_only_success_uses_no_gate(tmp_path: Path) -> None:
    _write_manifests(tmp_path, pii_policy="synthetic")
    bundle = export_dashboard_bundle(
        [_record(repo=tmp_path, exp_name="syn_e02_video_source_only")],
        repo_root=tmp_path,
    )

    assert bundle.runs[0].gate_verdict == "no_gate"


def test_dashboard_export_allowlists_and_redacts_tags(tmp_path: Path) -> None:
    _write_manifests(tmp_path, pii_policy="synthetic")
    record = _record(repo=tmp_path)
    tagged = RunRecord(
        registry=record.registry,
        eval=record.eval,
        spec=record.spec,
        mlflow_run_id=record.mlflow_run_id,
        tags={
            "research_claim_allowed": "false",
            "protocol_hash": record.eval.protocol_hash,
            "checkpoint_source": str(tmp_path / "checkpoints" / "model.pt"),
            "custom_note": f"debug path {tmp_path / 'data' / 'processed' / 'clip.npy'}",
        },
    )

    bundle = export_dashboard_bundle([tagged], repo_root=tmp_path)
    payload = json.dumps(bundle.model_dump(mode="json"))

    assert "checkpoint_source" not in bundle.runs[0].tags
    assert "custom_note" not in bundle.runs[0].tags
    assert str(tmp_path) not in payload
    assert "data/processed" not in payload


def test_dashboard_marks_thin_pai_unsupported_like_the_gate(tmp_path: Path) -> None:
    """A PAI below the protocol's min_attack_samples_per_pai must not look fully supported.

    The security gate calls such a comparison inconclusive (contract section 14.3). If the
    dashboard used "any attack sample at all" instead, it would overstate the evidence behind
    a run and disagree with the gate on the same numbers.
    """
    _write_manifests(tmp_path, pii_policy="synthetic")
    record = _record(repo=tmp_path, exp_name="syn_e02_video_source_only")
    minimum = record.spec.protocol.security_gate.min_attack_samples_per_pai
    assert minimum > 1
    thin_metrics = record.eval.metrics.model_copy(
        update={
            "n_attack_per_pai": {
                "print": minimum - 1,
                "replay_phone": minimum,
                "replay_tablet": minimum,
            }
        }
    )
    thin = RunRecord(
        registry=record.registry,
        eval=record.eval.model_copy(update={"metrics": thin_metrics}),
        spec=record.spec,
        mlflow_run_id=record.mlflow_run_id,
        tags=record.tags,
    )

    bundle = export_dashboard_bundle([thin], repo_root=tmp_path)
    support = {row.pai: row.insufficient_support for row in bundle.runs[0].per_attack}

    assert support["print"] is True
    assert support["replay_phone"] is False
    assert support["replay_tablet"] is False
