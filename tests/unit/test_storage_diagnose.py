"""The pre-flight check: does this machine's storage config actually reach this dataset?

What is being tested is mostly the *diagnosis*, not the read. A check that only says "failed"
sends someone to read source code; the value is in naming the variable, or in distinguishing
"the store is unreachable" from "the store is fine but your keys do not match the manifest".
"""

from __future__ import annotations

from pathlib import Path

import lmdb
import pytest

from pad_research.data.manifest import PAI, Label, ManifestRecord, MediaType, Split, write_manifest
from pad_research.data.storage.config import LmdbStorageConfig, LocalStorageConfig
from pad_research.data.storage.diagnose import diagnose_storage


def _records(n: int = 6) -> list[ManifestRecord]:
    return [
        ManifestRecord(
            dataset_id="unit_ds",
            sample_id=f"sample_{i:03d}",
            subject_id=f"subject_{i:03d}",
            split=Split.train,
            label=Label.bona_fide,
            pai=PAI.none,
            relative_path=f"unit_ds/clip_{i:03d}.npy",
            media_type=MediaType.npy_clip,
        )
        for i in range(n)
    ]


@pytest.fixture
def manifests_dir(tmp_path: Path) -> Path:
    out = tmp_path / "manifests"
    write_manifest(
        _records(),
        {
            "dataset_id": "unit_ds",
            "version": "1",
            "adapter": "unit",
            "license": "test",
            "pii_policy": "synthetic",
            "temporal_valid": True,
        },
        out,
    )
    return out


def _status(report: object, name: str) -> str:
    return next(c.status for c in report.checks if c.name == name)  # type: ignore[attr-defined]


def test_a_reachable_root_with_readable_media_passes(
    tmp_path: Path, manifests_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "media"
    (root / "unit_ds").mkdir(parents=True)
    for record in _records():
        (root / record.relative_path).write_bytes(b"x")
    monkeypatch.setenv("PAD_DATA_ROOT", str(root))

    report = diagnose_storage(
        LocalStorageConfig(), manifests_dir=manifests_dir, dataset_id="unit_ds"
    )
    assert report.ok
    assert report.n_probed > 0
    assert _status(report, "MEDIA_READABLE") == "pass"


def test_an_unset_variable_stops_at_the_first_check_and_names_it(
    manifests_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PAD_DATA_ROOT", raising=False)
    report = diagnose_storage(LocalStorageConfig(), manifests_dir=manifests_dir)
    assert not report.ok
    failure = report.failures()[0]
    assert failure.name == "BACKEND_REACHABLE"
    assert "PAD_DATA_ROOT" in failure.remedy
    # Later checks are not attempted: reporting "manifest unreadable" as well would bury the
    # one thing that needs fixing.
    assert len(report.checks) == 1


def test_a_reachable_store_whose_keys_do_not_match_is_reported_as_a_key_problem(
    tmp_path: Path, manifests_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mistake this command exists to catch.

    The LMDB opens, the manifest loads, and every single read misses because the store was
    built with a prefix the manifest does not carry. Without this distinction the symptom is
    an unhelpful FileNotFoundError per sample, thousands of times.
    """
    store = tmp_path / "s.lmdb"
    env = lmdb.open(str(store), subdir=True, map_size=1 << 22)
    with env.begin(write=True) as txn:
        for record in _records():
            txn.put(f"prefixed/{record.relative_path}".encode(), b"x")
    env.close()
    monkeypatch.setenv("PAD_LMDB_PATH", str(store))

    report = diagnose_storage(
        LmdbStorageConfig(kind="lmdb"), manifests_dir=manifests_dir, dataset_id="unit_ds"
    )
    assert not report.ok
    failure = report.failures()[0]
    assert failure.name == "MEDIA_READABLE"
    assert "key_prefix" in failure.remedy

    # And with the affix supplied, the same store and manifest pass.
    fixed = diagnose_storage(
        LmdbStorageConfig(kind="lmdb", key_prefix="prefixed/"),
        manifests_dir=manifests_dir,
        dataset_id="unit_ds",
    )
    assert fixed.ok


def test_a_missing_manifest_points_at_the_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAD_DATA_ROOT", str(tmp_path))
    report = diagnose_storage(
        LocalStorageConfig(), manifests_dir=tmp_path / "empty", dataset_id="unit_ds"
    )
    assert not report.ok
    assert "prepare_dataset.py" in report.failures()[0].remedy


def test_without_a_dataset_id_the_media_check_is_skipped_not_silently_passed(
    tmp_path: Path, manifests_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # "ok" here means the backend is reachable, which is weaker than "the data is readable";
    # a skip records that difference instead of implying a check that never ran.
    monkeypatch.setenv("PAD_DATA_ROOT", str(tmp_path))
    report = diagnose_storage(LocalStorageConfig(), manifests_dir=manifests_dir)
    assert report.ok
    assert _status(report, "MANIFEST_READABLE") == "skip"


def test_probing_spreads_across_the_manifest_rather_than_taking_the_first_rows(
    tmp_path: Path, manifests_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Records are sorted by sample_id, so the first N are one subject in one split.

    A layout mistake that only affects, say, the attack samples would pass a first-N probe and
    fail on the GPU. Here only the LAST record is present, and the probe must still notice.
    """
    root = tmp_path / "media"
    (root / "unit_ds").mkdir(parents=True)
    (root / _records()[-1].relative_path).write_bytes(b"x")
    monkeypatch.setenv("PAD_DATA_ROOT", str(root))

    report = diagnose_storage(
        LocalStorageConfig(), manifests_dir=manifests_dir, dataset_id="unit_ds", probe=3
    )
    assert not report.ok
    assert _status(report, "MEDIA_READABLE") == "fail"
