"""Building our own store: what it refuses to pack, and what it records about what it packs."""

from __future__ import annotations

from pathlib import Path

import pytest

from pad_research.data.build_store import (
    BuildError,
    DropReason,
    MemorySink,
    PaiGroup,
    allowed_pai,
    build_meta,
    build_records,
    check_output_root,
    estimate_bytes,
    frame_key,
    frames_per_class,
    plan_build,
    plan_report,
    unmapped_classes,
    write_store,
)
from pad_research.data.manifest import PAI, Label, MediaType, Split, manifest_hash
from pad_research.data.pai_map import PaiMappingError
from pad_research.data.sources.aihub_tree import SourceClip, scan_aihub_tree

# aihub115's measured shape: one camera recorded bona fide and the print cut-outs.
GOOD = {
    ("training", "0001", "SR305", "Light_01_High", "real_01"): 3,
    ("training", "0001", "SR305", "Light_01_High", "attack_01_print_eye_flat"): 2,
    ("validation", "0002", "SR305", "Light_03_Low", "real_01"): 2,
    ("validation", "0002", "SR305", "Light_03_Low", "attack_05_print_eye_nose_mouth_flat"): 2,
}
# aihub114's measured shape: attacks on the GoPro, bona fide on a phone.
CONFOUNDED = {
    ("training", "1302", "GOPRO", "Light_01_High", "attack_01_print_none_flat"): 3,
    ("training", "1302", "Galaxy Z Flip 5G", "Light_01_High", "real_01_phone"): 2,
}


def build_tree(root: Path, layout: dict[tuple[str, ...], int]) -> Path:
    for (purpose, subject, device, lighting, class_name), n_frames in layout.items():
        image_dir = root / purpose / subject / device / lighting / class_name / "color" / "image"
        image_dir.mkdir(parents=True)
        for index in range(1, n_frames + 1):
            (image_dir / f"{index}.jpg").write_bytes(f"{class_name}:{index}".encode())
    return root


def clip(**kwargs: object) -> SourceClip:
    defaults: dict[str, object] = {
        "subject_id": "0001",
        "split": Split.train,
        "class_name": "real_01",
        "capture_device": "SR305",
        "lighting": "Light_01_High",
        "rel_dir": "training/0001/SR305/Light_01_High/real_01/color/image",
        "frames": ("1.jpg",),
    }
    return SourceClip(**{**defaults, **kwargs})  # type: ignore[arg-type]


# -- the keep rule ---------------------------------------------------------------------


def test_a_camera_that_recorded_only_one_class_is_dropped_with_its_reason(tmp_path: Path) -> None:
    """The aihub114 case: no camera recorded both, so the plan is empty and says why."""
    clips = scan_aihub_tree(build_tree(tmp_path, CONFOUNDED))
    plan = plan_build(clips, "aihub114")
    assert plan.kept == ()
    assert plan.devices_recording_both == frozenset()
    assert plan.drop_counts() == {DropReason.camera_recorded_one_class.value: 2}


def test_a_camera_that_recorded_both_classes_is_kept(tmp_path: Path) -> None:
    plan = plan_build(scan_aihub_tree(build_tree(tmp_path, GOOD)), "aihub115")
    assert plan.devices_recording_both == {"SR305"}
    assert len(plan.kept) == 4
    assert plan.dropped == ()
    assert plan.classes_per_label() == {
        "bona_fide": ["real_01"],
        "spoof": ["attack_01_print_eye_flat", "attack_05_print_eye_nose_mouth_flat"],
    }


def test_the_rule_can_be_switched_off_for_a_domain_studied_on_purpose(tmp_path: Path) -> None:
    """Looking at a confounded domain is a decision, so it takes an argument, not a name test."""
    clips = scan_aihub_tree(build_tree(tmp_path, CONFOUNDED))
    plan = plan_build(clips, "aihub114", require_camera_recorded_both=False)
    assert len(plan.kept) == 2


def test_a_class_the_pai_table_does_not_cover_stops_the_plan() -> None:
    with pytest.raises(PaiMappingError):
        plan_build([clip(class_name="attack_99_new_thing")], "aihub115")
    assert unmapped_classes([clip(class_name="attack_99_new_thing")], "aihub115") == [
        "attack_99_new_thing"
    ]
    assert unmapped_classes([clip()], "aihub115") == []


