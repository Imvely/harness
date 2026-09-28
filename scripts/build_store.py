#!/usr/bin/env python3
"""Plan, price and (only when asked) write our own frame store from a raw dataset tree.

Runs in three steps, and stops after the first two unless ``--write`` is given:

1. **Scan** the source tree read-only and list its clips.
2. **Plan** what would be packed, why everything else would not, and how much disk it needs.
3. **Write** the frames into a new LMDB under our own root, plus the manifest beside it.

Step 3 is opt-in because a build costs hundreds of gigabytes and hours (ADR-016 names capacity
as the thing to check first). Without ``--write`` nothing is created anywhere.

The source tree is only ever read. The output must sit under the directory named by
``PAD_MY_ROOT``, so a mistyped argument cannot reach a teammate's storage.

    # look first: what would be packed, and how big is it?
    python scripts/build_store.py --dataset aihub115 --source-root "$SRC/aihub115"

    # then pack it
    python scripts/build_store.py --dataset aihub115 --source-root "$SRC/aihub115" \
        --out-root "$PAD_MY_ROOT/stores" --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from pad_research.data.build_store import (  # noqa: E402
    DEFAULT_PAI_GROUPS,
    BuildError,
    PaiGroup,
    build_meta,
    check_output_root,
    estimate_bytes,
    frames_per_class,
    plan_build,
    plan_report,
    unmapped_classes,
    write_store,
)
from pad_research.data.manifest import write_manifest  # noqa: E402
from pad_research.data.sources.aihub_tree import scan_aihub_tree  # noqa: E402

#: How each dataset's source tree is read. A dataset absent here has no scanner yet, which is a
#: clearer failure than a scanner guessing at a layout it has never seen.
SCANNERS = {
    "aihub114": scan_aihub_tree,
    "aihub115": scan_aihub_tree,
}
#: License and PII policy per dataset, as the distribution states them. Both AI Hub sets are
#: Korean-residents-only research data: a copy carries the same restriction and never leaves.
DATASET_TERMS = {
    "aihub114": ("AI Hub 168 (research use, Korean residents only)", "licensed_research"),
    "aihub115": ("AI Hub 161 (research use, Korean residents only)", "licensed_research"),
}


def human(n_bytes: int) -> str:
    size = float(n_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"  # pragma: no cover - unreachable, the loop returns at TB


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dataset", required=True, choices=sorted(SCANNERS), help="which source tree this is"
    )
    parser.add_argument("--source-root", required=True, type=Path, help="the raw tree; read only")
    parser.add_argument(
        "--out-root", type=Path, help="where the store goes; must be under PAD_MY_ROOT"
    )
    parser.add_argument(
        "--pai-groups",
        default=",".join(sorted(group.value for group in DEFAULT_PAI_GROUPS)),
        help="attack families to pack, comma separated: flat, three_d, on_face. "
        "Level 1 targets flat; adding three_d is what a Level 2 build changes.",
    )
    parser.add_argument(
        "--keep-single-class-cameras",
        action="store_true",
        help="pack clips from cameras that recorded only one class. Off by default: such a "
        "camera predicts the label by itself and no metric shows it.",
    )
    parser.add_argument("--version", default="v1", help="dataset version recorded in the manifest")
    parser.add_argument("--report", type=Path, help="write the plan report to this JSON file")
    parser.add_argument("--write", action="store_true", help="actually create the store")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_root = args.source_root.expanduser()
    if not source_root.is_dir():
        print(f"source root not found: {source_root}", file=sys.stderr)
        return 2
    groups = [PaiGroup(name.strip()) for name in args.pai_groups.split(",") if name.strip()]

    clips = SCANNERS[args.dataset](source_root)
    print(f"scanned {len(clips)} clips under {source_root.name}")
    missing = unmapped_classes(clips, args.dataset)
    if missing:
        print(f"no PAI mapping for: {missing}", file=sys.stderr)
        print("add them to data/pai_map.py; nothing is guessed here", file=sys.stderr)
        return 3

    plan = plan_build(
        clips,
        args.dataset,
        pai_groups=groups,
        require_camera_recorded_both=not args.keep_single_class_cameras,
    )
    payload = estimate_bytes(plan, source_root)
    report = plan_report(plan)
    report["estimated_bytes"] = payload
    report["frames_per_pai"] = dict(frames_per_class(plan))
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"\n{len(plan.kept)} clips, {plan.n_frames} frames, about {human(payload)}")
    if args.report:
        args.report.expanduser().write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        print(f"plan written to {args.report}")

    if not plan.kept:
        print("\nnothing to pack. The drop reasons above say why.", file=sys.stderr)
        return 4
    if not args.write:
        print("\nplan only. Re-run with --write --out-root <dir under PAD_MY_ROOT> to build.")
        return 0
    if args.out_root is None:
        print("--write needs --out-root", file=sys.stderr)
        return 2

    # Imported here so a plan-only run needs no LMDB driver at all.
    from pad_research.data.storage.lmdb_writer import LmdbSink, map_size_for

    out_root = check_output_root(args.out_root)
    store_path = out_root / f"{args.dataset}.lmdb"
    license_, pii_policy = DATASET_TERMS[args.dataset]

    done = 0

    def progress(_planned: object) -> None:
        nonlocal done
        done += 1
        if done % 100 == 0 or done == len(plan.kept):
            print(f"  {done}/{len(plan.kept)} clips", flush=True)

    print(f"\nwriting {store_path}")
    with LmdbSink(store_path, map_size=map_size_for(payload)) as sink:
        records = write_store(plan, source_root, sink, on_clip=progress)
        n_written = sink.n_written

    meta = write_manifest(
        records,
        build_meta(
            plan,
            version=args.version,
            license_=license_,
            pii_policy=pii_policy,
            adapter=f"{args.dataset}_ours",
        ),
        out_root / "manifests",
    )
    print(f"wrote {n_written} frames, {meta.n_records} records, {meta.n_subjects} subjects")
    print(f"manifest_hash {meta.manifest_hash}")
    print(f"splits {meta.splits}")
    print(f"pai_counts {meta.pai_counts}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as error:
        print(f"build refused: {error}", file=sys.stderr)
        raise SystemExit(5) from None
