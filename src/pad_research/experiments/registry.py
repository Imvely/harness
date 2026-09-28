"""Local, append-only run index (``experiments/registry.jsonl``; gitignored).

MLflow is the source of truth; the registry is a derived index readable without mlflow
(session summaries, the ``SMOKE_OK`` gate) that also records pre-run failures (invalid
spec/protocol, blocked by gate) which never reach MLflow (contract §35).
"""

from __future__ import annotations

import datetime as _dt
import importlib
import os
from pathlib import Path
from typing import Any, TextIO

from pydantic import BaseModel, ConfigDict

from pad_research import paths
from pad_research.experiments.status import RunStatus
from pad_research.utils.canonical_json import canonical_json

_fcntl: Any | None = importlib.import_module("fcntl") if os.name == "posix" else None
_msvcrt: Any | None = importlib.import_module("msvcrt") if os.name == "nt" else None
_WINDOWS_LOCK_BYTES = 1


class RegistryRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exp_id: str
    seed: int | None
    mode: str
    science_hash: str | None
    spec_hash: str | None
    protocol_id: str | None
    protocol_hash: str | None
    adaptation_set_hash: str | None = None
    mlflow_run_id: str | None = None
    status: RunStatus
    git_sha: str | None
    git_dirty: bool
    started_at: str
    finished_at: str | None = None
    results_dir: str | None = None
    note: str | None = None


def utc_now() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


def _lock_file(fh: TextIO) -> None:
    if _fcntl is not None:
        _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
        return
    if _msvcrt is not None:
        fh.seek(0)
        _msvcrt.locking(fh.fileno(), _msvcrt.LK_LOCK, _WINDOWS_LOCK_BYTES)


def _unlock_file(fh: TextIO) -> None:
    if _fcntl is not None:
        _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
        return
    if _msvcrt is not None:
        fh.seek(0)
        _msvcrt.locking(fh.fileno(), _msvcrt.LK_UNLCK, _WINDOWS_LOCK_BYTES)


class Registry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.registry_path()

    def append(self, row: RegistryRow) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = canonical_json(row.model_dump(mode="json")) + "\n"
        with open(self.path, "a+", encoding="utf-8") as fh:
            _lock_file(fh)
            try:
                fh.seek(0, os.SEEK_END)
                fh.write(line)
                fh.flush()
            finally:
                _unlock_file(fh)

    def rows(self) -> list[RegistryRow]:
        if not self.path.is_file():
            return []
        return [
            RegistryRow.model_validate_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def find_runs(
        self,
        *,
        exp_id: str | None = None,
        protocol_hash: str | None = None,
        science_hash: str | None = None,
        mode: str | None = None,
        status: set[RunStatus] | None = None,
    ) -> list[RegistryRow]:
        return [
            r
            for r in self.rows()
            if (exp_id is None or r.exp_id == exp_id)
            and (protocol_hash is None or r.protocol_hash == protocol_hash)
            and (science_hash is None or r.science_hash == science_hash)
            and (mode is None or r.mode == mode)
            and (status is None or r.status in status)
        ]

    def latest_success_smoke(self, science_hash: str, git_sha: str | None) -> RegistryRow | None:
        rows = self.find_runs(science_hash=science_hash, mode="smoke", status={RunStatus.smoke_ok})
        if git_sha is not None:
            rows = [r for r in rows if r.git_sha == git_sha]
        return rows[-1] if rows else None
