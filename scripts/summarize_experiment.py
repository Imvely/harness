#!/usr/bin/env python
"""Generate a contract §44 Markdown report from MLflow run artifacts."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

from pad_research.config.schema import TrackingSpec
from pad_research.errors import ProtocolMismatchError
from pad_research.reporting.report import generate_report, load_runs
from pad_research.tracking.mlflow_tracker import MlflowTracker


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--baseline-experiment-id", default=None)
    parser.add_argument("--justify", default=None)
    parser.add_argument("--include-smoke", action="store_true")
    parser.add_argument(
        "--mlflow-experiment",
        default="pad-report",
        help="Placeholder experiment name; run lookup searches all MLflow experiments.",
    )
    parser.add_argument("-o", "--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    tracker = MlflowTracker(TrackingSpec(mlflow_experiment=args.mlflow_experiment), Path.cwd())
    try:
        method = load_runs(args.experiment_id, include_smoke=args.include_smoke, tracker=tracker)
        baseline = (
            load_runs(
                args.baseline_experiment_id, include_smoke=args.include_smoke, tracker=tracker
            )
            if args.baseline_experiment_id is not None
            else None
        )
        bundle = generate_report(method, baseline, args.output, justify=args.justify)
    except ProtocolMismatchError as exc:
        print(f"protocol mismatch: {exc}", file=sys.stderr)
        return 6
    except Exception as exc:
        print(f"report generation failed: {exc}", file=sys.stderr)
        return 1
    print(f"report={bundle.report_path} per_attack_csv={bundle.per_attack_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
