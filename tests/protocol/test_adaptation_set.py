from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pad_research.data.manifest import Label, load_manifest
from pad_research.protocols.adaptation_set import (
    materialize_adaptation_set,
    select_adaptation_set,
)
from pad_research.protocols.validator import validate_protocol

from .helpers import protocol, standard_records, write_raw_manifest

pytestmark = pytest.mark.protocol


@pytest.fixture()
def target(tmp_path: Path):
    write_raw_manifest(standard_records("src", 0), tmp_path)
    write_raw_manifest(standard_records("tgt", 100), tmp_path)
    return tmp_path, load_manifest("tgt", tmp_path)


def test_select_is_deterministic(target) -> None:
    _, m = target
    a = select_adaptation_set(protocol(), m)
    b = select_adaptation_set(protocol(), m)
    assert a == b and len(a.sample_ids) == 4
    c = select_adaptation_set(
        protocol(
            target_adaptation={
                "enabled": True,
                "supervision": "bona_fide_only",
                "total_samples": 4,
                "selection_seed": 1,
            }
        ),
        m,
    )
    assert c.sample_ids != a.sample_ids  # seed matters (and is part of the protocol hash)


def test_select_bona_fide_only(target) -> None:
    _, m = target
    sel = select_adaptation_set(protocol(), m)
    by_id = {r.sample_id: r for r in m.records}
    assert all(by_id[s].label == Label.bona_fide for s in sel.sample_ids)
    assert all(by_id[s].split.value == "train" for s in sel.sample_ids)


def test_shots_per_subject(target) -> None:
    _, m = target
    p = protocol(
        target_adaptation={"enabled": True, "supervision": "bona_fide_only", "shots_per_subject": 1}
    )
    sel = select_adaptation_set(p, m)
    assert len(sel.sample_ids) == 3 and len(sel.subject_ids) == 3


def test_materialize_writes_and_is_idempotent(target) -> None:
    mdir, m = target
    sel = select_adaptation_set(protocol(), m)
    out = mdir / "adaptation"
    p1 = materialize_adaptation_set(sel, out, m)
    digest = hashlib.sha256(p1.read_bytes()).hexdigest()
    mtime = p1.stat().st_mtime_ns
    p2 = materialize_adaptation_set(sel, out, m)
    assert p1 == p2 and hashlib.sha256(p2.read_bytes()).hexdigest() == digest
    assert p2.stat().st_mtime_ns == mtime  # untouched when identical
    assert p1.name.startswith("t_src_to_tgt_v1.")


def test_validate_protocol_has_no_filesystem_side_effects(target) -> None:
    mdir, _ = target
    before = sorted(str(p.relative_to(mdir)) for p in mdir.rglob("*"))
    validate_protocol(protocol(), mdir)
    after = sorted(str(p.relative_to(mdir)) for p in mdir.rglob("*"))
    assert before == after
