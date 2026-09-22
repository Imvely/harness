#!/usr/bin/env python
"""Report the layout of a clip-level video PAD LMDB store, without changing anything in it.

    python inspect_lmdb_layout.py --dist-root <DIST_ROOT> --no-lmdb          # index only
    python inspect_lmdb_layout.py --dist-root <DIST_ROOT> --json > report.json

The Phase 1 adapter has to map an existing store onto manifest records, and contract section
27.2 forbids writing it from a guess. The build code says what the store *should* look like;
this reports what it *does* look like, so the adapter is written against measurements.

What it expects, from the build script that produced the stores (read, never run): under
``DIST_ROOT`` each domain is an LMDB directory ``<name>/`` next to ``<name>_meta.parquet``.
The parquet is the index, one row per clip, and its ``lmdb_key`` column is a JSON list of that
clip's frame keys, ``<video_id>#<index:05d>``, each holding one encoded frame. Nothing here
assumes that is true; every part of it is measured and deviations are reported as findings.

Read-only by construction, and a unit test checks the source for it:

* the LMDB is opened ``readonly=True, lock=False, create=False``: no write transaction, no
  lock file, no directory created when a path is wrong;
* the only file reads are the parquet index, ``build_config.json`` and the LMDB itself, plus
  a listing of file *names* under ``_frames/<domain>/`` (the build's cache of frames
  extracted from video) to count how many frames were dropped before reaching the store;
* nothing is written anywhere. The report goes to stdout; redirect it if you want a file.

It is also safe to paste. No path, host or pixel reaches the report: a domain is named by its
directory name, ``build_config.json`` loses its path fields, a frame is summarised by format,
byte size and pixel dimensions read from the header, and keys are shown as shapes
(``client{3d}_session{2d}#{5d}``) unless ``--examples`` asks for literal ones.

Self-contained on purpose: stdlib plus ``lmdb`` and ``pandas`` (with pyarrow or fastparquet),
which the environment that built the stores already has. It does not import ``pad_research``,
so it runs on the data server without installing this repository. Python 3.10 or newer.

Exit codes: 0 no error-level finding, 1 at least one, 2 nothing could be read.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

TOOL_VERSION = 1

PARQUET_SUFFIX = "_meta.parquet"
#: Columns the build script writes. ``source_paths`` is collected at build time but never
#: written to the parquet, so it is deliberately absent here.
PARQUET_COLUMNS = (
    "video_id",
    "domain",
    "subject_id",
    "cls",
    "sub_cls",
    "split",
    "lmdb_key",
    "num_frames",
    "frame_bboxes",
    "extra_meta",
    "resolution",
)
KEY_SEPARATOR = "#"
KEY_INDEX_WIDTH = 5
#: build_config.json fields that describe the build. The others hold machine paths.
BUILD_CONFIG_KEYS = ("target_fps", "num_frames", "bbox_margin", "datasets")
#: Splits a threshold can be fitted on (ADR-008).
DEV_LIKE_SPLITS = frozenset({"dev", "val", "devel", "validation"})
#: The extra_meta field in which the build records the extraction frame rate.
FRAME_RATE_KEY = "target_fps"
#: Where the build caches frames extracted from video, before face detection drops some.
FRAME_CACHE_DIR = "_frames"
CACHE_FRAME_SUFFIX = ".jpg"

DEFAULT_PROBE = 24
DEFAULT_SCAN_LIMIT = 2_000_000
#: Upper bound on point lookups spent finding examples of index keys missing from the store.
MISSING_LOOKUP_BUDGET = 200_000
MAX_DISTINCT_SHOWN = 10
TOP_SHAPES = 10
TOP_SUB_CLS = 30

_DIGIT_RUN = re.compile(r"\d+")
_JPEG_SOF = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class InspectError(RuntimeError):
    """Something could not be read. The message never contains a path."""


# ----------------------------------------------------------------------------- findings


def finding(level: str, code: str, detail: str, domain: str | None = None) -> dict[str, Any]:
    """One observation. ``level`` is ``error`` (the adapter cannot rely on this), ``warn``
    (it can, with care) or ``info`` (a fact a decision depends on)."""
    item: dict[str, Any] = {"level": level, "code": code, "detail": detail}
    if domain is not None:
        item["domain"] = domain
    return item


# ----------------------------------------------------------------------------- pure helpers


def key_shape(key: str) -> str:
    """Replace every digit run with its width: ``client001#00012`` -> ``client{3d}#{5d}``.

    A shape says how a key is built without saying whose clip it is, and it is exactly what a
    parser needs: where the separators are and how wide the numbers are.
    """
    return _DIGIT_RUN.sub(lambda match: f"{{{len(match.group())}d}}", key)


def expected_key(video_id: str, index: int) -> str:
    """The frame key the build script writes for frame ``index`` of ``video_id``."""
    return f"{video_id}{KEY_SEPARATOR}{index:0{KEY_INDEX_WIDTH}d}"


def sniff_format(data: bytes) -> str:
    """Name the container from its magic bytes. Nothing is decoded."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(_PNG_SIGNATURE):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return "avi"
    if data[4:8] == b"ftyp":
        return "mp4"
    if data.startswith(b"\x93NUMPY"):
        return "npy"
    if data.startswith(b"BM"):
        return "bmp"
    if data.startswith(b"GIF8"):
        return "gif"
    return "unknown"


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    # Walk the marker segments to the first start-of-frame; its header holds height, width.
    i, n = 2, len(data)
    while i + 3 < n:
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:  # markers without a length
            i += 2
            continue
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        if marker in _JPEG_SOF:
            if i + 9 > n:
                return None
            height = int.from_bytes(data[i + 5 : i + 7], "big")
            width = int.from_bytes(data[i + 7 : i + 9], "big")
            return width, height
        if length < 2:
            return None
        i += 2 + length
    return None


