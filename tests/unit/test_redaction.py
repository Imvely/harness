"""Tests for path/URI redaction before data leaves the harness."""

from __future__ import annotations

from pathlib import Path

from pad_research.utils.redaction import (
    PATH_REDACTION,
    URI_REDACTION,
    redact_tag_value,
    redact_text,
)


def test_redact_text_removes_absolute_and_protected_paths(tmp_path: Path) -> None:
    message = (
        f"failed loading {tmp_path / 'data' / 'processed' / 'clip.npy'} "
        "and checkpoints/model.pt"
    )

    redacted = redact_text(message, tmp_path)

    assert str(tmp_path) not in redacted
    assert "data/processed" not in redacted
    assert "checkpoints/model.pt" not in redacted
    assert PATH_REDACTION in redacted


def test_redact_text_removes_remote_uris() -> None:
    redacted = redact_text("remote artifact at https://example.test/mlruns/1")

    assert "https://example.test" not in redacted
    assert URI_REDACTION in redacted


def test_redact_tag_value_preserves_safe_metadata_and_collapses_sensitive_values(
    tmp_path: Path,
) -> None:
    assert redact_tag_value("exp_demo", tmp_path) == "exp_demo"
    assert redact_tag_value(tmp_path / "checkpoints" / "model.pt", tmp_path) == PATH_REDACTION
