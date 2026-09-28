from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pad_research.data.manifest import PAI
from pad_research.protocols.loader import load_protocol
from pad_research.protocols.schema import ProtocolSpec, pai_matches

from .helpers import protocol

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "protocols"
PROTOCOL_DIR = Path(__file__).resolve().parents[2] / "configs" / "protocol"


def test_yaml_roundtrip_matches_section15() -> None:
    p = load_protocol(FIXTURES / "section15_example.yaml")
    assert p.source_datasets == ["casia_fasd", "msu_mfsd", "oulu_npu"]  # lowercased + sorted
    assert p.target_dataset == ["replay_attack"]
    assert p.target_adaptation.total_samples == 100
    assert p.threshold.rule == "eer" and p.acer_policy == "max_pai"
    assert p.security_gate.min_attack_samples_per_pai == 20


@pytest.mark.parametrize("path", sorted(PROTOCOL_DIR.glob("*.yaml")), ids=lambda p: p.stem)
def test_every_committed_protocol_loads(path: Path) -> None:
    p = load_protocol(path)
    assert p.protocol_id == path.stem


def test_duplicate_dataset_rejected() -> None:
    with pytest.raises(ValidationError, match="DUPLICATE_DATASET"):
        protocol(source_datasets=["a", "A"])


def test_parent_requires_change_note() -> None:
    with pytest.raises(ValidationError, match="PARENT_REQUIRES_CHANGE_NOTE"):
        protocol(parent_protocol_id="x_v1")
    protocol(parent_protocol_id="x_v1", change_note="changed budget")


def test_source_target_overlap_rejected() -> None:
    with pytest.raises(ValidationError, match="SOURCE_TARGET_DATASET_OVERLAP"):
        protocol(source_datasets=["tgt"], target_dataset=["tgt"])


def test_attack_type_none_rejected() -> None:
    with pytest.raises(ValidationError, match="ATTACK_TYPE_NONE"):
        protocol(attack_types=[PAI.none])


def test_adaptation_requires_exactly_one_budget() -> None:
    with pytest.raises(ValidationError, match="ADAPT_BUDGET_AMBIGUOUS"):
        protocol(
            target_adaptation={"enabled": True, "supervision": "bona_fide_only"},
        )


def test_pai_matches_replay_prefix() -> None:
    assert pai_matches(PAI.replay, PAI.replay_phone)
    assert pai_matches(PAI.replay, PAI.replay_tablet)
    assert not pai_matches(PAI.replay, PAI.print)
    assert pai_matches(PAI.display, PAI.replay_display)
    assert pai_matches(PAI.print, PAI.print) and not pai_matches(PAI.print, PAI.replay)


def test_protocol_is_frozen() -> None:
    p = protocol()
    with pytest.raises(ValidationError):
        p.acer_policy = "pooled"  # type: ignore[misc]
    assert isinstance(p, ProtocolSpec)