def image_size(data: bytes) -> tuple[int, int] | None:
    """Return ``(width, height)`` from a JPEG or PNG header, or ``None``. No pixel is decoded."""
    if data.startswith(_PNG_SIGNATURE) and data[12:16] == b"IHDR" and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        return _jpeg_size(data)
    return None


def summarize(values: Sequence[float]) -> dict[str, float] | None:
    """Order statistics of ``values``; ``None`` when there are none."""
    if not values:
        return None
    ordered = sorted(values)
    last = len(ordered) - 1

    def at(fraction: float) -> float:
        return ordered[min(last, round(fraction * last))]

    return {
        "n": len(ordered),
        "min": round(ordered[0], 4),
        "p50": round(at(0.5), 4),
        "p90": round(at(0.9), 4),
        "max": round(ordered[-1], 4),
        "mean": round(statistics.fmean(ordered), 4),
    }


def parse_json_cell(value: Any) -> tuple[bool, Any]:
    """Decode a JSON-in-a-string parquet cell. ``(False, None)`` when it is not valid JSON."""
    if value is None or isinstance(value, (list, dict)):
        return True, value
    if isinstance(value, str):
        try:
            return True, json.loads(value)
        except ValueError:
            return False, None
    return False, None


def _is_box(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
        and value[2] > value[0]
        and value[3] > value[1]
    )


def box_jitter(boxes: Iterable[Any]) -> float | None:
    """How far a clip's per-frame face box wanders, relative to the box size.

    The spread of the box centres (root of the summed variances) divided by the median box
    side. ``0.0`` means one box for the whole clip. This is the quantity ADR-009 worries about:
    a clip cropped with a different box per frame acquires motion the face never made.
    ``None`` with fewer than two valid boxes.
    """
    valid = [b for b in boxes if _is_box(b)]
    if len(valid) < 2:
        return None
    centre_x = [(b[0] + b[2]) / 2 for b in valid]
    centre_y = [(b[1] + b[3]) / 2 for b in valid]
    side = statistics.median(max(b[2] - b[0], b[3] - b[1]) for b in valid)
    spread = math.sqrt(statistics.pvariance(centre_x) + statistics.pvariance(centre_y))
    return spread / side


def _counts(values: Iterable[Any]) -> dict[str, int]:
    return {str(k): v for k, v in Counter(str(v) for v in values).most_common()}


def sanitize_build_config(config: dict[str, Any]) -> dict[str, Any]:
    """Keep what describes the build; name, but drop, the fields that are machine paths."""
    kept = {key: config[key] for key in BUILD_CONFIG_KEYS if key in config}
    dropped = sorted(key for key in config if key not in BUILD_CONFIG_KEYS)
    if dropped:
        kept["dropped_fields"] = dropped
    return kept


# ----------------------------------------------------------------------------- the index


