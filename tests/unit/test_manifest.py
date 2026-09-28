"""Tests for manifest schema, hashing, validation and I/O."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pad_research.data.manifest import (
    PAI,
    Label,
    ManifestNotFoundError,
    ManifestRecord,
    ManifestTamperedError,
    ManifestValidationError,
    MediaType,
    Split,
    load_manifest,
    manifest_hash,
    resolve_path,
    validate_records,
    write_manifest,
)


def _rec(**overrides: Any) -> ManifestRecord:
    base: dict[str, Any] = {
        "dataset_id": "ds",
        "sample_id": "ds_s000_c00_none",
        "subject_id": "subj0000",
        "split": "train",
        "label": "bona_fide",
        "pai": "none",
        "relative_path": "ds/ds_s000_c00_none.npy",
        "media_type": "npy_clip",
    }
    base.update(overrides)
    return ManifestRecord(**base)


META: dict[str, Any] = {
    "dataset_id": "ds",
    "version": "1.0",
    "adapter": "synthetic",
    "license": "synthetic-cc0",
    "pii_policy": "synthetic",
    "temporal_valid": True,
}


def _records() -> list[ManifestRecord]:
    return [
        _rec(sample_id="b", subject_id="subj0001", split="dev", relative_path="ds/b.npy"),
        _rec(sample_id="a"),
        _rec(
            sample_id="c",
            subject_id="subj0002",
            split="test",
            label="spoof",
            pai="print",
            relative_path="ds/c.npy",
        ),
    ]


# --- schema -----------------------------------------------------------------------------------


def test_dataset_id_is_lowercased() -> None:
    assert _rec(dataset_id="REPLAY_ATTACK").dataset_id == "replay_attack"
    with pytest.raises(ValidationError):
        _rec(dataset_id="bad-id")


def test_absolute_and_parent_paths_rejected() -> None:
    for bad in ["/abs/x.npy", "../x.npy", "a/../x.npy", "C:/x.npy", "a\\b.npy", ""]:
        with pytest.raises(ValidationError):
            _rec(relative_path=bad)


def test_label_pai_consistency() -> None:
    with pytest.raises(ValidationError):
        _rec(label="bona_fide", pai="print")
    with pytest.raises(ValidationError):
        _rec(label="spoof", pai="none")
    assert _rec(label="spoof", pai="replay_phone").pai is PAI.replay_phone


def test_record_is_frozen_and_forbids_extra_fields() -> None:
    record = _rec()
    with pytest.raises(ValidationError):
        record.label = Label.spoof  # type: ignore[misc]
    with pytest.raises(ValidationError):
        _rec(unknown_field=1)


def test_sample_id_pattern() -> None:
    with pytest.raises(ValidationError):
        _rec(sample_id="has space")
    assert _rec(sample_id="ok.id-1_x").sample_id == "ok.id-1_x"


# --- hash -------------------------------------------------------------------------------------


def test_manifest_hash_is_order_independent_and_content_sensitive() -> None:
    records = _records()
    h1 = manifest_hash(records)
    h2 = manifest_hash(list(reversed(records)))
    assert h1 == h2
    assert len(h1) == 64
    changed = [
        *records[:2],
        _rec(
            sample_id="c",
            subject_id="subj0002",
            split="test",
            label="spoof",
            pai="print",
            relative_path="ds/c2.npy",
        ),
    ]
    assert manifest_hash(changed) != h1


# --- validate ---------------------------------------------------------------------------------


def test_validate_records_clean() -> None:
    assert validate_records(_records()) == []


def test_validate_records_duplicate_and_leakage_and_extension() -> None:
    records = [
        _rec(sample_id="a"),
        _rec(sample_id="a", split="dev"),  # duplicate id + subject subj0000 in train and dev
        _rec(sample_id="d", subject_id="subj0009", split="test", relative_path="ds/d.mp4"),
    ]
    errors = validate_records(records)
    joined = "\n".join(errors)
    assert "duplicate sample_id 'a'" in joined
    assert "subject leakage" in joined and "subj0000" in joined
    assert "'ds/d.mp4'" in joined and "npy_clip" in joined
    assert len(errors) == 3


def test_validate_records_mixed_dataset_ids() -> None:
    errors = validate_records([_rec(), _rec(dataset_id="other", sample_id="z", subject_id="s9")])
    assert any("mix dataset_ids" in e for e in errors)


# --- write / load -----------------------------------------------------------------------------


def test_write_load_roundtrip(tmp_path: Path) -> None:
    records = _records()
    meta = write_manifest(records, META, tmp_path)
    assert meta.manifest_hash == manifest_hash(records)
    assert meta.n_records == 3 and meta.n_subjects == 3
    assert meta.splits["train"]["n_records"] == 1
    assert meta.pai_counts == {"none": 2, "print": 1}
    assert meta.research_grade is False
    assert meta.created_at.endswith("+00:00")

    lines = (tmp_path / "ds.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["sample_id"] for line in lines] == ["a", "b", "c"]

    loaded = load_manifest("ds", tmp_path)
    assert loaded.meta == meta
    assert sorted(r.sample_id for r in loaded.records) == ["a", "b", "c"]
    assert loaded.by_split(Split.dev)[0].sample_id == "b"
    assert loaded.subjects("test") == {"subj0002"}
    assert loaded.subjects() == {"subj0000", "subj0001", "subj0002"}
    assert loaded.sample_ids() == {"a", "b", "c"}


def test_rewrite_is_byte_identical(tmp_path: Path) -> None:
    records = _records()
    write_manifest(records, META, tmp_path)
    first = [(tmp_path / n).read_bytes() for n in ("ds.jsonl", "ds.meta.json")]
    write_manifest(list(reversed(records)), META, tmp_path)
    second = [(tmp_path / n).read_bytes() for n in ("ds.jsonl", "ds.meta.json")]
    assert first == second


def test_load_detects_tampering(tmp_path: Path) -> None:
    write_manifest(_records(), META, tmp_path)
    jsonl = tmp_path / "ds.jsonl"
    jsonl.write_text(jsonl.read_text(encoding="utf-8").replace('"split":"test"', '"split":"dev"'))
    with pytest.raises(ManifestTamperedError):
        load_manifest("ds", tmp_path)


def test_load_detects_meta_tampering(tmp_path: Path) -> None:
    write_manifest(_records(), META, tmp_path)
    meta_path = tmp_path / "ds.meta.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    data["manifest_hash"] = "0" * 64
    meta_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ManifestTamperedError):
        load_manifest("ds", tmp_path)


def test_load_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(ManifestNotFoundError):
        load_manifest("nope", tmp_path)
    assert issubclass(ManifestNotFoundError, FileNotFoundError)


def test_write_rejects_invalid_record_sets(tmp_path: Path) -> None:
    with pytest.raises(ManifestValidationError):
        write_manifest([_rec(sample_id="a"), _rec(sample_id="a", split="dev")], META, tmp_path)
    with pytest.raises(ManifestValidationError):
        write_manifest([], META, tmp_path)
    with pytest.raises(ManifestValidationError):
        write_manifest(_records(), {**META, "dataset_id": "other"}, tmp_path)


def test_resolve_path() -> None:
    record = _rec(relative_path="ds/x.npy", media_type=MediaType.npy_clip)
    assert resolve_path(record, Path("/data/root")) == Path("/data/root/ds/x.npy")
