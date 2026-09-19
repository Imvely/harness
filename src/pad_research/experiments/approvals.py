"""Human approval tokens for unattended full runs (ADR-005).

``experiments/approvals/<exp_id>.<science_hash[:12]>.json`` is written only by a person
running the approve_full_run script in their own terminal (Claude Code is denied). The
launch hook turns ``ask`` into ``allow`` when a matching token exists; the in-process gate
records ``approved_by``.
"""

from __future__ import annotations

import datetime as _dt
import getpass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pad_research import paths


class ApprovalToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    science_hash: str
    git_sha: str | None
    approved_at: str
    approved_by: str


def token_path(experiment_id: str, science_hash: str, approvals_dir: Path | None = None) -> Path:
    return (approvals_dir or paths.approvals_dir()) / f"{experiment_id}.{science_hash[:12]}.json"


def read_token(
    experiment_id: str, science_hash: str, approvals_dir: Path | None = None
) -> ApprovalToken | None:
    path = token_path(experiment_id, science_hash, approvals_dir)
    if not path.is_file():
        return None
    try:
        tok = ApprovalToken.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if tok.experiment_id != experiment_id or tok.science_hash != science_hash:
        return None
    return tok


def write_token(
    experiment_id: str, science_hash: str, git_sha: str | None, approvals_dir: Path | None = None
) -> Path:
    path = token_path(experiment_id, science_hash, approvals_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tok = ApprovalToken(
        experiment_id=experiment_id,
        science_hash=science_hash,
        git_sha=git_sha,
        approved_at=_dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds"),
        approved_by=getpass.getuser(),
    )
    path.write_text(tok.model_dump_json(indent=1) + "\n", encoding="utf-8")
    return path