def analyze_rows(
    rows: Sequence[dict[str, Any]], domain: str
) -> tuple[dict[str, Any], list[dict[str, Any]], list[list[str]]]:
    """Measure one domain's parquet index.

    Returns the report section, its findings, and each row's frame keys (an empty list where
    the ``lmdb_key`` cell could not be parsed), aligned with ``rows``.
    """
    findings: list[dict[str, Any]] = []
    columns = set(rows[0]) if rows else set()
    missing_columns = [c for c in PARQUET_COLUMNS if c not in columns]
    if rows and missing_columns:
        findings.append(
            finding("error", "PARQUET_MISSING_COLUMNS", ", ".join(missing_columns), domain)
        )

    domain_values = _counts(row.get("domain") for row in rows)
    if rows and set(domain_values) != {domain}:
        findings.append(
            finding(
                "warn",
                "DOMAIN_COLUMN_MISMATCH",
                f"domain column holds {sorted(domain_values)}, directory is {domain!r}",
                domain,
            )
        )

    # -- identity and keys -------------------------------------------------------------
    video_counts = Counter(str(row.get("video_id")) for row in rows)
    duplicated_ids = sum(1 for n in video_counts.values() if n > 1)
    if duplicated_ids:
        findings.append(
            finding(
                "error",
                "DUPLICATE_VIDEO_ID",
                f"{duplicated_ids} video_id values occur on more than one row; the build "
                "writes frame keys from video_id, so their frames overwrite each other",
                domain,
            )
        )

    clip_keys: list[list[str]] = []
    n_unparseable = n_count_mismatch = n_nonconforming = 0
    all_keys: Counter[str] = Counter()
    for row in rows:
        ok, keys = parse_json_cell(row.get("lmdb_key"))
        if not ok or not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            n_unparseable += 1
            clip_keys.append([])
            continue
        clip_keys.append(keys)
        all_keys.update(keys)
        num_frames = row.get("num_frames")
        if isinstance(num_frames, int) and len(keys) != num_frames:
            n_count_mismatch += 1
        video_id = str(row.get("video_id"))
        n_nonconforming += sum(1 for i, key in enumerate(keys) if key != expected_key(video_id, i))

    n_keys = sum(all_keys.values())
    n_duplicate_keys = n_keys - len(all_keys)
    if n_unparseable:
        findings.append(finding("error", "LMDB_KEY_UNPARSEABLE", f"{n_unparseable} rows", domain))
    if n_count_mismatch:
        findings.append(
            finding(
                "error",
                "KEY_COUNT_MISMATCH",
                f"{n_count_mismatch} rows list a different number of keys than num_frames",
                domain,
            )
        )
    if n_duplicate_keys:
        findings.append(
            finding(
                "error",
                "DUPLICATE_LMDB_KEY",
                f"{n_duplicate_keys} frame keys are listed by more than one row",
                domain,
            )
        )
    if n_nonconforming:
        findings.append(
            finding(
                "warn",
                "KEY_PATTERN_DEVIATION",
                f"{n_nonconforming} of {n_keys} keys are not "
                f"<video_id>{KEY_SEPARATOR}<{KEY_INDEX_WIDTH}-digit index>",
                domain,
            )
        )

    # -- subjects, labels and splits ---------------------------------------------------
    splits_of: dict[str, set[str]] = {}
    classes_of: dict[str, set[str]] = {}
    for row in rows:
        subject = str(row.get("subject_id"))
        splits_of.setdefault(subject, set()).add(str(row.get("split")))
        classes_of.setdefault(subject, set()).add(str(row.get("cls")))
    clips_per_subject = Counter(str(row.get("subject_id")) for row in rows)
    in_multiple_splits = sum(1 for s in splits_of.values() if len(s) > 1)
    with_both_classes = sum(1 for c in classes_of.values() if len(c) > 1)

    split_counts = _counts(row.get("split") for row in rows)
    class_counts = _counts(row.get("cls") for row in rows)
    if in_multiple_splits and len(split_counts) > 1:
        findings.append(
            finding(
                "warn",
                "SUBJECT_IN_MULTIPLE_SPLITS",
                f"{in_multiple_splits} subjects appear in more than one split",
                domain,
            )
        )
    if rows and not DEV_LIKE_SPLITS & set(split_counts):
        findings.append(
            finding(
                "info",
                "NO_DEV_SPLIT",
                f"splits present: {sorted(split_counts)}; a dev set must be derived (ADR-008)",
                domain,
            )
        )
    if len(class_counts) > 1 and splits_of and with_both_classes == 0:
        findings.append(
            finding(
                "info",
                "SUBJECTS_SINGLE_CLASS",
                "no subject_id has both bona fide and attack clips; subject-disjoint splitting "
                "cannot keep one person's real and attack clips together",
                domain,
            )
        )

    # -- per-frame boxes (ADR-009) -----------------------------------------------------
    n_box_null = n_box_mismatch = n_box_invalid = 0
    jitters: list[float] = []
    for row, keys in zip(rows, clip_keys, strict=True):
        ok, boxes = parse_json_cell(row.get("frame_bboxes"))
        if not ok or boxes is None:
            n_box_null += 1
            continue
        if not isinstance(boxes, list):
            n_box_invalid += 1
            continue
        if keys and len(boxes) != len(keys):
            n_box_mismatch += 1
        n_box_invalid += sum(1 for b in boxes if not _is_box(b))
        jitter = box_jitter(boxes)
        if jitter is not None:
            jitters.append(jitter)
    if n_box_mismatch:
        findings.append(
            finding(
                "warn",
                "BBOX_COUNT_MISMATCH",
                f"{n_box_mismatch} rows have a different number of boxes than frame keys",
                domain,
            )
        )

    # -- extra_meta: keys, and values only where they are few ---------------------------
    extra_values: dict[str, Counter[str]] = {}
    n_extra_unparseable = 0
    n_with_frame_rate = 0
    for row in rows:
        ok, meta = parse_json_cell(row.get("extra_meta"))
        if not ok or not isinstance(meta, (dict, type(None))):
            n_extra_unparseable += 1
            continue
        if FRAME_RATE_KEY in (meta or {}):
            n_with_frame_rate += 1
        for key, value in (meta or {}).items():
            extra_values.setdefault(str(key), Counter())[json.dumps(value, sort_keys=True)] += 1
    if rows and n_with_frame_rate < len(rows):
        findings.append(
            finding(
                "info",
                "FRAME_RATE_NOT_RECORDED",
                f"{len(rows) - n_with_frame_rate} of {len(rows)} clips carry no "
                f"{FRAME_RATE_KEY}; the time between their frames is not known from the store",
                domain,
            )
        )
    extra_meta: dict[str, Any] = {}
    for key, counter in sorted(extra_values.items()):
        entry: dict[str, Any] = {"rows": sum(counter.values())}
        if len(counter) <= MAX_DISTINCT_SHOWN:
            entry["values"] = dict(counter.most_common())
        else:
            entry["n_distinct"] = len(counter)
        extra_meta[key] = entry

    num_frames_values = [
        float(row["num_frames"]) for row in rows if isinstance(row.get("num_frames"), int)
    ]
    section: dict[str, Any] = {
        "n_rows": len(rows),
        "columns": {
            "missing": missing_columns if rows else [],
            "extra": sorted(columns - set(PARQUET_COLUMNS)),
        },
        "domain_values": domain_values,
        "cls": class_counts,
        "sub_cls": dict(list(_counts(row.get("sub_cls") for row in rows).items())[:TOP_SUB_CLS]),
        "n_sub_cls": len({str(row.get("sub_cls")) for row in rows}),
        "split": split_counts,
        "subjects": {
            "n": len(clips_per_subject),
            "clips_per_subject": summarize([float(n) for n in clips_per_subject.values()]),
            "in_multiple_splits": in_multiple_splits,
            "with_both_classes": with_both_classes,
        },
        "num_frames": summarize(num_frames_values),
        "video_id": {"n_unique": len(video_counts), "n_duplicated": duplicated_ids},
        "lmdb_key": {
            "n_keys": n_keys,
            "n_unique": len(all_keys),
            "n_unparseable_rows": n_unparseable,
            "n_count_mismatch_rows": n_count_mismatch,
            "n_nonconforming": n_nonconforming,
            "conformance": round(1 - n_nonconforming / n_keys, 6) if n_keys else None,
            "shapes": dict(Counter(key_shape(k) for k in all_keys).most_common(TOP_SHAPES)),
        },
        "frame_bboxes": {
            "n_rows_null": n_box_null,
            "n_rows_count_mismatch": n_box_mismatch,
            "n_invalid_boxes": n_box_invalid,
            "clip_jitter": summarize(jitters),
        },
        "extra_meta": {"n_unparseable_rows": n_extra_unparseable, "keys": extra_meta},
        "frame_rate": {"key": FRAME_RATE_KEY, "n_rows_recorded": n_with_frame_rate},
        "resolution": {"n_null": sum(1 for row in rows if row.get("resolution") is None)},
    }
    return section, findings, clip_keys


