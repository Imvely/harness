#!/usr/bin/env python
"""Evaluate an existing checkpoint under the configured protocol."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import hydra
from omegaconf import DictConfig

from pad_research import paths
from pad_research.adaptation.strategies import NoAdaptation
from pad_research.config.compose import exp_name_from_overrides, spec_from_cfg, task_overrides
from pad_research.evaluation.evaluator import collect_scores, evaluate, measure_latency, roc_png
from pad_research.experiments.registry import Registry, utc_now
from pad_research.experiments.status import RunStatus
from pad_research.experiments.validator import resolve_tracking_uri
from pad_research.metrics.threshold import ThresholdPolicy
from pad_research.models.registry import build_model
from pad_research.protocols.validator import validate_protocol
from pad_research.tracking.env_snapshot import collect_env_snapshot
from pad_research.tracking.mlflow_tracker import MlflowTracker
from pad_research.training.checkpoint import Checkpoint, load_checkpoint
from pad_research.training.pipeline import (
    effective_limits,
    eval_loader_budget,
    invalid_registry_row,
    load_protocol_manifests,
    make_loader,
    protocol_splits,
    registry_row,
    run_output_dir,
    select_and_materialize_adaptation,
    terminal_status_for_pass,
    write_json,
    write_resolved_spec_to_run,
)
from pad_research.utils.device import resolve_device
from pad_research.utils.git import git_state
from pad_research.utils.redaction import redact_text
from pad_research.utils.seed import seed_everything


def _mlflow_artifact(run_id: str, name: str, tracking_uri: str) -> Path:
    import mlflow
    import mlflow.artifacts

    mlflow.set_tracking_uri(tracking_uri)
    return Path(mlflow.artifacts.download_artifacts(artifact_uri=f"runs:/{run_id}/{name}"))


def _load_eval_checkpoint(source: str, tracking_uri: str) -> tuple[Checkpoint, str]:
    if source.startswith("mlflow:"):
        run_id = source.split(":", 1)[1]
        path = _mlflow_artifact(run_id, "checkpoint.pt", tracking_uri)
        return load_checkpoint(path), source
    return load_checkpoint(source), source


def _artifact_paths(run_dir: Path) -> list[Path]:
    names = [
        "resolved_spec.yaml",
        "protocol.json",
        "env_snapshot.json",
        "eval_test.json",
        "scores_dev.csv",
        "scores_test.csv",
        "roc_curve.png",
        "latency.json",
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

    checkpoint_source = spec.evaluation.checkpoint or spec.model.checkpoint
    if checkpoint_source is None:
        print("evaluate.py requires evaluation.checkpoint or model.checkpoint", file=sys.stderr)
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

    tracking_uri = resolve_tracking_uri(spec.tracking.tracking_uri)
    ckpt, checkpoint_source = _load_eval_checkpoint(checkpoint_source, tracking_uri)
    if ckpt.protocol_hash != pv.protocol_hash:
        from pad_research.errors import CheckpointProtocolMismatchError

        raise CheckpointProtocolMismatchError(
            f"checkpoint protocol_hash {ckpt.protocol_hash[:12]} != current {pv.protocol_hash[:12]}"
        )

    run_id: str | None = None
    started_at = utc_now()
    final_status = terminal_status_for_pass(spec)
    run_dir: Path | None = None
    selection = None
    tracker: MlflowTracker | None = None
    try:
        # Setup runs inside the try so a crash here (missing data root, unreadable manifest,
        # unwritable tracking store) is recorded as failed_environment rather than vanishing
        # from the registry (contract section 35).
        seed_everything(spec.training.seed, deterministic=spec.training.deterministic)
        env = collect_env_snapshot(root, with_torch=True)
        device = resolve_device(spec.training.device)
        run_dir = run_output_dir()
        run_dir.mkdir(parents=True, exist_ok=True)
        data_root = paths.data_root(spec.data.root_env_var)
        manifests = load_protocol_manifests(spec, manifests_dir)
        selection, _ = select_and_materialize_adaptation(spec, manifests, manifests_dir)
        splits = protocol_splits(spec, manifests, selection)
        tracker = MlflowTracker(spec.tracking, root)
        model = build_model(spec.model.model_dump(mode="python"))
        model.load_state_dict(ckpt.state_dict)
        strategy = NoAdaptation()
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
        eval_batch_size, max_eval_batches = eval_loader_budget(spec, limits)
        source_dev_loader = make_loader(
            splits.source_dev,
            spec,
            data_root=data_root,
            batch_size=eval_batch_size,
            train=False,
            seed_offset=808,
            drop_last=False,
            shuffle=False,
        )
        target_dev_loader = make_loader(
            splits.target_dev,
            spec,
            data_root=data_root,
            batch_size=eval_batch_size,
            train=False,
            seed_offset=909,
            drop_last=False,
            shuffle=False,
        )
        target_test_loader = make_loader(
            splits.target_test,
            spec,
            data_root=data_root,
            batch_size=eval_batch_size,
            train=False,
            seed_offset=1001,
            drop_last=False,
            shuffle=False,
        )
        if ckpt.threshold is not None:
            threshold = ckpt.threshold
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
            threshold_dev_loader = (
                target_dev_loader
                if spec.protocol.threshold.dev_domain == "target"
                else source_dev_loader
            )
            threshold_domain = spec.protocol.threshold.dev_domain
            dev_scores = collect_scores(
                model,
                strategy,
                threshold_dev_loader,
                device,
                max_eval_batches,
                "dev",
                threshold_domain,
            )
            threshold = ThresholdPolicy(spec=spec.protocol.threshold).fit(dev_scores)
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
        test_eval = evaluate(test_scores, threshold, spec, pv, latency=latency, status=final_status)
        write_resolved_spec_to_run(run_dir / "resolved_spec.yaml", spec)
        write_json(run_dir / "protocol.json", spec.protocol)
        write_json(run_dir / "env_snapshot.json", env)
        write_json(run_dir / "eval_test.json", test_eval)
        if latency is not None:
            write_json(run_dir / "latency.json", latency)
        dev_scores.to_csv(run_dir / "scores_dev.csv")
        test_scores.to_csv(run_dir / "scores_test.csv")
        roc_png(test_scores, run_dir / "roc_curve.png")
        for artifact_path in _artifact_paths(run_dir):
            tracker.log_artifact_file(artifact_path)
        tracker.log_metrics(test_eval.metrics)
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
                note=f"checkpoint_source={checkpoint_source}",
            )
        )
        print(f"run_id={run_id} status={final_status.value} results_dir={run_dir}")
        return 0
    except Exception as exc:
        # A crash before the MLflow run exists is an environment failure; after it, a training
        # failure. Either way the registry keeps a row (contract section 35).
        status = RunStatus.failed_training if run_id is not None else RunStatus.failed_environment
        if run_id is not None and tracker is not None:
            tracker.set_tag("failure", redact_text(repr(exc), root))
            tracker.end_run(status)
        registry.append(
            registry_row(
                spec,
                pv,
                git,
                status,
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
