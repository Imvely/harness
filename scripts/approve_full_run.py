#!/usr/bin/env python
"""Human-only: approve an unattended FULL run of ``--exp NAME`` (ADR-005).

Run this in YOUR terminal. Claude Code is denied from running it (permissions + hook DG-12).
It records who approved which science_hash at which commit in
``experiments/approvals/<exp_id>.<science12>.json`` (gitignored). The launch hook then
allows the run without a prompt; the in-process gate still applies every other check.
"""

from __future__ import annotations

import argparse
import sys

from pad_research import paths
from pad_research.experiments.approvals import write_token
from pad_research.experiments.validator import validate_spec
from pad_research.utils.git import git_state


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exp", required=True)
    args = ap.parse_args()
    report = validate_spec([f"+exp={args.exp}"], for_launch=True)
    if report.mode != "full":
        print("refusing: the experiment file is not in execution.mode=full", file=sys.stderr)
        return 2
    if not report.ok:
        print("refusing: validation/gate failed:", file=sys.stderr)
        for e in report.errors:
            print(f"  {e}", file=sys.stderr)
        return 3
    assert report.experiment_id and report.science_hash
    path = write_token(report.experiment_id, report.science_hash, git_state(paths.repo_root()).sha)
    print(f"approved {report.experiment_id} science_hash={report.science_hash[:12]} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