# ----------------------------------------------------------------------------- the store


class KeyTally:
    """Accumulates what a scan of the store's keys shows, compared against the index."""

    def __init__(self, index_keys: set[str]) -> None:
        self.index_keys = index_keys
        self.n_scanned = 0
        self.n_undecodable = 0
        self.n_matched = 0
        self.n_with_separator = 0
        self.shapes: Counter[str] = Counter()
        self.index_widths: Counter[str] = Counter()
        self.orphan_shapes: Counter[str] = Counter()

    def add_undecodable(self) -> None:
        self.n_scanned += 1
        self.n_undecodable += 1

    def add(self, key: str) -> None:
        self.n_scanned += 1
        self.shapes[key_shape(key)] += 1
        head, sep, tail = key.rpartition(KEY_SEPARATOR)
        if sep and head:
            self.n_with_separator += 1
            self.index_widths[str(len(tail)) if tail.isdigit() else "non-numeric"] += 1
        if key in self.index_keys:
            self.n_matched += 1
        else:
            self.orphan_shapes[key_shape(key)] += 1

    def to_dict(self, *, entries: int, complete: bool) -> dict[str, Any]:
        decoded = self.n_scanned - self.n_undecodable
        section: dict[str, Any] = {
            "entries": entries,
            "n_scanned": self.n_scanned,
            "scan_complete": complete,
            "n_undecodable_keys": self.n_undecodable,
            "separator": KEY_SEPARATOR,
            "separator_ratio": round(self.n_with_separator / decoded, 6) if decoded else None,
            "index_widths": dict(self.index_widths.most_common()),
            "shapes": dict(self.shapes.most_common(TOP_SHAPES)),
        }
        if complete:
            section["n_index_keys_found"] = self.n_matched
            section["n_index_keys_missing"] = len(self.index_keys) - self.n_matched
            section["n_orphan_keys"] = decoded - self.n_matched
            section["orphan_shapes"] = dict(self.orphan_shapes.most_common(TOP_SHAPES))
        return section


