"""Checks for the Claude Code settings hook wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.hooks

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / ".claude" / "settings.json"


def _settings() -> dict[str, Any]:
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_settings_json_declares_required_hook_blocks() -> None:
    hooks = _settings()["hooks"]
    assert set(hooks) == {"PreToolUse", "PostToolUse", "SessionStart"}
    pre_matchers = {entry["matcher"] for entry in hooks["PreToolUse"]}
    assert "Bash" in pre_matchers
    assert "Edit|MultiEdit|Write|NotebookEdit" in pre_matchers
    assert hooks["PostToolUse"][0]["matcher"] == "Edit|MultiEdit|Write|NotebookEdit"
    assert hooks["SessionStart"][0]["matcher"] == "startup|resume|compact"


def test_settings_json_wires_experiment_and_file_guards() -> None:
    text = SETTINGS.read_text(encoding="utf-8")
    for script in (
        "guard_destructive.py",
        "gate_experiment.py",
        "protect_files.py",
        "post_edit_check.py",
        "session_start.py",
    ):
        assert script in text
