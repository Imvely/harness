"""Unit tests for human approval-token helpers."""

from __future__ import annotations

from pathlib import Path

from pad_research.experiments.approvals import ApprovalToken, read_token, token_path, write_token


def test_write_read_roundtrip(tmp_path: Path) -> None:
    science_hash = "a" * 64
    path = write_token("exp_a", science_hash, "b" * 40, tmp_path)
    assert path == token_path("exp_a", science_hash, tmp_path)
    token = read_token("exp_a", science_hash, tmp_path)
    assert token is not None
    assert token.experiment_id == "exp_a"
    assert token.science_hash == science_hash
    assert token.git_sha == "b" * 40
    assert token.approved_by


def test_mismatch_returns_none(tmp_path: Path) -> None:
    science_hash = "a" * 64
    wrong_exp = ApprovalToken(
        experiment_id="exp_other",
        science_hash=science_hash,
        git_sha=None,
        approved_at="2026-01-01T00:00:00+00:00",
        approved_by="human",
    )
    token_path("exp_a", science_hash, tmp_path).write_text(
        wrong_exp.model_dump_json(),
        encoding="utf-8",
    )
    assert read_token("exp_a", science_hash, tmp_path) is None

    wrong_hash = ApprovalToken(
        experiment_id="exp_a",
        science_hash="b" * 64,
        git_sha=None,
        approved_at="2026-01-01T00:00:00+00:00",
        approved_by="human",
    )
    token_path("exp_a", science_hash, tmp_path).write_text(
        wrong_hash.model_dump_json(),
        encoding="utf-8",
    )
    assert read_token("exp_a", science_hash, tmp_path) is None