class ValueTally:
    """Accumulates what a probe of frame values shows. Only headers are looked at."""

    def __init__(self) -> None:
        self.n_probed = 0
        self.n_missing = 0
        self.formats: Counter[str] = Counter()
        self.sizes: list[float] = []
        self.dimensions: Counter[str] = Counter()

    def add_missing(self) -> None:
        self.n_probed += 1
        self.n_missing += 1

    def add(self, data: bytes) -> None:
        self.n_probed += 1
        self.formats[sniff_format(data)] += 1
        self.sizes.append(float(len(data)))
        size = image_size(data)
        self.dimensions[f"{size[0]}x{size[1]}" if size else "unknown"] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_probed": self.n_probed,
            "n_missing": self.n_missing,
            "formats": dict(self.formats.most_common()),
            "bytes": summarize(self.sizes),
            "dimensions": dict(self.dimensions.most_common(TOP_SHAPES)),
        }


def spread_indices(n_items: int, n_wanted: int) -> list[int]:
    """Pick up to ``n_wanted`` indices evenly across ``range(n_items)``.

    Rows are ordered by how the build walked the source tree, so the first N are one subject
    in one split; a spread sample reaches every part of the index.
    """
    if n_items <= 0 or n_wanted <= 0:
        return []
    if n_wanted >= n_items:
        return list(range(n_items))
    step = n_items / n_wanted
    return sorted({min(n_items - 1, int(i * step)) for i in range(n_wanted)})


