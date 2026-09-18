"""Structural tests for the research store: ADRs, hypotheses and the pinned contract."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DECISIONS = REPO_ROOT / "research" / "decisions"
HYPOTHESES = REPO_ROOT / "research" / "hypotheses"
CONTRACT = REPO_ROOT / "docs" / "RESEARCH_CONTRACT.md"

# Defined locally on purpose: this test must not depend on other modules' constants.
CONTRACT_SHA256 = "0562540579b17857205945eb5584d6fda07852c52c48c020d4ff3de2a632d35d"

ADR_FILES = {
    1: "ADR-001-use-video-input.md",
    2: "ADR-002-switch-dg-to-da.md",
    3: "ADR-003-real-only-target-setting.md",
    4: "ADR-004-protocol-lock.md",
    5: "ADR-005-harness-phase0-scope-and-conventions.md",
}
TEMPLATE_SECTIONS = [
    "## Status",
    "## Context",
    "## Decision",
    "## Alternatives Considered",
    "## Why",
    "## Risks",
    "## Evidence",
    "## Date",
]
DG_EXACT_SENTENCE = (
    "현재 사용한 데이터 구성, 구현, 전처리, 학습 조건에서 DG 계열 재현 성능이 기대보다 낮았으며, "
    "실제 Target 환경 데이터를 활용할 수 있는 제품 조건을 고려해 DA를 중심으로 연구 방향을 전환했다."
)


def _status_line(text: str) -> str:
    lines = text.splitlines()
    idx = lines.index("## Status")
    return lines[idx + 1].strip()


@pytest.mark.parametrize("number", sorted(ADR_FILES))
def test_adrs_have_status_accepted(number: int) -> None:
    text = (DECISIONS / ADR_FILES[number]).read_text(encoding="utf-8")
    assert text.startswith(f"# ADR-{number:03d} — ")
    assert _status_line(text) == "Accepted"
    for section in TEMPLATE_SECTIONS:
        assert section in text, f"ADR-{number:03d} missing {section}"
    assert re.search(r"^## Date\n2026-09-17\s*$", text, flags=re.MULTILINE)


def test_adr_template_matches_contract_section_26() -> None:
    template = (DECISIONS / "ADR-000-template.md").read_text(encoding="utf-8")
    assert template.startswith("# ADR-XXX — 제목\n")
    assert _status_line(template) == "Accepted / Proposed / Superseded"
    assert [ln for ln in template.splitlines() if ln.startswith("## ")] == TEMPLATE_SECTIONS
    contract = CONTRACT.read_text(encoding="utf-8")
    assert template.strip() in contract


def test_adr_002_records_exact_wording_and_forbidden_generalizations() -> None:
    text = (DECISIONS / ADR_FILES[2]).read_text(encoding="utf-8")
    assert DG_EXACT_SENTENCE in text
    assert '"DG는 모두 안 된다" ❌' in text
    assert '"해당 논문은 성능을 조작했다" ❌' in text


def test_adr_004_records_hash_rules() -> None:
    text = (DECISIONS / ADR_FILES[4]).read_text(encoding="utf-8")
    assert 'HASH_EXCLUDED = {"description", "parent_protocol_id", "change_note", "status"}' in text
    assert "`protocol_id`는 hash에 포함" in text
    assert "--justify" in text
    assert "adaptation.enabled ⇒ protocol.target_adaptation.enabled" in text


def test_adr_readme_indexes_every_adr() -> None:
    readme = (DECISIONS / "README.md").read_text(encoding="utf-8")
    for name in ["ADR-000-template.md", *ADR_FILES.values()]:
        assert name in readme, name


@pytest.mark.parametrize("name", ["H1", "H2", "H3", "H4"])
def test_hypotheses_exist(name: str) -> None:
    text = (HYPOTHESES / f"{name}.md").read_text(encoding="utf-8")
    assert text.startswith(f"# {name} — ")
    assert "untested" in text
    assert "synthetic runs are NOT evidence" in text
    assert re.search(r"\bE0[1-7]\b", text)


def test_contract_sha_pinned() -> None:
    digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    assert digest == CONTRACT_SHA256, (
        "docs/RESEARCH_CONTRACT.md changed; the contract is verbatim and pinned (ADR-005). "
        "If the change is intended, update the pin here and in conventions.CONTRACT_SHA256."
    )
