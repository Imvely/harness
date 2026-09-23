"""The build CLI: it looks before it writes, and it writes only where it is allowed to."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_store.py"

GOOD = {
    ("training", "0001", "SR305", "Light_01_High", "real_01"): 3,
    ("training", "0001", "SR305", "Light_01_High", "attack_01_print_eye_flat"): 2,
}
CONFOUNDED = {
    ("training", "1302", "GOPRO", "Light_01_High", "attack_01_print_none_flat"): 2,
    ("training", "1302", "Galaxy Z Flip 5G", "Light_01_High", "real_01_phone"): 2,
}


def build_tree(root: Path, layout: dict[tuple[str, ...], int]) -> Path:
    for (purpose, subject, device, lighting, class_name), n_frames in layout.items():
        image_dir = root / purpose / subject / device / lighting / class_name / "color" / "image"
        image_dir.mkdir(parents=True)
        for index in range(1, n_frames + 1):
            (image_dir / f"{index}.jpg").write_bytes(f"{class_name}:{index}".encode())
    return root


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PYTHONPATH": str(SCRIPT.parents[1] / "src")}
    # Never inherit the caller's own output root: where a build may write is part of the test.
    environment.pop("PAD_MY_ROOT", None)
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=environment,
    )


def test_a_plan_only_run_prices_the_build_and_creates_nothing(tmp_path: Path) -> None:
    source = build_tree(tmp_path / "src", GOOD)
    report = tmp_path / "plan.json"
    result = run("--dataset", "aihub115", "--source-root", str(source), "--report", str(report))
    assert result.returncode == 0, result.stderr
    assert "plan only" in result.stdout
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["n_clips_kept"] == 2
    assert written["n_frames"] == 5
    assert written["devices_recording_both"] == ["SR305"]
    assert written["estimated_bytes"] > 0
    assert written["frames_per_pai"] == {"none": 3, "print": 2}
    # Nothing beyond the report exists.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["plan.json", "src"]


def test_a_tree_where_no_camera_recorded_both_classes_ends_without_a_store(tmp_path: Path) -> None:
    """aihub114. The command fails loudly rather than packing a confounded domain."""
    source = build_tree(tmp_path / "src", CONFOUNDED)
    result = run("--dataset", "aihub114", "--source-root", str(source))
    assert result.returncode == 4
    assert "nothing to pack" in result.stderr
    assert "camera_recorded_one_class" in result.stdout


def test_the_switch_that_studies_a_confounded_domain_on_purpose(tmp_path: Path) -> None:
    source = build_tree(tmp_path / "src", CONFOUNDED)
    result = run(
        "--dataset",
        "aihub114",
        "--source-root",
        str(source),
        "--keep-single-class-cameras",
    )
    assert result.returncode == 0, result.stderr
    assert '"n_clips_kept": 2' in result.stdout


def test_three_d_attacks_join_the_plan_only_when_the_group_is_named(tmp_path: Path) -> None:
    layout = {
        ("training", "0001", "SR305", "Light_01_High", "real_01_phone"): 2,
        ("training", "0001", "SR305", "Light_01_High", "attack_01_print_none_flat"): 2,
        ("training", "0001", "SR305", "Light_01_High", "attack_05_3d_mask"): 2,
    }
    source = build_tree(tmp_path / "src", layout)
    flat = run("--dataset", "aihub114", "--source-root", str(source))
    assert '"pai_group_off": 1' in flat.stdout
    both = run(
        "--dataset", "aihub114", "--source-root", str(source), "--pai-groups", "flat,three_d"
    )
    assert '"mask_3d": 2' in both.stdout


def test_writing_outside_our_own_root_is_refused(tmp_path: Path) -> None:
    source = build_tree(tmp_path / "src", GOOD)
    mine = tmp_path / "mine"
    mine.mkdir()
    result = run(
        "--dataset",
        "aihub115",
        "--source-root",
        str(source),
        "--out-root",
        str(tmp_path / "someone_else"),
        "--write",
        env={"PAD_MY_ROOT": str(mine)},
    )
    assert result.returncode == 5
    assert "not under PAD_MY_ROOT" in result.stderr
    assert not (tmp_path / "someone_else").exists()


def test_a_full_build_writes_the_store_and_a_manifest_beside_it(tmp_path: Path) -> None:
    pytest.importorskip("lmdb")
    source = build_tree(tmp_path / "src", GOOD)
    mine = tmp_path / "mine"
    mine.mkdir()
    result = run(
        "--dataset",
        "aihub115",
        "--source-root",
        str(source),
        "--out-root",
        str(mine / "stores"),
        "--write",
        env={"PAD_MY_ROOT": str(mine)},
    )
    assert result.returncode == 0, result.stderr
    assert "wrote 5 frames, 2 records, 1 subjects" in result.stdout
    assert "manifest_hash" in result.stdout
    store = mine / "stores" / "aihub115.lmdb"
    assert (store / "data.mdb").is_file()
    manifest = mine / "stores" / "manifests" / "aihub115.jsonl"
    assert len(manifest.read_text(encoding="utf-8").strip().splitlines()) == 2
    meta = json.loads((mine / "stores" / "manifests" / "aihub115.meta.json").read_text("utf-8"))
    assert meta["pai_counts"] == {"none": 1, "print": 1}
    assert meta["temporal_valid"] is False
    assert meta["pii_policy"] == "licensed_research"
