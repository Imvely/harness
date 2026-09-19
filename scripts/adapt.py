#!/usr/bin/env python
"""Adapt a source checkpoint on the protocol adaptation set and evaluate it."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import hydra
from omegaconf import DictConfig

from pad_research import paths
from pad_research.adaptation.strategies import build_strategy
from pad_research.config.compose import (
    config_sources,
    exp_name_from_overrides,
    spec_from_cfg,
    task_overrides,
)
from pad_research.config.freeze import read_frozen_spec
from pad_research.evaluation.evaluator import (
    EvalResult,
    collect_scores,
    evaluate,
    measure_latency,
    roc_png,
)
from pad_research.experiments.gate import check_full_run_gate
from pad_research.experiments.registry import Registry, utc_now
from pad_research.experiments.status import RunStatus
from pad_research.experiments.validator import resolve_tracking_uri, tracking_writable
from pad_research.metrics.security_gate import run_security_gate
from pad_research.metrics.threshold import ThresholdPolicy
from pad_research.models.registry import build_model
from pad_research.protocols.hashing import protocol_hash
from pad_research.protocols.loader import load_protocol
from pad_research.protocols.validator import validate_protocol
from pad_research.tracking.env_snapshot import collect_env_snapshot
from pad_research.tracking.mlflow_tracker import MlflowTracker
from pad_research.training.checkpoint import Checkpoint, load_checkpoint, save_checkpoint
from pad_research.training.pipeline import (
    effective_limits,
    invalid_registry_row,
    load_protocol_manifests,
    make_loader,
    protocol_splits,
    registry_row,
    run_output_dir,
    select_and_materialize_adaptation,
    torch_gpu_info,
    write_json,
    write_resolved_spec_to_run,
    write_train_curve_csv,
)
from pad_research.training.trainer import Trainer
from pad_research.utils.device import resolve_device
from pad_research.utils.git import git_state
from pad_research.utils.redaction import redact_text
from pad_research.utils.seed import seed_everything


def _mlflow_artifact(run_id: str, name: str, tracking_uri: str) -> Path:
    import mlflow
    import mlflow.artifacts

    mlflow.set_tracking_uri(tracking_uri)
    return Path(mlflow.artifacts.download_artifacts(artifact_uri=f"runs:/{run_id}/{name}"))


def _mlflow_dict(run_id: str, name: str, tracking_uri: str) -> dict[str, Any] | None:
    import mlflow
    import mlflow.artifacts

    mlflow.set_tracking_uri(tracking_uri)
    try:
        obj = mlflow.artifacts.load_dict(f"runs:/{run_id}/{name}")
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _load_source_checkpoint(spec: Any, tracking_uri: str) -> tuple[Checkpoint, str]:
    if spec.adaptation.source_checkpoint:
        source = str(spec.adaptation.source_checkpoint)
        return load_checkpoint(source), source
    if spec.adaptation.source_run_id:
        path = _mlflow_artifact(spec.adaptation.source_run_id, "checkpoint.pt", tracking_uri)
        return load_checkpoint(path), f"mlflow:{spec.adaptation.source_run_id}"
    raise ValueError(
        "adaptation.source_run_id or adaptation.source_checkpoint is required for adapt.py"
    )


def _allowed_protocol_hashes(spec: Any, root: Path) -> set[str]:
    allowed = {protocol_hash(spec.protocol)}
    if spec.protocol.parent_protocol_id:
        parent = load_protocol(spec.protocol.parent_protocol_id, root / "configs")
        allowed.add(protocol_hash(parent))
    return allowed


def _metric_deltas(before: dict[str, Any] | None, after: EvalResult) -> dict[str, Any] | None:
    if before is None:
        return None
    try:
        before_eval = EvalResult.model_validate(before)
    except ValueError:
        return None
    b = before_eval.metrics
    a = after.metrics
    return {
        "apcer_delta": a.apcer - b.apcer,
        "bpcer_delta": a.bpcer - b.bpcer,
        "acer_delta": a.acer - b.acer,
        "hter_delta": a.hter - b.hter,
        "auc_delta": a.auc - b.auc,
    }


def _status_from_verdict(mode: str, verdict: str) -> RunStatus:
    if mode == "smoke":
        return RunStatus.smoke_ok
    if verdict == "security_regression":
        return RunStatus.security_regression
    if verdict in ("inconclusive", "comparison_blocked"):
        return RunStatus.inconclusive
    return RunStatus.success


def _artifact_paths(run_dir: Path) -> list[Path]:
    names = [
        "resolved_spec.yaml",
        "protocol.json",
        "env_snapshot.json",
        "eval_source_dev.json",
        "eval_test.json",
        "scores_dev.csv",
        "scores_source_dev.csv",
        "scores_test.csv",
        "roc_curve.png",
        "training_curves.csv",
        "latency.json",
        "checkpoint.pt",
        "regression_check.json",
    ]
    return [run_dir / name for name in names if (run_dir / name).is_file()]


def _main_impl(cfg: DictConfig) -> int:
    root = paths.repo_root()
    registry = Registry()
    git = git_state(root)
    try:
        spec = spec_from_cfg(cfg)
    except Exception as exc:
        exp_name = exp_name_from_overrides(task_overrides()) or "unknown"
        registry.append(
            invalid_registry_row(
                exp_name,
                RunStatus.invalid_spec,
                git,
                note=redact_text(repr(exc), root),
            )
        )
        print(f"invalid spec: {redact_text(exc, root)}", file=sys.stderr)
        return 2
    if not spec.adaptation.enabled:
        print("adapt.py requires adaptation.enabled=true", file=sys.stderr)
        return 2

    manifests_dir = root / spec.data.manifests_dir
    pv = validate_protocol(spec.protocol, manifests_dir, frames=spec.model.input.frames)
    if not pv.ok:
        started = utc_now()
        registry.append(
            registry_row(
                spec,
                pv,
                git,
                RunStatus.invalid_protocol,
                started_at=started,
                finished_at=started,
                note=redact_text(
                    "; ".join(f"{i.code}: {i.message}" for i in pv.errors()),
                    root,
                ),
            )
        )
        for issue in pv.errors():
            print(
                f"protocol {issue.code}: {redact_text(issue.message, root)}",
                file=sys.stderr,
            )
        return 3

    env = collect_env_snapshot(root, with_torch=True)
    tracking_uri = resolve_tracking_uri(spec.tracking.tracking_uri)
    tracking_ok, tracking_note = tracking_writable(
        tracking_uri,
        allow_remote=spec.execution.mode != "full",
    )
    gate = check_full_run_gate(
        spec,
        git=git,
        task_overrides=[t for t in task_overrides() if not t.lstrip("+~").startswith("exp=")],
        protocol_validation=pv,
        tracking_ok=tracking_ok,
        registry=registry,
        frozen=read_frozen_spec(spec.experiment.id, paths.specs_dir()),
        gpu=torch_gpu_info(),
        config_sources=config_sources(),
        repo_root=root,
    )
    if not gate.allowed:
        started = utc_now()
        registry.append(
            registry_row(
                spec,
                pv,
                git,
                RunStatus.blocked_by_gate,
                started_at=started,
                finished_at=started,
                note="; ".join(gate.reasons),
            )
        )
        print("full-run gate blocked launch: " + "; ".join(gate.reasons), file=sys.stderr)
        return 4
    if tracking_note:
        print(f"tracking warning: {redact_text(tracking_note, root)}", file=sys.stderr)

    source_ckpt, checkpoint_source = _load_source_checkpoint(spec, tracking_uri)
    if source_ckpt.protocol_hash not in _allowed_protocol_hashes(spec, root):
        from pad_research.errors import CheckpointProtocolMismatchError

        raise CheckpointProtocolMismatchError(
            f"checkpoint protocol_hash {source_ckpt.protocol_hash[:12]} is not compatible "
            f"with current protocol {pv.protocol_hash[:12]}"
        )

    seed_everything(spec.training.seed, deterministic=spec.training.deterministic)
    device = resolve_device(spec.training.device)
    run_dir = run_output_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    data_root = paths.data_root(spec.data.root_env_var)
    manifests = load_protocol_manifests(spec, manifests_dir)
    selection, adaptation_path = select_and_materialize_adaptation(spec, manifests, manifests_dir)
    splits = protocol_splits(spec, manifests, selection)
    if not splits.adaptation:
        raise ValueError("protocol adaptation set is empty")

    tracker = MlflowTracker(spec.tracking, root)
    run_id: str | None = None
    started_at = utc_now()
    try:
        model = build_model(spec.model.model_dump(mode="python"))
        model.load_state_dict(source_ckpt.state_dict)
        strategy = build_strategy(spec.adaptation.model_dump(mode="python"))
        run_id = tracker.start_run(
            spec,
            pv,
            env,
            adaptation_set_hash=selection.adaptation_set_hash if selection else None,
            run_name=spec.tracking.run_name,
            model_init="checkpoint",
            checkpoint_source=checkpoint_source,
        )
        registry.append(
            registry_row(
                spec,
                pv,
                git,
                RunStatus.running,
                started_at=started_at,
                results_dir=run_dir,
                mlflow_run_id=run_id,
                adaptation_set_hash=selection.adaptation_set_hash if selection else None,
            )
        )

        limits = effective_limits(spec)
        max_eval_batches = limits.max_eval_batches if limits is not None else None
        eval_batch_size = spec.training.batch_size * (
            limits.max_eval_batches if limits is not None else 1
        )
        adapt_loader = make_loader(
            splits.adaptation,
            spec,
            data_root=data_root,
            batch_size=spec.adaptation.batch_size,
            train=True,
            seed_offset=404,
            drop_last=False,
        )
        source_dev_loader = make_loader(
            splits.source_dev,
            spec,
            data_root=data_root,
            batch_size=eval_batch_size,
            train=False,
            seed_offset=505,
            drop_last=False,
            shuffle=False,
        )
        target_dev_loader = make_loader(
            splits.target_dev,
            spec,
            data_root=data_root,
            batch_size=eval_batch_size,
            train=False,
            seed_offset=606,
            drop_last=False,
            shuffle=False,
        )
        target_test_loader = make_loader(
            splits.target_test,
            spec,
            data_root=data_root,
            batch_size=eval_batch_size,
            train=False,
            seed_offset=707,
            drop_last=False,
            shuffle=False,
        )

        train_result = Trainer(
            model,
            strategy,
            {"train": adapt_loader},
            spec,
            tracker,
            limits,
            device,
        ).fit()

        if spec.protocol.threshold.dev_domain == "source":
            if source_ckpt.threshold is None:
                raise ValueError("source checkpoint does not contain a fitted threshold")
            threshold = source_ckpt.threshold
            dev_scores = collect_scores(
                model,
                strategy,
                source_dev_loader,
                device,
                max_eval_batches,
                "dev",
                "source",
            )
        else:
            dev_scores = collect_scores(
                model,
                strategy,
                target_dev_loader,
                device,
                max_eval_batches,
                "dev",
                "target",
            )
            threshold = ThresholdPolicy(spec=spec.protocol.threshold).fit(dev_scores)

        source_dev_scores = (
            dev_scores
            if dev_scores.domain == "source"
            else collect_scores(
                model,
                strategy,
                source_dev_loader,
                device,
                max_eval_batches,
                "dev",
                "source",
            )
        )
        target_domain = "target" if spec.protocol.target_dataset else "source"
        test_scores = collect_scores(
            model,
            strategy,
            target_test_loader,
            device,
            max_eval_batches,
            "test",
            target_domain,
        )
        latency = (
            measure_latency(
                model,
                (
                    spec.model.input.frames,
                    3,
                    spec.model.input.image_size[0],
                    spec.model.input.image_size[1],
                ),
                device,
                spec.evaluation.latency.warmup,
                limits.latency_repetitions
                if limits is not None
                else spec.evaluation.latency.repetitions,
                spec.evaluation.latency.batch_size,
                smoke=limits is not None,
            )
            if spec.evaluation.measure_latency
            else None
        )
        source_dev_eval = evaluate(source_dev_scores, threshold, spec, pv)
        test_eval = evaluate(test_scores, threshold, spec, pv, latency=latency)

        baseline = (
            tracker.find_baseline(
                spec.evaluation.baseline_experiment_id,
                pv.protocol_hash,
                include_smoke=spec.execution.mode == "smoke",
            )
            if spec.evaluation.baseline_experiment_id is not None
            else None
        )
        if baseline is None:
            gate_verdict = "inconclusive"
            gate_payload: dict[str, Any] = {
                "verdict": gate_verdict,
                "baseline_run_id": None,
                "note": "no comparable baseline run found",
            }
        else:
            gate_result = run_security_gate(
                baseline.metrics,
                test_eval.metrics,
                baseline.protocol_hash,
                pv.protocol_hash,
                spec.protocol.security_gate,
                baseline_run_id=baseline.run_id,
            )
            gate_verdict = gate_result.verdict
            gate_payload = gate_result.model_dump(mode="json")
        final_status = _status_from_verdict(spec.execution.mode, gate_verdict)
        source_before = (
            _mlflow_dict(baseline.run_id, "eval_source_dev.json", tracking_uri)
            if baseline is not None
            else None
        )
        regression_payload = {
            "gate": gate_payload,
            "baseline_run_id": baseline.run_id if baseline is not None else None,
            "candidate_run_id": run_id,
            "source_domain_delta": _metric_deltas(source_before, source_dev_eval),
        }
        test_eval = test_eval.model_copy(update={"status": final_status})
        source_dev_eval = source_dev_eval.model_copy(update={"status": final_status})

        write_resolved_spec_to_run(run_dir / "resolved_spec.yaml", spec)
        write_json(run_dir / "protocol.json", spec.protocol)
        write_json(run_dir / "env_snapshot.json", env)
        write_json(run_dir / "eval_source_dev.json", source_dev_eval)
        write_json(run_dir / "eval_test.json", test_eval)
        if latency is not None:
            write_json(run_dir / "latency.json", latency)
        dev_scores.to_csv(run_dir / "scores_dev.csv")
        source_dev_scores.to_csv(run_dir / "scores_source_dev.csv")
        test_scores.to_csv(run_dir / "scores_test.csv")
        roc_png(test_scores, run_dir / "roc_curve.png")
        write_train_curve_csv(run_dir / "training_curves.csv", train_result.train_curve)
        write_json(run_dir / "regression_check.json", regression_payload)
        if adaptation_path is not None:
            tracker.log_artifact_file(adaptation_path)
        checkpoint_path = save_checkpoint(
            run_dir / "checkpoint.pt",
            model,
            spec,
            threshold,
            pv.protocol_hash,
            {
                **strategy.state(),
                "source_checkpoint": checkpoint_source,
                "train_result": {
                    "epochs_run": train_result.epochs_run,
                    "steps": train_result.steps,
                    "wall_clock_s": train_result.wall_clock_s,
                },
                "source_dev_metrics": source_dev_eval.metrics.model_dump(mode="json"),
                "gate_verdict": gate_verdict,
            },
        )
        for artifact_path in _artifact_paths(run_dir):
            if artifact_path.name == "checkpoint.pt" and not spec.tracking.log_checkpoint:
                continue
            tracker.log_artifact_file(artifact_path)
        tracker.log_metrics(test_eval.metrics)
        tracker.set_tag("gate_verdict", gate_verdict)
        tracker.end_run(final_status)
        registry.append(
            registry_row(
                spec,
                pv,
                git,
                final_status,
                started_at=started_at,
                finished_at=utc_now(),
                results_dir=run_dir,
                mlflow_run_id=run_id,
                adaptation_set_hash=selection.adaptation_set_hash if selection else None,
                note=f"gate_verdict={gate_verdict}; checkpoint={checkpoint_path.name}",
            )
        )
        print(
            f"run_id={run_id} status={final_status.value} gate_verdict={gate_verdict} "
            f"results_dir={run_dir}"
        )
        return 0
    except Exception as exc:
        if run_id is not None:
            tracker.set_tag("failure", redact_text(repr(exc), root))
            tracker.end_run(RunStatus.failed_training)
            registry.append(
                registry_row(
                    spec,
                    pv,
                    git,
                    RunStatus.failed_training,
                    started_at=started_at,
                    finished_at=utc_now(),
                    results_dir=run_dir,
                    mlflow_run_id=run_id,
                    adaptation_set_hash=selection.adaptation_set_hash if selection else None,
                    note=redact_text(repr(exc), root),
                )
            )
        raise


@hydra.main(config_path=str(paths.configs_dir()), config_name="config", version_base="1.3")
def main(cfg: DictConfig) -> None:
    code = _main_impl(cfg)
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
