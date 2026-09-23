"""Structural tests for the CI workflow."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_contains_required_phase0_steps() -> None:
    text = CI.read_text(encoding="utf-8")
    required = [
        "uses: astral-sh/setup-uv@v6",
        "uv sync --frozen",
        "uv run --no-sync ruff check .",
        "uv run --no-sync pyright src scripts",
        "uv run --no-sync python scripts/prepare_dataset.py --adapter synthetic --dataset-id synthetic_a --dataset-id synthetic_b",
        'uv run --no-sync pytest -q -m "not slow"',
    ]
    missing = [needle for needle in required if needle not in text]
    assert missing == []


def test_ci_workflow_uses_only_synthetic_data_and_no_full_approval() -> None:
    text = CI.read_text(encoding="utf-8")
    forbidden = [
        "scripts/approve_full_run.py",
        "ALLOW_FULL",
        "data/raw",
        "dvc pull",
        "dvc push",
    ]
    present = [needle for needle in forbidden if needle in text]
    assert present == []


def test_ci_workflow_builds_web_mockup() -> None:
    text = CI.read_text(encoding="utf-8")
    required = [
        "web-mockup:",
        "uses: oven-sh/setup-bun@v2",
        "working-directory: web-mockup",
        "bun install --frozen-lockfile",
        "bun run build",
    ]
    missing = [needle for needle in required if needle not in text]
    assert missing == []