def probe_keys(clip_keys: Sequence[list[str]], n_clips: int) -> list[str]:
    """First, middle and last frame key of clips spread across the index."""
    chosen = [i for i in spread_indices(len(clip_keys), n_clips) if clip_keys[i]]
    keys: list[str] = []
    for i in chosen:
        frames = clip_keys[i]
        for position in sorted({0, len(frames) // 2, len(frames) - 1}):
            keys.append(frames[position])
    return keys


# ----------------------------------------------------------------------------- the frame cache


def compare_with_cache(
    rows: Sequence[dict[str, Any]],
    cache_counts: dict[str, int],
    ambiguous: set[str],
    domain: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compare each clip's stored frame count with the number of frames extracted for it.

    For video sources the build extracts frames at a fixed rate into a cache folder named
    after the video, then keeps only the frames with exactly one detected face. A clip that
    stores fewer frames than were extracted lost some in between, and the store does not
    record which, so the time between its remaining frames is no longer constant. That
    matters to anything that reads time from frame order: temporal FFT, optical flow, and a
    video model's notion of motion speed.
    """
    kept: list[float] = []
    n_matched = n_dropped = n_excess = n_ambiguous = frames_dropped = 0
    for row in rows:
        video_id = str(row.get("video_id"))
        if video_id in ambiguous:
            n_ambiguous += 1
            continue
        extracted = cache_counts.get(video_id)
        stored = row.get("num_frames")
        if extracted is None or not isinstance(stored, int) or extracted <= 0:
            continue
        n_matched += 1
        kept.append(stored / extracted)
        if stored < extracted:
            n_dropped += 1
            frames_dropped += extracted - stored
        elif stored > extracted:
            n_excess += 1
    section: dict[str, Any] = {
        "n_cache_folders": len(cache_counts) + len(ambiguous),
        "n_clips_matched": n_matched,
        "n_clips_ambiguous": n_ambiguous,
        "n_clips_with_drops": n_dropped,
        "n_frames_dropped": frames_dropped,
        "n_clips_stored_more_than_extracted": n_excess,
        "kept_ratio": summarize(kept),
    }
    findings: list[dict[str, Any]] = []
    if n_dropped:
        findings.append(
            finding(
                "warn",
                "FRAMES_DROPPED_AFTER_EXTRACTION",
                f"{n_dropped} of {n_matched} clips kept fewer frames than were extracted "
                f"({frames_dropped} frames in total); the store does not record which, so "
                "the time between their remaining frames is irregular",
                domain,
            )
        )
    if n_excess:
        findings.append(
            finding(
                "warn",
                "CACHE_INCONSISTENT",
                f"{n_excess} clips store more frames than their cache folder holds; the cache "
                "is not the one this store was built from",
                domain,
            )
        )
    if cache_counts and not n_matched:
        findings.append(
            finding(
                "info",
                "CACHE_UNMATCHED",
                "a frame cache exists but no cache folder name matches a video_id",
                domain,
            )
        )
    return section, findings


def scan_frame_cache(dist_root: Path, domain: str) -> tuple[dict[str, int], set[str]] | None:
    """Count the cached frames per folder under ``_frames/<domain>/``. Names only, no content.

    Returns ``(counts by folder name, folder names seen more than once)``, or ``None`` when
    the domain has no cache (image-sequence sources are read in place and never cached).
    """
    root = dist_root / FRAME_CACHE_DIR / domain
    if not root.is_dir():
        return None
    counts: dict[str, int] = {}
    ambiguous: set[str] = set()
    for folder, _subdirs, files in os.walk(root):
        n_frames = sum(1 for name in files if name.lower().endswith(CACHE_FRAME_SUFFIX))
        if not n_frames:
            continue
        name = Path(folder).name
        if name in counts or name in ambiguous:
            counts.pop(name, None)
            ambiguous.add(name)
        else:
            counts[name] = n_frames
    return counts, ambiguous


# ----------------------------------------------------------------------------- I/O


def _native(value: Any) -> Any:
    """Turn numpy scalars/arrays and NaN from pandas into plain Python values."""
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        value = value.tolist()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def read_index(parquet_path: Path) -> list[dict[str, Any]]:
    try:
        import pandas as pd  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise InspectError(
            "pandas (with pyarrow or fastparquet) is needed to read the *_meta.parquet index"
        ) from exc
    try:
        frame = pd.read_parquet(parquet_path)
    except Exception as exc:
        raise InspectError(f"cannot read {parquet_path.name}: {type(exc).__name__}") from exc
    return [
        {str(k): _native(v) for k, v in record.items()}
        for record in frame.to_dict(orient="records")
    ]


def open_readonly(lmdb_dir: Path) -> Any:
    """Open an existing LMDB directory for reading only.

    ``readonly`` opens the data file read-only; ``lock=False`` means no lock file is touched or
    created; ``create=False`` means a wrong path fails instead of producing an empty store.
    ``lock=False`` is only correct while nobody is writing the store, so do not run this
    during a build.
    """
    try:
        import lmdb  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise InspectError("the lmdb package is needed to open the store") from exc
    if not (lmdb_dir / "data.mdb").is_file():
        raise InspectError(f"{lmdb_dir.name}: no data.mdb in the store directory")
    try:
        return lmdb.open(
            str(lmdb_dir),
            subdir=True,
            readonly=True,
            lock=False,
            create=False,
            readahead=False,
            meminit=False,
            max_spare_txns=0,
        )
    except Exception as exc:
        raise InspectError(f"{lmdb_dir.name}: cannot open: {type(exc).__name__}") from exc


def inspect_store(
    env: Any, clip_keys: Sequence[list[str]], *, probe: int, scan_limit: int
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Scan the store's keys and probe some values. Returns (keys, values, missing shapes)."""
    stat = env.stat()
    entries = int(stat["entries"])
    index_keys = {key for keys in clip_keys for key in keys}
    tally = KeyTally(index_keys)
    complete = entries <= scan_limit
    with env.begin(write=False, buffers=True) as txn:
        for raw in txn.cursor().iternext(keys=True, values=False):
            if tally.n_scanned >= scan_limit:
                break
            try:
                tally.add(bytes(raw).decode("utf-8"))
            except UnicodeDecodeError:
                tally.add_undecodable()
    keys_section = tally.to_dict(entries=entries, complete=complete)
    keys_section["depth"] = int(stat["depth"])
    keys_section["page_size"] = int(stat["psize"])

    missing_shapes: list[str] = []
    values = ValueTally()
    with env.begin(write=False, buffers=False) as txn:
        if complete and keys_section["n_index_keys_missing"]:
            seen: Counter[str] = Counter()
            for n, key in enumerate(index_keys):
                if n >= MISSING_LOOKUP_BUDGET or len(seen) >= TOP_SHAPES:
                    break
                if txn.get(key.encode("utf-8")) is None:
                    seen[key_shape(key)] += 1
            missing_shapes = list(seen)
        for key in probe_keys(clip_keys, probe):
            data = txn.get(key.encode("utf-8"))
            if data is None:
                values.add_missing()
            else:
                values.add(bytes(data))
    return keys_section, values.to_dict(), missing_shapes


def store_findings(
    keys: dict[str, Any], values: dict[str, Any], missing_shapes: list[str], domain: str
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if keys.get("n_index_keys_missing"):
        findings.append(
            finding(
                "error",
                "INDEX_KEYS_MISSING_FROM_STORE",
                f"{keys['n_index_keys_missing']} keys listed in the parquet are not in the "
                f"LMDB; shapes: {missing_shapes}",
                domain,
            )
        )
    if keys.get("n_orphan_keys"):
        findings.append(
            finding(
                "warn",
                "ORPHAN_KEYS_IN_STORE",
                f"{keys['n_orphan_keys']} LMDB keys are listed by no parquet row",
                domain,
            )
        )
    if not keys.get("scan_complete"):
        findings.append(
            finding(
                "info",
                "SCAN_TRUNCATED",
                f"scanned {keys['n_scanned']} of {keys['entries']} keys; raise --scan-limit "
                "for an exact index/store comparison",
                domain,
            )
        )
    if values["n_missing"]:
        findings.append(
            finding(
                "error",
                "PROBED_KEYS_MISSING",
                f"{values['n_missing']} of {values['n_probed']} probed frame keys are absent",
                domain,
            )
        )
    formats = values["formats"]
    if len(formats) > 1 or "unknown" in formats:
        findings.append(finding("warn", "VALUE_FORMATS", f"frame value formats: {formats}", domain))
    return findings


def discover(dist_root: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (paired domains, stores without an index, indexes without a store)."""
    stores: set[str] = set()
    indexes: set[str] = set()
    for entry in dist_root.iterdir():
        if entry.name.startswith(("_", ".")):
            continue
        if entry.is_dir() and (entry / "data.mdb").is_file():
            stores.add(entry.name)
        elif entry.is_file() and entry.name.endswith(PARQUET_SUFFIX):
            indexes.add(entry.name[: -len(PARQUET_SUFFIX)])
    return sorted(stores & indexes), sorted(stores - indexes), sorted(indexes - stores)


def read_build_config(dist_root: Path) -> dict[str, Any] | None:
    path = dist_root / "build_config.json"
    if not path.is_file():
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"unreadable": True}
    return sanitize_build_config(config) if isinstance(config, dict) else {"unreadable": True}


def inspect_domain(
    dist_root: Path,
    name: str,
    *,
    read_store: bool,
    probe: int,
    scan_limit: int,
    examples: int,
) -> dict[str, Any]:
    report: dict[str, Any] = {"name": name}
    try:
        rows = read_index(dist_root / f"{name}{PARQUET_SUFFIX}")
    except InspectError as exc:
        report["findings"] = [finding("error", "INDEX_UNREADABLE", str(exc), name)]
        return report
    index, findings, clip_keys = analyze_rows(rows, name)
    report["index"] = index
    try:
        cache = scan_frame_cache(dist_root, name)
    except OSError as exc:
        cache = None
        findings.append(
            finding("warn", "FRAME_CACHE_UNREADABLE", f"cannot list: {type(exc).__name__}", name)
        )
    if cache is not None:
        report["frame_cache"], cache_findings = compare_with_cache(rows, *cache, domain=name)
        findings.extend(cache_findings)
    if examples > 0:
        report["examples"] = {
            "video_ids": [str(row.get("video_id")) for row in rows[:examples]],
            "keys": [key for keys in clip_keys[:examples] for key in keys[:2]],
        }
    if read_store:
        env = None
        try:
            env = open_readonly(dist_root / name)
            keys, values, missing_shapes = inspect_store(
                env, clip_keys, probe=probe, scan_limit=scan_limit
            )
            report["store"] = {"keys": keys, "values": values}
            findings.extend(store_findings(keys, values, missing_shapes, name))
        except InspectError as exc:
            findings.append(finding("error", "STORE_UNREADABLE", str(exc), name))
        finally:
            if env is not None:
                env.close()
    report["findings"] = findings
    return report


# ----------------------------------------------------------------------------- output


def render_text(report: dict[str, Any]) -> str:
    lines = [f"inspect_lmdb_layout v{report['tool_version']}  (read-only)"]
    if report.get("build_config") is not None:
        lines.append(f"build_config: {json.dumps(report['build_config'], ensure_ascii=False)}")
    for label, names in (
        ("stores without an index", report["unpaired"]["stores_without_index"]),
        ("indexes without a store", report["unpaired"]["indexes_without_store"]),
    ):
        if names:
            lines.append(f"{label}: {', '.join(names)}")
    for domain in report["domains"]:
        lines.append("")
        lines.append(f"== {domain['name']} ==")
        index = domain.get("index")
        if index:
            keys = index["lmdb_key"]
            lines.append(
                f"  clips {index['n_rows']}  subjects {index['subjects']['n']}  "
                f"frame keys {keys['n_keys']} (pattern conformance {keys['conformance']})"
            )
            lines.append(f"  cls {index['cls']}  split {index['split']}")
            lines.append(f"  num_frames {index['num_frames']}")
            lines.append(f"  sub_cls ({index['n_sub_cls']}) {index['sub_cls']}")
            lines.append(f"  key shapes {keys['shapes']}")
            boxes = index["frame_bboxes"]
            lines.append(
                f"  bboxes null rows {boxes['n_rows_null']}  clip jitter {boxes['clip_jitter']}"
            )
            lines.append(f"  extra_meta {json.dumps(index['extra_meta']['keys'])}")
        cache = domain.get("frame_cache")
        if cache:
            lines.append(
                f"  frame cache: clips matched {cache['n_clips_matched']}  "
                f"with drops {cache['n_clips_with_drops']}  "
                f"frames dropped {cache['n_frames_dropped']}  kept ratio {cache['kept_ratio']}"
            )
        store = domain.get("store")
        if store:
            keys = store["keys"]
            lines.append(
                f"  store entries {keys['entries']}  scanned {keys['n_scanned']}  "
                f"separator ratio {keys['separator_ratio']}  index widths {keys['index_widths']}"
            )
            if keys["scan_complete"]:
                lines.append(
                    f"  index keys found {keys['n_index_keys_found']}  "
                    f"missing {keys['n_index_keys_missing']}  orphans {keys['n_orphan_keys']}"
                )
            values = store["values"]
            lines.append(
                f"  probed {values['n_probed']}  formats {values['formats']}  "
                f"dims {values['dimensions']}  bytes {values['bytes']}"
            )
        for item in domain.get("findings", []):
            lines.append(f"  [{item['level'].upper()}] {item['code']}: {item['detail']}")
    lines.append("")
    counts = Counter(item["level"] for item in report["findings"])
    lines.append(
        f"findings: {counts.get('error', 0)} error, {counts.get('warn', 0)} warn, "
        f"{counts.get('info', 0)} info"
    )
    return "\n".join(lines)


def build_report(
    dist_root: Path,
    *,
    domains: Sequence[str] | None,
    read_store: bool,
    probe: int,
    scan_limit: int,
    examples: int,
) -> dict[str, Any]:
    if not dist_root.is_dir():
        raise InspectError("--dist-root is not a directory")
    paired, stores_only, indexes_only = discover(dist_root)
    if domains:
        unknown = sorted(set(domains) - set(paired))
        if unknown:
            raise InspectError(f"not a paired store+index under --dist-root: {unknown}")
        paired = [name for name in paired if name in set(domains)]
    report: dict[str, Any] = {
        "tool": "inspect_lmdb_layout",
        "tool_version": TOOL_VERSION,
        "read_store": read_store,
        "build_config": read_build_config(dist_root),
        "unpaired": {"stores_without_index": stores_only, "indexes_without_store": indexes_only},
        "domains": [
            inspect_domain(
                dist_root,
                name,
                read_store=read_store,
                probe=probe,
                scan_limit=scan_limit,
                examples=examples,
            )
            for name in paired
        ],
    }
    report["findings"] = [item for d in report["domains"] for item in d.get("findings", [])]
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Report the layout of a video PAD LMDB store. Reads only; writes nothing."
    )
    ap.add_argument("--dist-root", type=Path, required=True, help="directory holding the stores")
    ap.add_argument("--domain", action="append", help="limit to this domain (repeatable)")
    ap.add_argument(
        "--no-lmdb",
        action="store_true",
        help="read only the parquet indexes; do not open any LMDB",
    )
    ap.add_argument("--probe", type=int, default=DEFAULT_PROBE, help="clips whose frames to probe")
    ap.add_argument(
        "--scan-limit",
        type=int,
        default=DEFAULT_SCAN_LIMIT,
        help="keys to scan per store; the index/store comparison is exact only within it",
    )
    ap.add_argument(
        "--examples",
        type=int,
        default=0,
        help="include N literal video_ids and keys per domain (default: shapes only)",
    )
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)

    try:
        report = build_report(
            args.dist_root,
            domains=args.domain,
            read_store=not args.no_lmdb,
            probe=max(0, args.probe),
            scan_limit=max(1, args.scan_limit),
            examples=max(0, args.examples),
        )
    except InspectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not report["domains"]:
        print("error: no <name>/data.mdb with a matching <name>_meta.parquet", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))
    return 1 if any(item["level"] == "error" for item in report["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
