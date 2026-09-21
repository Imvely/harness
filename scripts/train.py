#!/usr/bin/env python
"""Train a source-only PAD baseline and evaluate it on the protocol test split."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import hydra
from omegaconf import DictConfig

from pad_research import paths
from pad_research.adaptation.strategies import NoAdaptation
from pad_research.config.compose import (
    config_sources,
    exp_name_from_overrides,
    spec_from_cfg,
    task_overrides,
)
from pad_research.config.freeze import read_frozen_spec
from pad_research.data.storage.registry import build_storage
from pad_research.evaluation.evaluator import collect_scores, evaluate, measure_latency, roc_png
from pad_research.experiments.gate import check_full_run_gate
from pad_research.experiments.registry import Registry, utc_now
from pad_research.experiments.status import RunStatus
from pad_research.experiments.validator import resolve_tracking_uri, tracking_writable
from pad_research.metrics.threshold import ThresholdPolicy
from pad_research.models.registry import build_model
from pad_research.protocols.validator import validate_protocol
from pad_research.tracking.env_snapshot import collect_env_snapshot
from pad_research.tracking.mlflow_tracker import MlflowTracker
from pad_research.training.checkpoint import load_checkpoint, save_checkpoint
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
            print(f"protocol {issue.code}: {redact_text(issue.message, root)}", file=sys.stderr)
        return 3

    env = collect_env_snapshot(root, with_torch=True)
    tracking_ok, tracking_note = tracking_writable(
        resolve_tracking_uri(spec.tracking.tracking_uri),
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

    run_id: str | None = None
    started_at = utc_now()
    final_status = terminal_status_for_pass(spec)
    run_dir: Path | None = None
    selection = None
    tracker: MlflowTracker | None = None
    try:
        # Setup runs inside the try so a crash here (missing data root, unreadable manifest,
        # unwritable tracking store) is recorded as failed_environment rather than vanishing
        # from the registry (contract section 35: failed experiments are kept).
        seed_everything(spec.training.seed, deterministic=spec.training.deterministic)
        device = resolve_device(spec.training.device)
        run_dir = run_output_dir()
        run_dir.mkdir(parents=True, exist_ok=True)
        source = build_storage(spec.storage)
        manifests = load_protocol_manifests(spec, manifests_dir)
        selection, adaptation_path = select_and_materialize_adaptation(
            spec, manifests, manifests_dir
        )
        splits = protocol_splits(spec, manifests, selection)
        tracker = MlflowTracker(spec.tracking, root)
        model = build_model(spec.model.model_dump(mode="python"))
        model_init = "random"
        checkpoint_source = "none"
        if spec.model.checkpoint is not None:
            ckpt = load_checkpoint(spec.model.checkpoint)
            model.load_state_dict(ckpt.state_dict)
            model_init = "checkpoint"
            checkpoint_source = str(spec.model.checkpoint)
        strategy = NoAdaptation()
        run_id = tracker.start_run(
            spec,
            pv,
            env,
            adaptation_set_hash=selection.adaptation_set_hash if selection else None,
            run_name=spec.tracking.run_name,
            model_init=model_init,
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
        train_loader = make_loader(
            splits.source_train,
            spec,
            source=source,
            batch_size=spec.training.batch_size,
            train=True,
            drop_last=spec.data.loader.drop_last,
        )
        source_dev_loader = make_loader(
            splits.source_dev,
            spec,
            source=source,
            batch_size=eval_batch_size,
            train=False,
            seed_offset=101,
            drop_last=False,
            shuffle=False,
        )
        target_dev_loader = make_loader(
            splits.target_dev,
            spec,
            source=source,
            batch_size=eval_batch_size,
            train=False,
            seed_offset=202,
            drop_last=False,
            shuffle=False,
        )
        target_test_loader = make_loader(
            splits.target_test,
            spec,
            source=source,
            batch_size=eval_batch_size,
            train=False,
            seed_offset=303,
            drop_last=False,
            shuffle=False,
        )
        train_result = Trainer(
            model,
            strategy,
            {"train": train_loader},
            spec,
            tracker,
            limits,
            device,
        ).fit()

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
        source_dev_scores = (
            dev_scores
            if threshold_domain == "source"
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
        source_dev_eval = evaluate(source_dev_scores, threshold, spec, pv, status=final_status)
        test_eval = evaluate(test_scores, threshold, spec, pv, latency=latency, status=final_status)

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
                "train_result": {
                    "epochs_run": train_result.epochs_run,
                    "steps": train_result.steps,
                    "wall_clock_s": train_result.wall_clock_s,
                },
                "source_dev_metrics": source_dev_eval.metrics.model_dump(mode="json"),
            },
        )
        for artifact_path in _artifact_paths(run_dir):
            if artifact_path.name == "checkpoint.pt" and not spec.tracking.log_checkpoint:
                continue
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
                note=f"checkpoint={checkpoint_path.name}",
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
