#!/usr/bin/env python
"""Answer "can this machine read this dataset?" before a run is queued, not after it dies.

    uv run --no-sync python scripts/check_storage.py --storage lmdb --dataset-id oulu_npu
    uv run --no-sync python scripts/check_storage.py --exp ocim_i_e01_frame_source_only

``--storage`` reads ``configs/storage/<name>.yaml`` on its own, which is the fast form while
someone is still getting their environment variables right. ``--exp`` composes the whole
experiment and checks the storage block it would actually use, against every dataset its
protocol names — the form that answers "will this run work".

Exit codes: 0 every check passed, 1 a check failed, 2 the configuration could not be read.
Never imports torch or mlflow, so it stays usable on a machine that has not synced yet.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

from pad_research import paths
from pad_research.data.storage.config import StorageConfig
from pad_research.data.storage.diagnose import DEFAULT_PROBE, StorageDiagnosis, diagnose_storage
from pad_research.utils.redaction import redact_text

_STORAGE = TypeAdapter(StorageConfig)

_SYMBOL = {"pass": "OK  ", "fail": "FAIL", "skip": "SKIP"}


def _storage_from_file(name: str, config_dir: Path) -> StorageConfig:
    path = config_dir / "storage" / f"{name}.yaml"
    if not path.is_file():
        available = sorted(p.stem for p in (config_dir / "storage").glob("*.yaml"))
        raise FileNotFoundError(f"no storage config named {name!r}; available: {available}")
    return _STORAGE.validate_python(yaml.safe_load(path.read_text(encoding="utf-8")))


def _from_experiment(exp: str, config_dir: Path) -> tuple[StorageConfig, list[str], Path]:
    """Return the experiment's storage block, the datasets it reads, and its manifests dir."""
    from pad_research.config.compose import compose_spec

    _, spec = compose_spec([f"+exp={exp}"], config_dir=config_dir)
    datasets = [*spec.protocol.source_datasets, *spec.protocol.target_dataset]
    return spec.storage, datasets, paths.repo_root() / spec.data.manifests_dir


def _render(report: StorageDiagnosis, dataset_id: str | None) -> list[str]:
    title = f"storage={report.storage_kind}"
    if dataset_id:
        title += f" dataset={dataset_id}"
    lines = [f"{title}  ->  {'OK' if report.ok else 'FAILED'}"]
    for check in report.checks:
        lines.append(f"  [{_SYMBOL[check.status]}] {check.name}")
        if check.detail:
            lines.append(f"         {check.detail}")
        if check.remedy and check.status != "pass":
            lines.append(f"         fix: {check.remedy}")
    return lines


def _env_help(report: StorageDiagnosis) -> list[str]:
    if report.ok or not report.env_vars:
        return []
    return [
        "",
        "This backend is configured by environment variables. Set them in the shell that",
        "launches the run (values are never written into configs/, which is committed):",
        *(f"  export {name}=..." for name in report.env_vars),
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--storage", help="a name under configs/storage/ (local, lmdb, sftp)")
    source.add_argument("--exp", help="an experiment name; uses its storage block and datasets")
    ap.add_argument(
        "--dataset-id",
        action="append",
        default=None,
        help="check media for this dataset (repeatable). Without it only the backend is checked.",
    )
    ap.add_argument("--probe", type=int, default=DEFAULT_PROBE, help="records to read per dataset")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--config-dir", type=Path, default=None, help="Hydra config dir (tests)")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    config_dir = args.config_dir or paths.configs_dir()
    manifests_dir = paths.manifests_dir()
    datasets: list[str | None] = list(args.dataset_id or [])

    try:
        if args.exp:
            config, from_protocol, manifests_dir = _from_experiment(args.exp, config_dir)
            datasets = datasets or list(from_protocol)
        else:
            config = _storage_from_file(args.storage, config_dir)
    except (FileNotFoundError, ValidationError, yaml.YAMLError) as exc:
        message = redact_text(str(exc), paths.repo_root())
        print(json.dumps({"ok": False, "error": message}) if args.json else f"error: {message}")
        return 2

    # Without a dataset the diagnosis still runs once, to answer "is the backend reachable".
    reports = [
        diagnose_storage(config, manifests_dir=manifests_dir, dataset_id=dataset, probe=args.probe)
        for dataset in (datasets or [None])
    ]
    ok = all(report.ok for report in reports)

    if args.json:
        print(json.dumps({"ok": ok, "reports": [r.model_dump(mode="json") for r in reports]}))
        return 0 if ok else 1

    lines: list[str] = []
    for report in reports:
        lines += _render(report, report.dataset_id)
    lines += _env_help(reports[0])
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
