#!/usr/bin/env python
"""Export MLflow/registry runs into dashboard JSON."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

from pad_research import paths
from pad_research.config.schema import TrackingSpec
from pad_research.dashboard.export import (
    export_dashboard_bundle,
    load_dashboard_records,
    write_dashboard_bundle,
)
from pad_research.experiments.registry import Registry
from pad_research.experiments.status import RunStatus
from pad_research.tracking.mlflow_tracker import MlflowTracker

_REPORTABLE = {
    RunStatus.smoke_ok,
    RunStatus.success,
    RunStatus.security_regression,
    RunStatus.inconclusive,
}


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment-id",
        action="append",
        default=[],
        help="Experiment ID to export. Repeat to export multiple experiments.",
    )
    parser.add_argument("--include-smoke", action="store_true")
    parser.add_argument(
        "--mlflow-experiment",
        default="pad-dashboard",
        help="Placeholder experiment name. Run lookup searches all MLflow experiments.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("web-mockup/public/dashboard-demo.json"),
    )
    return parser.parse_args(argv)


def _registry_experiment_ids() -> list[str]:
    rows = Registry().rows()
    exp_ids = {
        row.exp_id
        for row in rows
        if row.mlflow_run_id is not None and row.status in _REPORTABLE and row.exp_id
    }
    return sorted(exp_ids)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    experiment_ids = list(dict.fromkeys(args.experiment_id or _registry_experiment_ids()))
    tracker = MlflowTracker(
        TrackingSpec(mlflow_experiment=args.mlflow_experiment), paths.repo_root()
    )
    records = load_dashboard_records(
        experiment_ids,
        include_smoke=args.include_smoke,
        tracker=tracker,
    )
    bundle = export_dashboard_bundle(records, repo_root=paths.repo_root())
    output = write_dashboard_bundle(bundle, args.output)
    print(f"dashboard_json={output} runs={len(bundle.runs)} experiments={len(experiment_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
