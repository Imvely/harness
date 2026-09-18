"""Research store: verified paper claims and the paper index.

Implements the claim structure of RESEARCH_CONTRACT §8.2 and the paper index of §7.

Rules enforced at the type level (§8.1 / §8.2):

* a numeric ``value`` may only be recorded once the claim is ``verified`` **and** the
  source is the primary paper or a local observation — never a secondary source;
* a ``secondary`` source (blog, related-work table, README, search snippet) can never be
  marked ``verified``;
* while a value is unverified it stays ``null``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

SourceType = Literal["primary_paper", "official_code", "secondary", "local_observation"]
CodeStatus = Literal["verify", "available", "unavailable", "partial"]

#: ``paper_id`` used for claims that come from this repository's own runs, not a paper.
LOCAL_PAPER_ID = "local"

#: Only these source types may carry a numeric value (§8.1: no numbers from secondaries).
VALUE_ALLOWED_SOURCE_TYPES: frozenset[str] = frozenset({"primary_paper", "local_observation"})


class ClaimsFileError(ValueError):
    """Raised by :func:`load_claims` / :func:`load_paper_index` when a file is invalid."""

    def __init__(self, path: Path, errors: list[str]) -> None:
        self.path = path
        self.errors = errors
        joined = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"{path}: {len(errors)} error(s)\n{joined}")


class Claim(BaseModel):
    """One row of ``research/claims/claims.jsonl`` (§8.2)."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim: str
    paper_id: str
    source_type: SourceType
    section: str
    table: str
    protocol: str
    metric: str
    value: float | None
    verified: bool
    notes: str
    verified_by: str | None = None
    verified_at: str | None = None

    @model_validator(mode="after")
    def _check_evidence_rules(self) -> Claim:
        if self.source_type == "secondary" and self.verified:
            raise ValueError(
                "source_type='secondary' can never be verified (§8.1); "
                "confirm from the primary paper and change source_type"
            )
        if self.value is not None:
            if not self.verified:
                raise ValueError(
                    "value must stay null until the claim is verified (§8.2); "
                    "set verified=true (with verified_by/verified_at) or value=null"
                )
            if self.source_type not in VALUE_ALLOWED_SOURCE_TYPES:
                raise ValueError(
                    "a numeric value requires source_type in "
                    f"{sorted(VALUE_ALLOWED_SOURCE_TYPES)}, got {self.source_type!r}"
                )
        return self


class PaperEntry(BaseModel):
    """One entry of ``research/papers/paper_index.yaml`` (§7 reading list)."""

    model_config = ConfigDict(extra="forbid")

    paper_id: str
    title: str
    venue: str
    year: int
    urls: list[str]
    code_url: str | None = None
    code_status: CodeStatus = "verify"
    review: str | None = None


def _format_validation_error(err: ValidationError) -> str:
    parts = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "<root>"
        msg = e["msg"]
        parts.append(f"{loc}: {msg}")
    return "; ".join(parts)


def _iter_jsonl(path: Path) -> Iterable[tuple[int, str]]:
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            yield lineno, line


def _parse_claims(path: Path) -> tuple[list[Claim], list[str]]:
    claims: list[Claim] = []
    errors: list[str] = []
    seen: dict[str, int] = {}
    if not path.is_file():
        return claims, [f"file not found: {path}"]
    for lineno, line in _iter_jsonl(path):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {lineno}: invalid JSON: {exc.msg} (col {exc.colno})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"line {lineno}: expected a JSON object, got {type(obj).__name__}")
            continue
        try:
            claim = Claim.model_validate(obj)
        except ValidationError as exc:
            cid = obj.get("claim_id", "<no claim_id>")
            errors.append(f"line {lineno} ({cid}): {_format_validation_error(exc)}")
            continue
        if claim.claim_id in seen:
            errors.append(
                f"line {lineno}: duplicate claim_id {claim.claim_id!r} "
                f"(first seen on line {seen[claim.claim_id]})"
            )
            continue
        seen[claim.claim_id] = lineno
        claims.append(claim)
    return claims, errors


def validate_claims_file(path: str | Path) -> list[str]:
    """Return a list of human-readable errors for a claims JSONL file (empty = valid)."""
    _, errors = _parse_claims(Path(path))
    return errors


def load_claims(path: str | Path) -> list[Claim]:
    """Load and validate ``claims.jsonl``; raise :class:`ClaimsFileError` on any problem."""
    p = Path(path)
    claims, errors = _parse_claims(p)
    if errors:
        raise ClaimsFileError(p, errors)
    return claims


def _parse_paper_index(path: Path) -> tuple[list[PaperEntry], list[str]]:
    entries: list[PaperEntry] = []
    errors: list[str] = []
    if not path.is_file():
        return entries, [f"file not found: {path}"]
    try:
        with path.open(encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return entries, [f"invalid YAML: {exc}"]
    if not isinstance(doc, dict) or "papers" not in doc:
        return entries, ["top-level must be a mapping with a 'papers' list"]
    papers = doc["papers"]
    if not isinstance(papers, list):
        return entries, ["'papers' must be a list"]
    seen: dict[str, int] = {}
    for idx, item in enumerate(papers):
        if not isinstance(item, dict):
            errors.append(f"papers[{idx}]: expected a mapping, got {type(item).__name__}")
            continue
        try:
            entry = PaperEntry.model_validate(item)
        except ValidationError as exc:
            pid = item.get("paper_id", "<no paper_id>")
            errors.append(f"papers[{idx}] ({pid}): {_format_validation_error(exc)}")
            continue
        if entry.paper_id in seen:
            errors.append(
                f"papers[{idx}]: duplicate paper_id {entry.paper_id!r} "
                f"(first seen at papers[{seen[entry.paper_id]}])"
            )
            continue
        seen[entry.paper_id] = idx
        entries.append(entry)
    return entries, errors


def validate_paper_index(path: str | Path) -> list[str]:
    """Return a list of human-readable errors for ``paper_index.yaml`` (empty = valid)."""
    _, errors = _parse_paper_index(Path(path))
    return errors


def load_paper_index(path: str | Path) -> list[PaperEntry]:
    """Load and validate ``paper_index.yaml``; raise :class:`ClaimsFileError` on any problem."""
    p = Path(path)
    entries, errors = _parse_paper_index(p)
    if errors:
        raise ClaimsFileError(p, errors)
    return entries


def check_claim_paper_ids(claims: Iterable[Claim], papers: Iterable[PaperEntry]) -> list[str]:
    """Cross-check: every non-local claim must reference a paper_id present in the index."""
    known = {p.paper_id for p in papers}
    return [
        f"claim {c.claim_id!r}: unknown paper_id {c.paper_id!r}"
        for c in claims
        if c.paper_id != LOCAL_PAPER_ID and c.paper_id not in known
    ]
