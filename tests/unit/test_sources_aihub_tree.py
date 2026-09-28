"""Reading an AI Hub tree: every recording condition kept, and the camera/label question."""

from __future__ import annotations

from pathlib import Path

from pad_research.data.manifest import Split
from pad_research.data.sources.aihub_tree import (
    SourceClip,
    classes_per_device,
    devices_recording_both,
    scan_aihub_tree,
)

# The shape measured in the lab's copy on 2026-09-23: attacks on the GoPro, bona fide on a
# phone and a tablet, three lighting conditions each.
TREE = {
    ("training", "1302", "GOPRO", "Light_01_High", "attack_01_print_none_flat"): 3,
    ("training", "1302", "GOPRO", "Light_02_Mid", "attack_01_print_none_flat"): 3,
    ("training", "1302", "Galaxy Z Flip 5G", "Light_01_High", "real_01_phone"): 2,
    (
        "training",
        "1302",
        "[PAD] iPad Pro 4th Generation 11 WiFi (256GB)",
        "Light_01_High",
        "real_01_tablet",
    ): 2,
    ("validation", "1500", "GOPRO", "Light_03_Low", "attack_03_replay_phone"): 4,
}


def build_tree(root: Path, layout: dict[tuple[str, ...], int] = TREE) -> Path:
    for (purpose, subject, device, lighting, class_name), n_frames in layout.items():
        image_dir = root / purpose / subject / device / lighting / class_name / "color" / "image"
        image_dir.mkdir(parents=True)
        # Not zero-padded, as in the real tree.
        for index in range(1, n_frames + 1):
            (image_dir / f"{index}.jpg").write_bytes(b"")
        (image_dir / "1.json").write_bytes(b"{}")  # the per-frame label file sits alongside
    return root


def test_every_recording_condition_survives_the_scan(tmp_path: Path) -> None:
    clips = scan_aihub_tree(build_tree(tmp_path))
    assert len(clips) == len(TREE)
    lightings = {clip.lighting for clip in clips}
    assert lightings == {"Light_01_High", "Light_02_Mid", "Light_03_Low"}
    devices = {clip.capture_device for clip in clips}
    assert "GOPRO" in devices and any(device.startswith("[PAD]") for device in devices)


def test_frames_come_back_in_capture_order_not_lexicographic(tmp_path: Path) -> None:
    layout = {("training", "s1", "GOPRO", "Light_01_High", "attack_01_print_none_flat"): 12}
    clips = scan_aihub_tree(build_tree(tmp_path, layout))
    assert clips[0].frames[:3] == ("1.jpg", "2.jpg", "3.jpg")
    assert clips[0].frames[-1] == "12.jpg"
    # Only images; the label JSON beside them is not a frame.
    assert all(name.endswith(".jpg") for name in clips[0].frames)


def test_validation_is_the_dev_split_because_a_threshold_may_be_fitted_on_it(
    tmp_path: Path,
) -> None:
    clips = scan_aihub_tree(build_tree(tmp_path))
    assert {clip.split for clip in clips} == {Split.train, Split.dev}


def test_a_sample_id_comes_from_the_path_so_two_recordings_cannot_collide(tmp_path: Path) -> None:
    clips = scan_aihub_tree(build_tree(tmp_path))
    ids = [clip.sample_id for clip in clips]
    assert len(set(ids)) == len(ids)
    # Device names carry spaces and brackets; a sample id may not.
    assert all(id_.replace("_", "").replace("-", "").replace(".", "").isalnum() for id_ in ids)
    same_class_two_devices = {
        clip.sample_id for clip in clips if clip.class_name.startswith("real_01")
    }
    assert len(same_class_two_devices) == 2


def test_it_reports_when_no_camera_recorded_both_classes(tmp_path: Path) -> None:
    """The aihub114 case, which decides whether the domain can back a claim at all."""
    clips = scan_aihub_tree(build_tree(tmp_path))
    bona_fide = {"real_01_phone", "real_01_tablet"}
    assert devices_recording_both(clips, bona_fide) == set()
    per_device = classes_per_device(clips)
    assert per_device["GOPRO"] == {"attack_01_print_none_flat", "attack_03_replay_phone"}


def test_a_camera_that_recorded_both_is_found(tmp_path: Path) -> None:
    layout = {
        ("training", "s1", "SR305", "Light_02_Mid", "real_01"): 2,
        ("training", "s1", "SR305", "Light_02_Mid", "attack_01_print_eye_flat"): 2,
        ("training", "s1", "KINECT", "Light_02_Mid", "real_01"): 2,
    }
    clips = scan_aihub_tree(build_tree(tmp_path, layout))
    assert devices_recording_both(clips, {"real_01"}) == {"SR305"}


def test_an_empty_or_missing_directory_is_skipped_rather_than_failing(tmp_path: Path) -> None:
    root = build_tree(tmp_path)
    empty = (
        root / "training" / "1302" / "GOPRO" / "Light_01_High" / "attack_09_new" / "color" / "image"
    )
    empty.mkdir(parents=True)
    (root / "training" / "1302" / "GOPRO" / "Light_01_High" / "no_color_dir").mkdir()
    clips = scan_aihub_tree(root)
    assert len(clips) == len(TREE)
    assert all(isinstance(clip, SourceClip) for clip in clips)