def test_a_clip_with_no_frames_is_dropped_rather_than_packed_empty() -> None:
    plan = plan_build([clip(frames=())], "aihub115", require_camera_recorded_both=False)
    assert plan.drop_counts() == {DropReason.no_frames.value: 1}


# -- the attack-group switch ----------------------------------------------------------


def test_three_d_attacks_are_off_until_a_build_asks_for_them() -> None:
    """iBeta Level 1 is the target now; Level 2 turns the group on without new code."""
    assert PAI.mask_3d not in allowed_pai([PaiGroup.flat])
    assert PAI.mask_3d in allowed_pai([PaiGroup.flat, PaiGroup.three_d])
    # Bona fide is never switched off.
    assert PAI.none in allowed_pai([])

    clips = [
        clip(class_name="real_01_phone", capture_device="GOPRO"),
        clip(class_name="attack_01_print_none_flat", capture_device="GOPRO"),
        clip(class_name="attack_05_3d_mask", capture_device="GOPRO"),
    ]
    flat_only = plan_build(clips, "aihub114")
    assert {planned.clip.class_name for planned in flat_only.kept} == {
        "real_01_phone",
        "attack_01_print_none_flat",
    }
    assert flat_only.drop_counts() == {DropReason.pai_group_off.value: 1}

    with_masks = plan_build(clips, "aihub114", pai_groups=[PaiGroup.flat, PaiGroup.three_d])
    assert len(with_masks.kept) == 3
    assert with_masks.pai_groups == {PaiGroup.flat, PaiGroup.three_d}


def test_the_group_names_are_accepted_as_plain_strings_from_a_config() -> None:
    assert allowed_pai(["flat", "three_d"]) == allowed_pai([PaiGroup.flat, PaiGroup.three_d])
    with pytest.raises(ValueError, match="three-d"):
        allowed_pai(["three-d"])


# -- keys -----------------------------------------------------------------------------


def test_a_key_is_the_sample_id_and_a_zero_padded_index_so_byte_order_is_capture_order() -> None:
    keys = [frame_key("clipA", index) for index in (0, 1, 9, 10, 100)]
    assert keys[0] == "clipA/00000"
    assert keys == sorted(keys)
    with pytest.raises(ValueError, match="negative"):
        frame_key("clipA", -1)


def test_two_recordings_sharing_a_frame_name_do_not_share_a_key(tmp_path: Path) -> None:
    """What cost Replay-Attack 79,091 frames: same file name in two directories."""
    layout = {
        ("training", "0001", "SR305", "Light_01_High", "real_01"): 2,
        ("training", "0001", "SR305", "Light_02_Mid", "real_01"): 2,
        ("training", "0001", "SR305", "Light_01_High", "attack_01_print_eye_flat"): 2,
    }
    plan = plan_build(scan_aihub_tree(build_tree(tmp_path, layout)), "aihub115")
    keys = plan.frame_keys()
    assert len(keys) == len(set(keys)) == 6
    assert plan.duplicate_keys() == []


def test_a_duplicate_key_fails_the_build_before_anything_is_written(tmp_path: Path) -> None:
    build_tree(tmp_path, GOOD)
    plan = plan_build(scan_aihub_tree(tmp_path), "aihub115")
    # Two clips whose sample ids collide: the shape a path-derived key rules out, forced here.
    doubled = plan.__class__(
        dataset_id=plan.dataset_id,
        kept=plan.kept + plan.kept[:1],
        devices_recording_both=plan.devices_recording_both,
    )
    sink = MemorySink()
    with pytest.raises(BuildError, match="duplicate keys"):
        write_store(doubled, tmp_path, sink)
    assert sink.written == {}


def test_a_plan_with_nothing_in_it_fails_and_names_the_reason(tmp_path: Path) -> None:
    clips = scan_aihub_tree(build_tree(tmp_path, CONFOUNDED))
    plan = plan_build(clips, "aihub114")
    with pytest.raises(BuildError, match="camera_recorded_one_class"):
        write_store(plan, tmp_path, MemorySink())


# -- writing --------------------------------------------------------------------------


def test_frames_are_copied_byte_for_byte_in_capture_order(tmp_path: Path) -> None:
    source = build_tree(tmp_path / "src", GOOD)
    plan = plan_build(scan_aihub_tree(source), "aihub115")
    sink = MemorySink()
    records = write_store(plan, source, sink)

    assert len(sink.written) == plan.n_frames == 9
    bona_fide = next(r for r in records if r.split is Split.train and r.label is Label.bona_fide)
    written = [
        sink.written[key] for key in sorted(sink.written) if key.startswith(bona_fide.sample_id)
    ]
    assert written == [b"real_01:1", b"real_01:2", b"real_01:3"]


