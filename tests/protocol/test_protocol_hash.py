from __future__ import annotations

import json
from pathlib import Path

import yaml
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from pad_research.protocols.hashing import HASH_EXCLUDED, protocol_hash, short_hash
from pad_research.protocols.loader import load_protocol
from pad_research.protocols.schema import ProtocolSpec

from .helpers import protocol

ROOT = Path(__file__).resolve().parents[2]
PINNED = json.loads((ROOT / "tests" / "fixtures" / "protocol_hashes.json").read_text())


def test_committed_protocol_hashes_unchanged() -> None:
    """Changing a committed protocol (or the schema defaults) must be a deliberate act:
    update tests/fixtures/protocol_hashes.json in the same commit and record it in an ADR."""
    actual = {
        p.stem: protocol_hash(load_protocol(p))
        for p in (ROOT / "configs" / "protocol").glob("*.yaml")
    }
    assert actual == PINNED


def test_hash_stable_under_key_order() -> None:
    text = (ROOT / "configs" / "protocol" / "syn_a_to_b_v1.yaml").read_text()
    data = yaml.safe_load(text)
    reordered = dict(reversed(list(data.items())))
    assert protocol_hash(ProtocolSpec.model_validate(reordered)) == PINNED["syn_a_to_b_v1"]


def test_hash_ignores_description_parent_change_note_status() -> None:
    a = protocol()
    b = protocol(description="other", status="draft", parent_protocol_id="p_v1", change_note="note")
    assert protocol_hash(a) == protocol_hash(b)
    assert {"description", "parent_protocol_id", "change_note", "status"} == HASH_EXCLUDED


def test_hash_sensitive_to_total_samples() -> None:
    a = protocol()
    b = protocol(
        target_adaptation={"enabled": True, "supervision": "bona_fide_only", "total_samples": 5}
    )
    assert protocol_hash(a) != protocol_hash(b)


def test_hash_sensitive_to_acer_policy_and_gate_tolerance() -> None:
    a = protocol()
    assert protocol_hash(a) != protocol_hash(protocol(acer_policy="pooled"))
    assert protocol_hash(a) != protocol_hash(
        protocol(security_gate={"abs_tolerance": 0.02, "min_attack_samples_per_pai": 2})
    )


def test_hash_includes_protocol_id_and_schema_version() -> None:
    assert protocol_hash(protocol()) != protocol_hash(protocol(protocol_id="other_v1"))
    dumped = protocol().model_dump(mode="json", exclude=set(HASH_EXCLUDED))
    assert dumped["schema_version"] == 1 and "protocol_id" in dumped


def test_hash_order_insensitive_for_dataset_lists() -> None:
    a = protocol(source_datasets=["b", "a"], attack_types=["replay_phone", "print"])
    b = protocol(source_datasets=["a", "b"], attack_types=["print", "replay_phone"])
    assert protocol_hash(a) == protocol_hash(b)


def test_hash_identical_via_hydra_and_yaml() -> None:
    with initialize_config_dir(version_base="1.3", config_dir=str(ROOT / "configs")):
        cfg = compose(config_name="config", overrides=["+exp=syn_e02_video_source_only"])
    raw = OmegaConf.to_container(cfg.protocol, resolve=True, throw_on_missing=True)
    assert isinstance(raw, dict)
    via_hydra = protocol_hash(ProtocolSpec.model_validate(raw))
    assert via_hydra == PINNED["syn_a_to_b_bf_adapt_v1"]


def test_short_hash() -> None:
    assert short_hash("a" * 64) == "a" * 12
