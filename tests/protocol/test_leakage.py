from __future__ import annotations

from pathlib import Path

import pytest

from pad_research.data.manifest import PAI, Split
from pad_research.protocols.validator import validate_protocol

from .helpers import protocol, rec, standard_records, write_raw_manifest

pytestmark = pytest.mark.protocol


@pytest.fixture()
def good_dir(tmp_path: Path) -> Path:
    write_raw_manifest(standard_records("src", 0), tmp_path)
    write_raw_manifest(standard_records("tgt", 100), tmp_path)
    return tmp_path


def test_clean_manifests_validate_ok(good_dir: Path) -> None:
    v = validate_protocol(protocol(), good_dir)
    assert v.ok, v.issues
    assert v.adaptation_set_hash is not None
    assert v.research_claim_allowed is True
    assert set(v.manifest_hashes) == {"src", "tgt"}


def test_synthetic_policy_disables_research_claims(tmp_path: Path) -> None:
    write_raw_manifest(standard_records("src", 0), tmp_path, pii_policy="synthetic")
    write_raw_manifest(standard_records("tgt", 100), tmp_path)
    assert validate_protocol(protocol(), tmp_path).research_claim_allowed is False


def test_subject_overlap_detected(tmp_path: Path) -> None:
    recs = standard_records("src", 0)
    recs.append(rec("src", 0, 9, Split.test, PAI.none))  # subject 0 is a train subject
    write_raw_manifest(recs, tmp_path)
    write_raw_manifest(standard_records("tgt", 100), tmp_path)
    v = validate_protocol(protocol(), tmp_path)
    assert "SUBJECT_OVERLAP_SPLITS" in v.codes() and not v.ok


def test_source_target_subject_overlap_detected(tmp_path: Path) -> None:
    write_raw_manifest(standard_records("src", 0), tmp_path)
    write_raw_manifest(standard_records("tgt", 0), tmp_path)  # same subject ids as source
    v = validate_protocol(protocol(), tmp_path)
    assert "SOURCE_TARGET_SUBJECT_OVERLAP" in v.codes()


def test_adapt_from_test_split_rejected(good_dir: Path) -> None:
    p = protocol(
        target_adaptation={
            "enabled": True,
            "supervision": "bona_fide_only",
            "total_samples": 4,
            "source_split": "test",
        }
    )
    v = validate_protocol(p, good_dir)
    assert {"ADAPT_FROM_TEST_SPLIT", "ADAPT_TEST_SAMPLE_OVERLAP"} <= v.codes()


def test_adapt_test_subject_overlap_detected(tmp_path: Path) -> None:
    recs = standard_records("tgt", 100)
    # a bona-fide train clip whose subject is a test subject (subject 106 is in test)
    recs.append(rec("tgt", 106, 9, Split.train, PAI.none))
    write_raw_manifest(standard_records("src", 0), tmp_path)
    write_raw_manifest(recs, tmp_path)
    p = protocol(
        target_adaptation={
            "enabled": True,
            "supervision": "bona_fide_only",
            "shots_per_subject": 1,
        }
    )
    v = validate_protocol(p, tmp_path)
    assert "ADAPT_TEST_SUBJECT_OVERLAP" in v.codes()


def test_adapt_test_not_excluded_rejected(good_dir: Path) -> None:
    p = protocol(target_test={"exclude_adaptation_samples": False})
    assert "ADAPT_TEST_NOT_EXCLUDED" in validate_protocol(p, good_dir).codes()


def test_adapt_insufficient_candidates(good_dir: Path) -> None:
    p = protocol(
        target_adaptation={"enabled": True, "supervision": "bona_fide_only", "total_samples": 999}
    )
    assert "ADAPT_INSUFFICIENT_CANDIDATES" in validate_protocol(p, good_dir).codes()


def test_image_dataset_as_clip_rejected(tmp_path: Path) -> None:
    write_raw_manifest(standard_records("src", 0), tmp_path, temporal_valid=False)
    write_raw_manifest(standard_records("tgt", 100), tmp_path)
    assert "IMAGE_DATASET_AS_CLIP" in validate_protocol(protocol(), tmp_path, frames=8).codes()
    assert "IMAGE_DATASET_AS_CLIP" not in validate_protocol(protocol(), tmp_path, frames=1).codes()
    ok = validate_protocol(protocol(allow_image_dataset_as_clip=True), tmp_path, frames=8)
    assert "IMAGE_DATASET_AS_CLIP" not in ok.codes()


def test_attack_type_absent_detected(good_dir: Path) -> None:
    v = validate_protocol(protocol(attack_types=[PAI.mask_3d]), good_dir)
    assert "ATTACK_TYPE_ABSENT_IN_TEST" in v.codes() and not v.ok


def test_small_pai_support_warning(good_dir: Path) -> None:
    p = protocol(security_gate={"min_attack_samples_per_pai": 50})
    v = validate_protocol(p, good_dir)
    assert "SMALL_PAI_SUPPORT" in v.codes() and v.ok  # warning only


def test_missing_manifest_error_when_active_warning_when_draft(tmp_path: Path) -> None:
    write_raw_manifest(standard_records("src", 0), tmp_path)
    active = validate_protocol(protocol(), tmp_path)
    assert "MISSING_MANIFEST" in {i.code for i in active.errors()}
    draft = validate_protocol(protocol(status="draft"), tmp_path)
    assert draft.ok and "MISSING_MANIFEST" in {i.code for i in draft.warnings()}


def test_tampered_manifest_detected(tmp_path: Path) -> None:
    write_raw_manifest(standard_records("src", 0), tmp_path, corrupt_hash=True)
    write_raw_manifest(standard_records("tgt", 100), tmp_path)
    assert "MANIFEST_HASH_MISMATCH" in validate_protocol(protocol(), tmp_path).codes()


def test_committed_synthetic_protocols_validate(repo_root: Path) -> None:
    from pad_research.protocols.loader import load_protocol

    mdir = repo_root / "data" / "manifests"
    for name in ("syn_a_to_b_v1", "syn_a_to_b_bf_adapt_v1"):
        v = validate_protocol(load_protocol(name), mdir, frames=8)
        assert v.ok, (name, v.issues)
        assert v.research_claim_allowed is False
    assert validate_protocol(load_protocol("syn_a_to_b_bf_adapt_v1"), mdir).adaptation_set_hash
