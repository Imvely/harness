"""scripts/inspect_lmdb_layout.py: the analysis, and a static proof that it only reads.

Everything here runs on plain Python values. No test in this file imports lmdb or pandas or
creates a store: the tool exists to be pointed at real face data, so what it may do to a store
is checked from its source, and what it concludes is checked on hand-built index rows.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "inspect_lmdb_layout.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("inspect_lmdb_layout", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


m = _load()


def _row(
    video_id: str,
    subject: str,
    *,
    cls: int = 0,
    split: str = "train",
    n: int = 3,
    keys: list[str] | None = None,
    boxes: Any = None,
    extra: dict[str, Any] | None = None,
    domain: str = "dom",
) -> dict[str, Any]:
    keys = keys if keys is not None else [f"{video_id}#{i:05d}" for i in range(n)]
    return {
        "video_id": video_id,
        "domain": domain,
        "subject_id": subject,
        "cls": cls,
        "sub_cls": "real" if cls == 0 else "print",
        "split": split,
        "lmdb_key": json.dumps(keys),
        "num_frames": n,
        "frame_bboxes": None if boxes is None else json.dumps(boxes),
        "extra_meta": json.dumps(extra or {}),
        "resolution": None,
    }


def _codes(findings: list[dict[str, Any]]) -> dict[str, str]:
    return {f["code"]: f["level"] for f in findings}


# ----------------------------------------------------------------------------- read-only proof

_FORBIDDEN_CALLS = {
    "put",
    "putmulti",
    "delete",
    "drop",
    "replace",
    "write_text",
    "write_bytes",
    "unlink",
    "rmdir",
    "mkdir",
    "makedirs",
    "rmtree",
    "remove",
    "rename",
    "to_parquet",
    "truncate",
    "touch",
    "system",
    "popen",
}
_FORBIDDEN_IMPORTS = {
    "shutil",
    "tempfile",
    "subprocess",
    "socket",
    "paramiko",
    "requests",
    "urllib",
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _keyword(node: ast.Call, name: str) -> Any:
    for kw in node.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return "<absent>"


def test_the_source_contains_no_call_that_writes_deletes_or_reaches_the_network() -> None:
    tree = ast.parse(SOURCE)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _FORBIDDEN_CALLS:
                offenders.append(f"line {node.lineno}: .{name}()")
            # The builtin open() is not used at all; files are read with Path.read_text.
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                offenders.append(f"line {node.lineno}: open()")
            for flag in ("write", "create", "lock"):
                if _keyword(node, flag) is True:
                    offenders.append(f"line {node.lineno}: {flag}=True")
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.split(".")[0] in _FORBIDDEN_IMPORTS]
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in _FORBIDDEN_IMPORTS
        ):
            offenders.append(node.module)
    assert offenders == []


def test_the_store_is_opened_read_only_without_a_lock_file_and_never_created() -> None:
    opens = [
        node
        for node in ast.walk(ast.parse(SOURCE))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "open"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "lmdb"
    ]
    assert len(opens) == 1
    call = opens[0]
    assert _keyword(call, "readonly") is True
    assert _keyword(call, "lock") is False
    assert _keyword(call, "create") is False


def test_every_transaction_is_explicitly_read_only() -> None:
    begins = [
        node
        for node in ast.walk(ast.parse(SOURCE))
        if isinstance(node, ast.Call) and _call_name(node) == "begin"
    ]
    assert begins, "the tool reads through transactions"
    assert all(_keyword(call, "write") is False for call in begins)


def test_the_tool_does_not_depend_on_this_repository() -> None:
    # It has to run on the data server, where pad_research is not installed.
    imported = set()
    for node in ast.walk(ast.parse(SOURCE)):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    third_party = imported - set(sys.stdlib_module_names) - {"__future__"}
    assert third_party == {"lmdb", "pandas", "cv2"}


# ----------------------------------------------------------------------------- pure helpers


def test_key_shape_replaces_digit_runs_with_their_width() -> None:
    assert m.key_shape("client001_session01_x#00012") == "client{3d}_session{2d}_x#{5d}"
    assert m.key_shape("no-digits") == "no-digits"


def test_expected_key_is_the_build_scripts_frame_key() -> None:
    assert m.expected_key("a/b/clip", 7) == "a/b/clip#00007"


@pytest.mark.parametrize(
    ("head", "name"),
    [
        (b"\xff\xd8\xff\xe0rest", "jpeg"),
        (b"\x89PNG\r\n\x1a\n....", "png"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp"),
        (b"\x00\x00\x00\x18ftypisom", "mp4"),
        (b"\x93NUMPY\x01\x00", "npy"),
        (b"plain text", "unknown"),
    ],
)
def test_sniff_format_names_the_container_from_magic_bytes(head: bytes, name: str) -> None:
    assert m.sniff_format(head) == name


def _jpeg(width: int, height: int) -> bytes:
    app0 = b"\xff\xe0" + (16).to_bytes(2, "big") + b"JFIF\x00" + bytes(9)
    sof0 = (
        b"\xff\xc0"
        + (17).to_bytes(2, "big")
        + b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + bytes(10)
    )
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"


def _png(width: int, height: int) -> bytes:
    ihdr = b"IHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes(5)
    return b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + ihdr + bytes(4)


def test_image_size_reads_dimensions_from_headers_after_other_segments() -> None:
    assert m.image_size(_jpeg(640, 480)) == (640, 480)
    assert m.image_size(_png(128, 96)) == (128, 96)
    assert m.image_size(b"\xff\xd8\xff") is None
    assert m.image_size(b"not an image") is None


def test_summarize_reports_order_statistics_and_none_for_nothing() -> None:
    assert m.summarize([]) is None
    stats = m.summarize([1.0, 2.0, 3.0, 4.0, 5.0])
    assert stats == {"n": 5, "min": 1.0, "p50": 3.0, "p90": 5.0, "max": 5.0, "mean": 3.0}


def test_box_jitter_is_zero_for_one_box_and_grows_with_movement() -> None:
    fixed = [[10, 10, 110, 110]] * 5
    assert m.box_jitter(fixed) == pytest.approx(0.0, abs=1e-12)
    moving = [[10 + 4 * i, 10, 110 + 4 * i, 110] for i in range(5)]
    assert m.box_jitter(moving) > 0.0
    assert m.box_jitter([[0, 0, 10, 10]]) is None
    assert m.box_jitter([[5, 5, 1, 1], "x"]) is None  # nothing valid


def test_build_config_loses_its_path_fields_but_says_which() -> None:
    kept = m.sanitize_build_config(
        {"data_root": "/srv/x", "dist_root": "/srv/y", "target_fps": 3.0, "datasets": ["a"]}
    )
    assert kept == {
        "target_fps": 3.0,
        "datasets": ["a"],
        "dropped_fields": ["data_root", "dist_root"],
    }
    assert "/srv" not in json.dumps(kept)


def test_nan_from_pandas_becomes_none() -> None:
    assert m._native(float("nan")) is None
    assert m._native(3) == 3


# ----------------------------------------------------------------------------- the index


def test_a_conforming_index_has_no_error_findings() -> None:
    rows = [
        _row("v1", "s1", split="train"),
        _row("v2", "s1", cls=1, split="train"),
        _row("v3", "s2", split="val"),
    ]
    section, findings, clip_keys = m.analyze_rows(rows, "dom")
    assert not [f for f in findings if f["level"] == "error"]
    assert section["lmdb_key"]["conformance"] == 1.0
    assert section["lmdb_key"]["n_keys"] == 9
    assert section["lmdb_key"]["shapes"] == {"v{1d}#{5d}": 9}
    assert section["subjects"] == {
        "n": 2,
        "clips_per_subject": m.summarize([2.0, 1.0]),
        "in_multiple_splits": 0,
        "with_both_classes": 1,
    }
    assert clip_keys[0] == ["v1#00000", "v1#00001", "v1#00002"]
    assert "NO_DEV_SPLIT" not in _codes(findings)


def test_a_repeated_video_id_is_an_error_because_its_frames_overwrite_each_other() -> None:
    rows = [_row("v1", "s1"), _row("v1", "s2")]
    codes = _codes(m.analyze_rows(rows, "dom")[1])
    assert codes["DUPLICATE_VIDEO_ID"] == "error"
    assert codes["DUPLICATE_LMDB_KEY"] == "error"


def test_key_count_and_pattern_deviations_are_reported() -> None:
    short = _row("v1", "s1", n=3, keys=["v1#00000", "v1#00001"])
    renamed = _row("v2", "s1", n=2, keys=["v2/0", "v2/1"])
    codes = _codes(m.analyze_rows([short, renamed], "dom")[1])
    assert codes["KEY_COUNT_MISMATCH"] == "error"
    assert codes["KEY_PATTERN_DEVIATION"] == "warn"


def test_an_unparseable_key_cell_leaves_that_clip_without_keys() -> None:
    bad = _row("v1", "s1")
    bad["lmdb_key"] = "not json"
    _, findings, clip_keys = m.analyze_rows([bad, _row("v2", "s1")], "dom")
    assert _codes(findings)["LMDB_KEY_UNPARSEABLE"] == "error"
    assert clip_keys[0] == []
    assert len(clip_keys[1]) == 3


def test_split_facts_that_adr_008_depends_on_are_reported() -> None:
    rows = [_row("v1", "s1", split="train"), _row("v2", "s1", split="test")]
    codes = _codes(m.analyze_rows(rows, "dom")[1])
    assert codes["SUBJECT_IN_MULTIPLE_SPLITS"] == "warn"
    assert codes["NO_DEV_SPLIT"] == "info"


def test_per_clip_attack_subjects_are_flagged() -> None:
    # One subject id per attack clip: nobody has both classes.
    rows = [_row("live1", "p1"), _row("atk1", "atk1", cls=1), _row("atk2", "atk2", cls=1)]
    assert _codes(m.analyze_rows(rows, "dom")[1])["SUBJECTS_SINGLE_CLASS"] == "info"


def test_boxes_are_measured_and_a_count_mismatch_is_reported() -> None:
    steady = _row("v1", "s1", n=3, boxes=[[0, 0, 100, 100]] * 3)
    short = _row("v2", "s1", n=3, boxes=[[0, 0, 100, 100]] * 2)
    none = _row("v3", "s1", n=3)
    section, findings, _ = m.analyze_rows([steady, short, none], "dom")
    boxes = section["frame_bboxes"]
    assert boxes["n_rows_null"] == 1
    assert boxes["n_rows_count_mismatch"] == 1
    assert boxes["clip_jitter"]["max"] == pytest.approx(0.0, abs=1e-12)
    assert _codes(findings)["BBOX_COUNT_MISMATCH"] == "warn"


def test_extra_meta_values_are_shown_only_when_few() -> None:
    rows = [_row(f"v{i}", "s1", extra={"target_fps": 3.0, "session": str(i)}) for i in range(12)]
    keys = m.analyze_rows(rows, "dom")[0]["extra_meta"]["keys"]
    assert keys["target_fps"] == {"rows": 12, "values": {"3.0": 12}}
    assert keys["session"] == {"rows": 12, "n_distinct": 12}


def test_a_domain_column_that_disagrees_with_the_directory_is_reported() -> None:
    rows = [_row("v1", "s1", domain="other")]
    assert _codes(m.analyze_rows(rows, "dom")[1])["DOMAIN_COLUMN_MISMATCH"] == "warn"


def test_clips_without_a_recorded_frame_rate_are_reported() -> None:
    rows = [_row("v1", "s1", extra={"target_fps": 3.0}), _row("v2", "s1")]
    section, findings, _ = m.analyze_rows(rows, "dom")
    assert section["frame_rate"] == {"key": "target_fps", "n_rows_recorded": 1}
    assert _codes(findings)["FRAME_RATE_NOT_RECORDED"] == "info"
    everything = [_row("v1", "s1", extra={"target_fps": 3.0})]
    assert "FRAME_RATE_NOT_RECORDED" not in _codes(m.analyze_rows(everything, "dom")[1])


# ----------------------------------------------------------------------------- the frame cache


def test_frames_dropped_between_extraction_and_the_store_are_counted() -> None:
    rows = [_row("full", "s1", n=9), _row("gappy", "s2", n=6), _row("nocache", "s3", n=5)]
    section, findings = m.compare_with_cache(rows, {"full": 9, "gappy": 9}, set(), "dom")
    assert section["n_clips_matched"] == 2
    assert section["n_clips_with_drops"] == 1
    assert section["n_frames_dropped"] == 3
    assert section["kept_ratio"]["min"] == pytest.approx(6 / 9, abs=1e-4)
    assert _codes(findings) == {"FRAMES_DROPPED_AFTER_EXTRACTION": "warn"}


def test_a_cache_smaller_than_the_store_is_inconsistent_and_duplicates_are_skipped() -> None:
    rows = [_row("more", "s1", n=10), _row("twice", "s2", n=3)]
    section, findings = m.compare_with_cache(rows, {"more": 4}, {"twice"}, "dom")
    assert section["n_clips_ambiguous"] == 1
    assert section["n_clips_stored_more_than_extracted"] == 1
    assert _codes(findings) == {"CACHE_INCONSISTENT": "warn"}


def test_an_unrelated_cache_is_reported_as_unmatched() -> None:
    _, findings = m.compare_with_cache([_row("v1", "s1")], {"other": 5}, set(), "dom")
    assert _codes(findings) == {"CACHE_UNMATCHED": "info"}


def test_scan_frame_cache_counts_frames_by_folder_name(tmp_path: Path) -> None:
    root = tmp_path / "_frames" / "dom"
    layout = {"train/real/clipA": 3, "test/attack/hand/clipB": 2, "a/dup": 1, "b/dup": 1}
    for folder, n in layout.items():
        (root / folder).mkdir(parents=True)
        for i in range(n):
            (root / folder / f"frame_{i:05d}.jpg").write_bytes(b"")
    (root / "train/real/clipA/notes.txt").write_bytes(b"")
    folders, ambiguous = m.scan_frame_cache(tmp_path, "dom")
    assert ambiguous == {"dup"}
    assert folders == {
        "clipA": m.CachedClip(
            "train/real/clipA", ("frame_00000.jpg", "frame_00001.jpg", "frame_00002.jpg")
        ),
        "clipB": m.CachedClip("test/attack/hand/clipB", ("frame_00000.jpg", "frame_00001.jpg")),
    }
    assert m.scan_frame_cache(tmp_path, "absent") is None


# ----------------------------------------------------------------------------- the time axis


@pytest.mark.parametrize(
    ("source_fps", "hop", "rate"),
    [(30.0, 10, 3.0), (25.0, 8, 3.125), (29.97, 10, 2.997), (20.0, 7, 2.857), (2.0, 1, 2.0)],
)
def test_extraction_hop_reproduces_the_builds_arithmetic(
    source_fps: float, hop: int, rate: float
) -> None:
    # The build: hop_interval = max(1, round(video_fps / target_fps)), target 3 fps.
    assert m.extraction_hop(source_fps, 3.0) == hop
    assert round(source_fps / hop, 3) == rate


def test_stored_frames_are_matched_to_cache_positions_in_order() -> None:
    cached = ["a", "b", "c", "d", "e", "f"]
    assert m.match_cache_positions(["a", "b", "c"], cached) == [0, 1, 2]
    assert m.match_cache_positions(["a", "c", "f"], cached) == [0, 2, 5]
    assert m.match_cache_positions(["b", "zz", "d"], cached) == [1, None, 3]
    # Order is respected: a digest seen earlier in the cache is not matched backwards.
    assert m.match_cache_positions(["d", "a"], cached) == [3, None]


def test_extraction_gaps_are_steps_between_found_positions() -> None:
    assert m.extraction_gaps([0, 1, 2]) == [1, 1]
    assert m.extraction_gaps([0, 2, 5]) == [2, 3]
    assert m.extraction_gaps([1, None, 3]) == [2]
    assert m.extraction_gaps([4]) == []


def test_timing_tally_turns_gaps_into_seconds_with_the_source_rate() -> None:
    tally = m.TimingTally()
    # 25 fps source, 3 fps target: hop 8, one step = 0.32 s. Frame 2 was dropped.
    tally.add([0, 1, 3], n_cached=4, target_fps=3.0, source_fps=25.0, source_frames=30)
    tally.add([0, 1, 2], n_cached=3, target_fps=3.0, source_fps=30.0, source_frames=30)
    section = tally.to_dict()
    assert section["n_clips"] == 2
    assert section["n_clips_irregular"] == 1
    assert section["pairs_one_step_apart"] == 0.75
    assert section["hop"] == {"8": 1, "10": 1}
    assert section["effective_rate_fps"] == {"3.125": 1, "3.000": 1}
    seconds = section["seconds_between_frames"]
    assert seconds["min"] == pytest.approx(0.32, abs=1e-4)
    assert seconds["max"] == pytest.approx(0.64, abs=1e-4)
    assert section["n_cache_inconsistent_with_hop"] == 0


def test_a_cache_that_the_recorded_rate_cannot_produce_is_flagged() -> None:
    tally = m.TimingTally()
    # 300 source frames at hop 10 give 30 cached frames, not 100.
    tally.add([0, 1], n_cached=100, target_fps=3.0, source_fps=30.0, source_frames=300)
    section = tally.to_dict()
    assert section["n_cache_inconsistent_with_hop"] == 1
    codes = _codes(m.timing_findings(section, "dom"))
    assert codes["CACHE_HOP_MISMATCH"] == "warn"
    assert codes["EFFECTIVE_FRAME_RATE"] == "info"


def test_without_source_headers_gaps_are_still_counted_in_steps() -> None:
    tally = m.TimingTally()
    tally.add([0, 3, None], n_cached=5, target_fps=3.0, source_fps=None, source_frames=None)
    section = tally.to_dict()
    assert section["gap_steps"]["max"] == 3.0
    assert section["seconds_between_frames"] is None
    assert section["effective_rate_fps"] == {}
    codes = _codes(m.timing_findings(section, "dom"))
    assert codes == {"IRREGULAR_FRAME_SPACING": "warn", "STORED_FRAMES_NOT_IN_CACHE": "warn"}


def test_the_source_video_is_found_by_mirroring_the_cache_path(tmp_path: Path) -> None:
    folder = tmp_path / "dom" / "train" / "real"
    folder.mkdir(parents=True)
    (folder / "client001_x.MOV").write_bytes(b"")
    (folder / "client001_x.txt").write_bytes(b"")
    found = m.find_source_video(tmp_path, "dom", "train/real/client001_x")
    assert found is not None and found.name == "client001_x.MOV"
    assert m.find_source_video(tmp_path, "dom", "train/real/absent") is None
    assert m.find_source_video(tmp_path, "dom", "nowhere/clip") is None


def test_digest_is_a_stable_fingerprint() -> None:
    assert m.digest(b"frame") == m.digest(b"frame")
    assert m.digest(b"frame") != m.digest(b"frame2")
    assert len(m.digest(b"")) == 32


# ----------------------------------------------------------------------------- store tallies


def test_key_tally_compares_the_store_against_the_index() -> None:
    tally = m.KeyTally({"v1#00000", "v1#00001", "v2#00000"})
    for key in ("v1#00000", "v1#00001", "stray#00000", "odd-key"):
        tally.add(key)
    tally.add_undecodable()
    section = tally.to_dict(entries=5, complete=True)
    assert section["n_index_keys_found"] == 2
    assert section["n_index_keys_missing"] == 1
    assert section["n_orphan_keys"] == 2
    assert section["n_undecodable_keys"] == 1
    assert section["index_widths"] == {"5": 3}
    assert section["separator_ratio"] == 0.75


def test_an_incomplete_scan_makes_no_exact_claims() -> None:
    tally = m.KeyTally({"v1#00000"})
    tally.add("v1#00000")
    section = tally.to_dict(entries=10, complete=False)
    assert "n_index_keys_missing" not in section
    assert "n_orphan_keys" not in section


def test_value_tally_reads_headers_and_counts_missing() -> None:
    tally = m.ValueTally()
    tally.add(_jpeg(320, 240))
    tally.add(_jpeg(320, 240))
    tally.add_missing()
    section = tally.to_dict()
    assert section["n_probed"] == 3
    assert section["n_missing"] == 1
    assert section["formats"] == {"jpeg": 2}
    assert section["dimensions"] == {"320x240": 2}


def test_store_findings_turn_measurements_into_verdicts() -> None:
    keys = {"n_index_keys_missing": 4, "n_orphan_keys": 2, "scan_complete": True}
    values = {"n_missing": 1, "n_probed": 9, "formats": {"jpeg": 7, "unknown": 1}}
    codes = _codes(m.store_findings(keys, values, ["v{1d}#{5d}"], "dom"))
    assert codes == {
        "INDEX_KEYS_MISSING_FROM_STORE": "error",
        "ORPHAN_KEYS_IN_STORE": "warn",
        "PROBED_KEYS_MISSING": "error",
        "VALUE_FORMATS": "warn",
    }


def test_probing_spreads_across_the_index_and_takes_first_middle_last() -> None:
    assert m.spread_indices(100, 4) == [0, 25, 50, 75]
    assert m.spread_indices(3, 10) == [0, 1, 2]
    assert m.spread_indices(0, 5) == []
    clips = [[f"c{i}#{j:05d}" for j in range(5)] for i in range(4)] + [[]]
    keys = m.probe_keys(clips, 2)
    assert keys == ["c0#00000", "c0#00002", "c0#00004", "c2#00000", "c2#00002", "c2#00004"]


def test_the_text_report_names_findings_and_no_paths() -> None:
    section, findings, _ = m.analyze_rows([_row("v1", "s1"), _row("v1", "s2")], "dom")
    report = {
        "tool_version": m.TOOL_VERSION,
        "build_config": m.sanitize_build_config({"dist_root": "/srv/pad", "target_fps": 3.0}),
        "unpaired": {"stores_without_index": [], "indexes_without_store": ["legacy"]},
        "domains": [{"name": "dom", "index": section, "findings": findings}],
        "findings": findings,
    }
    text = m.render_text(report)
    assert "== dom ==" in text
    assert "[ERROR] DUPLICATE_VIDEO_ID" in text
    assert "indexes without a store: legacy" in text
    assert "/srv" not in text
