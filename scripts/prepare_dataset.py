#!/usr/bin/env python
"""Build dataset manifests (and, for synthetic adapters, the media itself).

Example::

    PAD_DATA_ROOT=$PWD/data/processed uv run --no-sync python scripts/prepare_dataset.py \
        --adapter synthetic --dataset-id synthetic_a --dataset-id synthetic_b

The script is idempotent: re-running it over unchanged data leaves the manifest files
byte-identical. It never imports torch.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from pad_research import paths
except ModuleNotFoundError:  # package not installed (fresh clone): fall back to src/
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from pad_research import paths

from pad_research.data.adapters.base import ADAPTERS, get_adapter
from pad_research.data.manifest import write_manifest


def _default_root() -> Path:
    env = os.environ.get("PAD_DATA_ROOT")
    if env:
        return Path(env).expanduser()
    return paths.repo_root() / "data" / "processed"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--adapter", default="synthetic", choices=sorted(ADAPTERS), help="adapter name"
    )
    parser.add_argument(
        "--dataset-id",
        dest="dataset_ids",
        action="append",
        required=True,
        help="dataset id to build (repeatable)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="media root (default: $PAD_DATA_ROOT, else <repo>/data/processed)",
    )
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=None,
        help="where to write <id>.jsonl / <id>.meta.json (default: <repo>/data/manifests)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root: Path = args.root if args.root is not None else _default_root()
    manifests_dir: Path = (
        args.manifests_dir if args.manifests_dir is not None else paths.manifests_dir()
    )
    root.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    for dataset_id in args.dataset_ids:
        adapter = get_adapter(args.adapter, dataset_id=dataset_id)
        records = adapter.build(root)
        meta = write_manifest(records, adapter.meta_partial(), manifests_dir)
        print(
            f"dataset_id={meta.dataset_id} n_records={meta.n_records} "
            f"manifest_hash={meta.manifest_hash}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
