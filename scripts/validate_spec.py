#!/usr/bin/env python
"""Validate (and optionally freeze / gate) an experiment spec: ``--exp NAME [-- OVERRIDES]``.

Exit codes: 0 ok, 2 spec/compose error, 3 protocol error, 4 gate denied, 5 internal.
Never imports torch or mlflow. Used by the Claude Code launch hook with ``--for-launch --json``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

from pad_research.experiments.validator import validate_spec
from pad_research.utils.redaction import redact_text


def _parse(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exp", required=True, help="experiment name (configs/exp/<name>.yaml)")
    ap.add_argument("--for-launch", action="store_true", help="also evaluate the full-run gate")
    ap.add_argument(
        "--freeze", action="store_true", help="write experiments/specs/<id>.resolved.yaml"
    )
    ap.add_argument(
        "--approval-optional",
        action="store_true",
        help=(
            "for hook/approval tooling: evaluate all launch-gate checks but do not fail solely "
            "because the human approval token is missing"
        ),
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--config-dir", type=Path, default=None, help="extra Hydra search path (tests)")
    if "--" in argv:
        i = argv.index("--")
        return ap.parse_args(argv[:i]), argv[i + 1 :]
    return ap.parse_args(argv), []


def main(argv: list[str] | None = None) -> int:
    args, overrides = _parse(sys.argv[1:] if argv is None else argv)
    try:
        report = validate_spec(
            [f"+exp={args.exp}", *overrides],
            for_launch=args.for_launch,
            freeze=args.freeze,
            extra_config_dir=args.config_dir,
            require_approval=not args.approval_optional,
        )
    except Exception as exc:  # pragma: no cover - defensive
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "exit_code": 5,
                        "errors": [redact_text(repr(exc))],
                        "warnings": [],
                    }
                )
            )
        else:
            print(f"internal error: {redact_text(repr(exc))}", file=sys.stderr)
        return 5
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=True))
    else:
        print(
            f"experiment={report.experiment_id} mode={report.mode} ok={report.ok} "
            f"science_hash={(report.science_hash or '')[:12]} protocol={report.protocol_id} "
            f"protocol_hash={(report.protocol_hash or '')[:12]} approval_token={report.approval_token_ok}"
        )
        for e in report.errors:
            print(f"  [error] {e}")
        for w in report.warnings:
            print(f"  [warning] {w}")
        if report.frozen_path:
            print(f"  frozen: {report.frozen_path}")
        if report.gate is not None:
            print(f"  gate: allowed={report.gate['allowed']} checks={report.gate['checks']}")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
