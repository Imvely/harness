"""Structural Definition-of-Done tests for the Phase 0 harness MVP."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "docs" / "RESEARCH_CONTRACT.md"
README = REPO_ROOT / "README.md"
CONTRACT_SHA256 = "37a849366fb16754b29b93c59eb97543e841c64f2c00c7bad28aae7746261d2f"

DOD_ITEMS = [
    "root `CLAUDE.md`",
    "`.claude/rules/`",
    "3개 subagent",
    "destructive-command safety hook",
    "experiment launch validation",
    "uv-based environment",
    "Hydra config",
    "dataset manifest",
    "protocol schema",
    "protocol hash",
    "APCER unit test",
    "BPCER unit test",
    "ACER unit test",
    "HTER unit test",
    "AUC unit test",
    "MLflow run logging",
    "Git SHA logging",
    "environment metadata logging",
    "smoke-test mode",
    "full GPU run gate",
    "experiment report generator",
    "research claim store",
    "ADR structure",
]


def _path(rel: str) -> Path:
    return REPO_ROOT / rel


def _read(rel: str) -> str:
    return _path(rel).read_text(encoding="utf-8")


def _assert_files(*paths: str) -> None:
    missing = [p for p in paths if not _path(p).is_file()]
    assert missing == []


def _assert_dirs(*paths: str) -> None:
    missing = [p for p in paths if not _path(p).is_dir()]
    assert missing == []


def _yaml(rel: str) -> dict[str, Any]:
    obj = yaml.safe_load(_read(rel))
    assert isinstance(obj, dict)
    return obj


def _settings_text() -> str:
    settings = json.loads(_read(".claude/settings.json"))
    return json.dumps(settings, sort_keys=True)


def _assert_text_contains(rel: str, *needles: str) -> None:
    text = _read(rel)
    missing = [needle for needle in needles if needle not in text]
    assert missing == []


def _assert_test_contains(rel: str, *test_names: str) -> None:
    _assert_text_contains(rel, *[f"def {name}" for name in test_names])


def _check_root_claude() -> None:
    _assert_files("CLAUDE.md")
    _assert_text_contains("CLAUDE.md", "docs/RESEARCH_CONTRACT.md", CONTRACT_SHA256[:8])


def _check_claude_rules() -> None:
    _assert_dirs(".claude/rules")
    _assert_files(
        ".claude/rules/coding-style.md",
        ".claude/rules/data-governance.md",
        ".claude/rules/experiment-safety.md",
        ".claude/rules/research-integrity.md",
    )


def _check_subagents() -> None:
    _assert_dirs(".claude/agents")
    agents = {p.name for p in _path(".claude/agents").glob("*.md")}
    assert agents == {"experiment-engineer.md", "paper-researcher.md", "research-reviewer.md"}


def _check_destructive_hook() -> None:
    _assert_files(".claude/hooks/guard_destructive.py", "tests/hooks/test_guard_destructive.py")
    settings = _settings_text()
    assert "guard_destructive.py" in settings
    assert "rm -rf data" in settings


def _check_experiment_launch_validation() -> None:
    _assert_files(
        ".claude/hooks/gate_experiment.py",
        "scripts/validate_spec.py",
        "src/pad_research/experiments/gate.py",
        "src/pad_research/experiments/validator.py",
        "tests/hooks/test_gate_experiment.py",
        "tests/unit/test_gate.py",
    )


def _check_uv_environment() -> None:
    _assert_files("pyproject.toml", "uv.lock", ".python-version")
    with _path("pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)
    assert pyproject["project"]["name"] == "pad-research"
    assert pyproject["project"]["requires-python"] == ">=3.11,<3.13"
    assert pyproject["tool"]["uv"]["default-groups"] == ["dev"]
    assert _read(".python-version").strip() == "3.11"


def _check_hydra_config() -> None:
    _assert_files("configs/config.yaml")
    _assert_dirs(
        "configs/model", "configs/data", "configs/adaptation", "configs/protocol", "configs/exp"
    )
    cfg = _yaml("configs/config.yaml")
    defaults = cfg["defaults"]
    assert any(item == {"model": "frame_baseline"} for item in defaults)
    assert any(item == {"data": "synthetic"} for item in defaults)
    exp_files = {p.name for p in _path("configs/exp").glob("*.yaml")}
    assert {
        "syn_e01_frame_source_only.yaml",
        "syn_e02_video_source_only.yaml",
        "syn_e03_video_full_ft_bf_only.yaml",
    }.issubset(exp_files)


def _check_dataset_manifest() -> None:
    _assert_files(
        "scripts/prepare_dataset.py",
        "src/pad_research/data/manifest.py",
        "src/pad_research/data/adapters/synthetic.py",
        "data/manifests/README.md",
        "data/manifests/synthetic_a.jsonl",
        "data/manifests/synthetic_a.meta.json",
        "data/manifests/synthetic_b.jsonl",
        "data/manifests/synthetic_b.meta.json",
        "tests/unit/test_manifest.py",
    )
    for dataset_id in ("synthetic_a", "synthetic_b"):
        meta = json.loads(_read(f"data/manifests/{dataset_id}.meta.json"))
        assert meta["dataset_id"] == dataset_id
        assert meta["pii_policy"] == "synthetic"
        assert meta["manifest_hash"]


def _check_protocol_schema() -> None:
    _assert_files(
        "src/pad_research/protocols/schema.py",
        "src/pad_research/protocols/validator.py",
        "tests/protocol/test_protocol_schema.py",
    )
    protocols = {p.name for p in _path("configs/protocol").glob("*.yaml")}
    assert {"syn_a_to_b_v1.yaml", "syn_a_to_b_bf_adapt_v1.yaml"}.issubset(protocols)


def _check_protocol_hash() -> None:
    _assert_files(
        "src/pad_research/protocols/hashing.py",
        "src/pad_research/protocols/compare.py",
        "tests/protocol/test_protocol_hash.py",
    )
    _assert_text_contains("configs/protocol/syn_a_to_b_v1.yaml", "protocol_id: syn_a_to_b_v1")


def _check_apcer_unit_test() -> None:
    _assert_test_contains(
        "tests/unit/test_metrics.py", "test_apcer_per_pai_toy", "test_apcer_max_toy"
    )


def _check_bpcer_unit_test() -> None:
    _assert_test_contains("tests/unit/test_metrics.py", "test_bpcer_toy")


def _check_acer_unit_test() -> None:
    _assert_test_contains("tests/unit/test_metrics.py", "test_acer_iso_max_pai")


def _check_hter_unit_test() -> None:
    _assert_test_contains("tests/unit/test_metrics.py", "test_hter_pooled")


def _check_auc_unit_test() -> None:
    _assert_test_contains("tests/unit/test_metrics.py", "test_auc_perfect")


def _check_mlflow_run_logging() -> None:
    _assert_files(
        "src/pad_research/tracking/mlflow_tracker.py",
        "src/pad_research/tracking/tags.py",
        "tests/unit/test_mlflow_tracker.py",
    )
    _assert_text_contains(
        "src/pad_research/tracking/mlflow_tracker.py",
        "class MlflowTracker",
        "start_run",
        "log_metrics",
    )


def _check_git_sha_logging() -> None:
    _assert_files(
        "src/pad_research/tracking/env_snapshot.py",
        "src/pad_research/experiments/registry.py",
        "tests/unit/test_env_snapshot.py",
    )
    _assert_text_contains("src/pad_research/tracking/env_snapshot.py", "git_sha", "as_tags")
    _assert_text_contains("src/pad_research/experiments/registry.py", "git_sha")


def _check_environment_metadata_logging() -> None:
    _assert_files("src/pad_research/tracking/env_snapshot.py", "tests/unit/test_env_snapshot.py")
    _assert_text_contains("scripts/train.py", "collect_env_snapshot", "env_snapshot.json")
    _assert_text_contains("scripts/adapt.py", "collect_env_snapshot", "env_snapshot.json")


def _check_smoke_test_mode() -> None:
    cfg = _yaml("configs/config.yaml")
    assert cfg["execution"]["mode"] == "smoke"
    smoke = cfg["execution"]["smoke"]
    assert smoke["max_epochs"] <= 1
    assert smoke["max_batches"] <= 20
    _assert_files(
        "src/pad_research/training/pipeline.py",
        "tests/integration/test_train_smoke.py",
    )
    _assert_text_contains("src/pad_research/training/pipeline.py", "effective_limits")


def _check_full_gpu_run_gate() -> None:
    _assert_files(
        "scripts/approve_full_run.py",
        "src/pad_research/experiments/gate.py",
        "tests/unit/test_gate.py",
        "tests/hooks/test_gate_experiment.py",
    )
    settings = _settings_text()
    assert "approve_full_run.py" in settings
    assert "Bash(uv run --no-sync python scripts/approve_full_run.py*)" in settings
    _assert_text_contains(
        "src/pad_research/experiments/gate.py", "GPU_OK", "SMOKE_OK", "SPEC_FROZEN"
    )


def _check_experiment_report_generator() -> None:
    _assert_files(
        "src/pad_research/reporting/template.py",
        "src/pad_research/reporting/report.py",
        "scripts/summarize_experiment.py",
        "tests/unit/test_report.py",
    )
    _assert_test_contains(
        "tests/unit/test_report.py", "test_report_contains_all_section44_headings"
    )


def _check_research_claim_store() -> None:
    _assert_files(
        "research/claims/claims.jsonl",
        "research/claims/README.md",
        "src/pad_research/research/claims.py",
        "tests/unit/test_claims.py",
        "tests/unit/test_research_store.py",
    )


def _check_adr_structure() -> None:
    _assert_files(
        "research/decisions/ADR-000-template.md",
        "research/decisions/ADR-001-use-video-input.md",
        "research/decisions/ADR-002-switch-dg-to-da.md",
        "research/decisions/ADR-003-real-only-target-setting.md",
        "research/decisions/ADR-004-protocol-lock.md",
        "research/decisions/ADR-005-harness-phase0-scope-and-conventions.md",
        "research/decisions/README.md",
        "tests/unit/test_research_store.py",
    )


DOD_CHECKS: list[tuple[int, str, Callable[[], None]]] = [
    (1, DOD_ITEMS[0], _check_root_claude),
    (2, DOD_ITEMS[1], _check_claude_rules),
    (3, DOD_ITEMS[2], _check_subagents),
    (4, DOD_ITEMS[3], _check_destructive_hook),
    (5, DOD_ITEMS[4], _check_experiment_launch_validation),
    (6, DOD_ITEMS[5], _check_uv_environment),
    (7, DOD_ITEMS[6], _check_hydra_config),
    (8, DOD_ITEMS[7], _check_dataset_manifest),
    (9, DOD_ITEMS[8], _check_protocol_schema),
    (10, DOD_ITEMS[9], _check_protocol_hash),
    (11, DOD_ITEMS[10], _check_apcer_unit_test),
    (12, DOD_ITEMS[11], _check_bpcer_unit_test),
    (13, DOD_ITEMS[12], _check_acer_unit_test),
    (14, DOD_ITEMS[13], _check_hter_unit_test),
    (15, DOD_ITEMS[14], _check_auc_unit_test),
    (16, DOD_ITEMS[15], _check_mlflow_run_logging),
    (17, DOD_ITEMS[16], _check_git_sha_logging),
    (18, DOD_ITEMS[17], _check_environment_metadata_logging),
    (19, DOD_ITEMS[18], _check_smoke_test_mode),
    (20, DOD_ITEMS[19], _check_full_gpu_run_gate),
    (21, DOD_ITEMS[20], _check_experiment_report_generator),
    (22, DOD_ITEMS[21], _check_research_claim_store),
    (23, DOD_ITEMS[22], _check_adr_structure),
]


def _contract_dod_items() -> list[str]:
    contract = CONTRACT.read_text(encoding="utf-8")
    section = contract.split("# 49. Definition of Done — Harness MVP", maxsplit=1)[1]
    section = section.split("---", maxsplit=1)[0]
    return [
        re.sub(r"^- \[ \] ", "", line) for line in section.splitlines() if line.startswith("- [ ] ")
    ]


def test_contract_sha_pinned_for_dod() -> None:
    digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    assert digest == CONTRACT_SHA256


def test_contract_section49_lists_expected_23_items() -> None:
    assert _contract_dod_items() == DOD_ITEMS
    assert len(DOD_CHECKS) == 23


@pytest.mark.parametrize(
    ("number", "item", "check"),
    DOD_CHECKS,
    ids=[
        f"{number:02d}-{item.replace('`', '').replace('/', '').replace(' ', '-')}"
        for number, item, _ in DOD_CHECKS
    ],
)
def test_dod_item_has_local_proof(number: int, item: str, check: Callable[[], None]) -> None:
    assert DOD_ITEMS[number - 1] == item
    check()


def test_readme_has_t11_operator_sections() -> None:
    text = README.read_text(encoding="utf-8")
    required = [
        "## Quickstart",
        "## Command cheat sheet",
        "## Smoke to full procedure",
        "## H100 migration checklist",
        "## `.claude/**` deny-promotion guidance",
        "## Agent-surface notes",
        "## Definition of Done evidence map",
        CONTRACT_SHA256,
        "SYNTHETIC SANITY",
        "scripts/approve_full_run.py",
        "gpt-5.5",
        "gpt-5.6-sol",
        "DEC-YYYYMMDD-NN",
    ]
    missing = [needle for needle in required if needle not in text]
    assert missing == []


def test_readme_maps_every_dod_item_to_a_local_proof() -> None:
    readme = README.read_text(encoding="utf-8")
    for number, item in enumerate(DOD_ITEMS, start=1):
        assert f"| {number} | {item} |" in readme
