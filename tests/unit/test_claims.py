"""Unit tests for the research claim store (RESEARCH_CONTRACT §8.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pad_research.research.claims import (
    Claim,
    ClaimsFileError,
    PaperEntry,
    check_claim_paper_ids,
    load_claims,
    load_paper_index,
    validate_claims_file,
    validate_paper_index,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAIMS_PATH = REPO_ROOT / "research" / "claims" / "claims.jsonl"
PAPER_INDEX_PATH = REPO_ROOT / "research" / "papers" / "paper_index.yaml"

BASE_CLAIM: dict[str, object] = {
    "claim_id": "x_001",
    "claim": "some claim",
    "paper_id": "li2025ota",
    "source_type": "primary_paper",
    "section": "s",
    "table": "VERIFY_FROM_PDF",
    "protocol": "VERIFY_FROM_PDF",
    "metric": "HTER",
    "value": None,
    "verified": False,
    "notes": "n",
}


def _claim(**overrides: object) -> dict[str, object]:
    return {**BASE_CLAIM, **overrides}


def _write_jsonl(path: Path, rows: list[object]) -> Path:
    path.write_text(
        "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )
    return path


def test_all_claims_parse() -> None:
    assert validate_claims_file(CLAIMS_PATH) == []
    claims = load_claims(CLAIMS_PATH)
    ids = {c.claim_id for c in claims}
    assert {"ota_2025_oneclass_001", "local_dg_repro_001"} <= ids
    ota = next(c for c in claims if c.claim_id == "ota_2025_oneclass_001")
    assert ota.value is None and ota.verified is False and ota.paper_id == "li2025ota"
    local = next(c for c in claims if c.claim_id == "local_dg_repro_001")
    assert local.source_type == "local_observation" and local.paper_id == "local"
    assert local.verified is True and local.value is None
    # every non-local claim must point at an indexed paper
    assert check_claim_paper_ids(claims, load_paper_index(PAPER_INDEX_PATH)) == []


def test_unverified_claim_value_must_be_null() -> None:
    with pytest.raises(ValidationError, match="value must stay null"):
        Claim.model_validate(_claim(value=3.2, verified=False))
    # verified + primary_paper may carry a value
    ok = Claim.model_validate(
        _claim(value=3.2, verified=True, verified_by="me", verified_at="2026-09-17")
    )
    assert ok.value == 3.2
    # verified official_code still may not carry a numeric value
    with pytest.raises(ValidationError, match="requires source_type"):
        Claim.model_validate(_claim(value=3.2, verified=True, source_type="official_code"))


def test_secondary_cannot_be_verified() -> None:
    with pytest.raises(ValidationError, match="never be verified"):
        Claim.model_validate(_claim(source_type="secondary", verified=True))
    with pytest.raises(ValidationError):
        Claim.model_validate(_claim(source_type="secondary", verified=True, value=1.0))
    unverified = Claim.model_validate(_claim(source_type="secondary", verified=False))
    assert unverified.value is None


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(_claim(bonus="nope"))


def test_duplicate_claim_id_detected(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "claims.jsonl", [_claim(claim_id="dup"), _claim(claim_id="dup")])
    errors = validate_claims_file(path)
    assert len(errors) == 1
    assert "duplicate claim_id 'dup'" in errors[0] and "line 2" in errors[0]
    with pytest.raises(ClaimsFileError) as excinfo:
        load_claims(path)
    assert excinfo.value.errors == errors


def test_json_parse_error_reports_line_number(tmp_path: Path) -> None:
    path = _write_jsonl(
        tmp_path / "claims.jsonl",
        [_claim(claim_id="a"), "{not json", _claim(claim_id="b", value=1.0)],
    )
    errors = validate_claims_file(path)
    assert any(e.startswith("line 2: invalid JSON") for e in errors)
    assert any(e.startswith("line 3 (b)") and "value must stay null" in e for e in errors)
    assert len(errors) == 2


def test_missing_claims_file_is_an_error(tmp_path: Path) -> None:
    assert validate_claims_file(tmp_path / "nope.jsonl") == [
        f"file not found: {tmp_path / 'nope.jsonl'}"
    ]


def test_paper_index_loads_nine_papers() -> None:
    assert validate_paper_index(PAPER_INDEX_PATH) == []
    papers = load_paper_index(PAPER_INDEX_PATH)
    assert len(papers) == 9
    assert [p.paper_id for p in papers] == [
        "liu2018auxiliary",
        "yu2020cdcn",
        "wang2022ttn",
        "yang2025g2v2former",
        "liu2022sdafas",
        "guo2022mdl",
        "liu2024sdafaspp",
        "he2024ccga",
        "li2025ota",
    ]
    for p in papers:
        assert p.urls, p.paper_id
        assert p.code_status == "verify" and p.review is None
    by_id = {p.paper_id: p for p in papers}
    assert by_id["yu2020cdcn"].code_url == "https://github.com/ZitongYu/CDCN"
    assert by_id["liu2022sdafas"].code_url == "https://github.com/YuchenLiu98/ECCV2022-SDA-FAS"
    assert by_id["li2025ota"].venue == "CVPR" and by_id["li2025ota"].year == 2025


def test_paper_index_validation_errors(tmp_path: Path) -> None:
    entry = PaperEntry(paper_id="p", title="t", venue="v", year=2020, urls=["u"]).model_dump()
    bad = tmp_path / "idx.yaml"
    bad.write_text(
        json.dumps({"papers": [entry, entry, {**entry, "paper_id": "q", "code_status": "??"}]}),
        encoding="utf-8",
    )
    errors = validate_paper_index(bad)
    assert any("duplicate paper_id 'p'" in e for e in errors)
    assert any("(q)" in e and "code_status" in e for e in errors)
    with pytest.raises(ClaimsFileError):
        load_paper_index(bad)
    (tmp_path / "list.yaml").write_text("- a\n", encoding="utf-8")
    assert validate_paper_index(tmp_path / "list.yaml") == [
        "top-level must be a mapping with a 'papers' list"
    ]
