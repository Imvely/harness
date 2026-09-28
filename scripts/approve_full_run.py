#!/usr/bin/env python
"""Human-only: approve a FULL run of ``--exp NAME`` (ADR-005, ADR-011).

Run this in YOUR terminal. Claude Code is denied from running it (permissions + hook DG-12).
Whichever form you choose, the approval is bound to the experiment's ``science_hash``, so it
covers this scientific configuration and nothing else: change the protocol, the model or the
seed and the approval stops applying by itself.

    python scripts/approve_full_run.py --exp NAME
        Writes experiments/approvals/<exp_id>.<science12>.json (gitignored) and prints where.
        Valid for 24 hours by default; --ttl-hours changes that and --no-expiry restores the
        pre-ADR-011 behaviour of never expiring.

    python scripts/approve_full_run.py --exp NAME --print
        Writes nothing. Prints a signed one-line token, valid for two hours, that you export
        in the shell you launch from:

            export PAD_APPROVAL_TOKEN=pad1....
            uv run --no-sync python scripts/train.py +exp=NAME

        Needs a signing key once, created by --init-key. Keep the token to yourself: anything
        that can read it can launch THIS experiment until it expires.

Either way every other gate still applies (freeze, smoke, clean tree, GPU, tracking).
Exit codes: 0 approved, 2 not a full-run experiment, 3 another gate check failed, 4 no key.
"""

from __future__ import annotations

import argparse
import sys

from pad_research import paths
from pad_research.experiments.approvals import (
    DEFAULT_FILE_TTL_HOURS,
    DEFAULT_TTL_MINUTES,
    ApprovalKeyMissingError,
    create_key,
    key_path,
    mint_pasteable,
    write_token,
)
from pad_research.experiments.validator import validate_spec
from pad_research.utils.git import git_state


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exp", help="experiment name (configs/exp/<name>.yaml)")
    ap.add_argument(
        "--print",
        dest="print_token",
        action="store_true",
        help="print a paste-able token instead of writing an approvals file",
    )
    ap.add_argument(
        "--ttl-minutes",
        type=float,
        default=DEFAULT_TTL_MINUTES,
        help=f"lifetime of a --print token (default {DEFAULT_TTL_MINUTES:g})",
    )
    ap.add_argument(
        "--ttl-hours",
        type=float,
        default=DEFAULT_FILE_TTL_HOURS,
        help=f"lifetime of a file approval (default {DEFAULT_FILE_TTL_HOURS:g})",
    )
    ap.add_argument(
        "--no-expiry",
        action="store_true",
        help="file approvals only: never expire (the behaviour before ADR-011)",
    )
    ap.add_argument(
        "--init-key",
        action="store_true",
        help="create the signing key used by --print, then exit",
    )
    args = ap.parse_args()

    if args.init_key:
        path = create_key()
        print(f"signing key ready at {path} (keep it out of the repository and off backups)")
        return 0
    if not args.exp:
        ap.error("--exp is required unless --init-key is given")

    report = validate_spec([f"+exp={args.exp}"], for_launch=True, require_approval=False)
    if report.mode != "full":
        print("refusing: the experiment file is not in execution.mode=full", file=sys.stderr)
        return 2
    if not report.ok:
        print("refusing: validation/gate failed:", file=sys.stderr)
        for e in report.errors:
            print(f"  {e}", file=sys.stderr)
        return 3
    assert report.experiment_id and report.science_hash
    git_sha = git_state(paths.repo_root()).sha

    if args.print_token:
        try:
            token = mint_pasteable(
                report.experiment_id,
                report.science_hash,
                git_sha,
                ttl_minutes=args.ttl_minutes,
            )
        except ApprovalKeyMissingError as exc:
            print(f"refusing: {exc}", file=sys.stderr)
            print(f"  (the key would live at {key_path()})", file=sys.stderr)
            return 4
        print(
            f"approved {report.experiment_id} science_hash={report.science_hash[:12]} "
            f"for {args.ttl_minutes:g} minutes. Run this in the launching shell:"
        )
        print()
        print(f"  export PAD_APPROVAL_TOKEN={token}")
        return 0

    path = write_token(
        report.experiment_id,
        report.science_hash,
        git_sha,
        ttl_hours=None if args.no_expiry else args.ttl_hours,
    )
    lifetime = "no expiry" if args.no_expiry else f"{args.ttl_hours:g}h"
    print(
        f"approved {report.experiment_id} science_hash={report.science_hash[:12]} "
        f"({lifetime}) -> {path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