def test_the_source_tree_is_not_touched(tmp_path: Path) -> None:
    source = build_tree(tmp_path / "src", GOOD)
    before = {p: p.stat().st_mtime_ns for p in sorted(source.rglob("*")) if p.is_file()}
    write_store(plan_build(scan_aihub_tree(source), "aihub115"), source, MemorySink())
    after = {p: p.stat().st_mtime_ns for p in sorted(source.rglob("*")) if p.is_file()}
    assert after == before


def test_a_record_keeps_every_recording_condition_and_claims_no_timing(tmp_path: Path) -> None:
    source = build_tree(tmp_path / "src", GOOD)
    records = build_records(plan_build(scan_aihub_tree(source), "aihub115"))
    record = next(r for r in records if r.pai_detail == "attack_01_print_eye_flat")
    assert record.label is Label.spoof and record.pai is PAI.print
    assert record.capture_device == "SR305"
    assert record.environment == "Light_01_High"
    assert record.media_type is MediaType.frames_dir
    # The frames_dir is the key prefix its frames sit under.
    assert record.relative_path == record.sample_id
    assert record.n_frames == 2
    # Nothing in the tree says when a frame was taken.
    assert record.fps is None
    assert record.extra["time_source"] == "unknown"
    assert "dt_seconds" not in record.extra
    assert record.extra["source_rel_dir"].endswith("attack_01_print_eye_flat/color/image")


def test_a_documented_frame_rate_is_recorded_as_an_interval_when_one_is_known(
    tmp_path: Path,
) -> None:
    source = build_tree(tmp_path / "src", GOOD)
    records = build_records(
        plan_build(scan_aihub_tree(source), "aihub115"), time_source="documented", source_fps=30.0
    )
    assert records[0].fps == pytest.approx(30.0)
    assert records[0].extra["dt_seconds"] == pytest.approx(1.0 / 30.0, abs=1e-12)
    assert records[0].extra["time_source"] == "documented"


def test_the_records_are_a_valid_manifest_that_hashes(tmp_path: Path) -> None:
    source = build_tree(tmp_path / "src", GOOD)
    plan = plan_build(scan_aihub_tree(source), "aihub115")
    records = build_records(plan)
    assert manifest_hash(records) == manifest_hash(list(reversed(records)))
    meta = build_meta(
        plan,
        version="v1",
        license_="AI Hub research use",
        pii_policy="licensed_research",
        adapter="aihub115_ours",
    )
    assert meta["temporal_valid"] is False
    assert meta["dataset_id"] == "aihub115"


# -- planning before spending disk ----------------------------------------------------


def test_a_plan_prices_itself_from_directory_entries(tmp_path: Path) -> None:
    source = build_tree(tmp_path / "src", GOOD)
    plan = plan_build(scan_aihub_tree(source), "aihub115")
    expected = sum(p.stat().st_size for p in source.rglob("*.jpg"))
    assert estimate_bytes(plan, source) == expected
    report = plan_report(plan, source)
    assert report["estimated_bytes"] == expected
    assert report["n_frames"] == 9
    assert report["pai_groups"] == ["flat"]
    assert report["devices_recording_both"] == ["SR305"]


def test_frames_per_pai_are_the_sample_sizes_a_per_pai_apcer_will_rest_on(tmp_path: Path) -> None:
    source = build_tree(tmp_path / "src", GOOD)
    plan = plan_build(scan_aihub_tree(source), "aihub115")
    assert dict(frames_per_class(plan)) == {"none": 5, "print": 4}


# -- where a build may write ----------------------------------------------------------


def test_a_build_writes_only_under_our_own_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The raw trees sit on the same volume as a teammate's storage, which is read-only for us."""
    ours = tmp_path / "mine"
    ours.mkdir()
    monkeypatch.setenv("PAD_MY_ROOT", str(ours))
    assert (
        check_output_root(ours / "stores" / "aihub115") == (ours / "stores" / "aihub115").resolve()
    )
    with pytest.raises(BuildError, match="not under PAD_MY_ROOT"):
        check_output_root(tmp_path / "someone_else")

    monkeypatch.delenv("PAD_MY_ROOT")
    with pytest.raises(BuildError, match="PAD_MY_ROOT is not set"):
        check_output_root(ours)
