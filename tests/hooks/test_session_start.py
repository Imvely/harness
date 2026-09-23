"""Tests for .claude/hooks/session_start.py (SessionStart brief; must never fail)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from .conftest import REPO_ROOT, TmpProject, run_hook

pytestmark = pytest.mark.hooks


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def test_prints_branch_in_tmp_repo(tmp_project: TmpProject, load_fixture) -> None:
    _git(tmp_project.root, "init", "-q", "-b", "main")
    _git(tmp_project.root, "add", "pyproject.toml")
    _git(tmp_project.root, "commit", "-q", "-m", "init")
    tmp_project.write(
        "experiments/registry.jsonl",
        "\n".join(
            json.dumps(
                {
                    "timestamp": "2026-09-18T00:00:00",
                    "experiment_id": f"exp_{i}",
                    "mode": "smoke",
                    "status": "smoke_ok",
                    "run_id": "abcdef1234",
                    "protocol_hash": "c" * 64,
                }
            )
            for i in range(7)
        )
        + "\n",
    )
    res = tmp_project.run("session_start", load_fixture("session_start.json", tmp_project.root))
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert lines and any(ln.startswith("[pad-harness] branch=main sha=") for ln in lines)
    assert len(lines) <= 45
    assert any(ln.startswith("env: python=") and "torch=" in ln and "lock=" in ln for ln in lines)
    assert any("registry (last 5 of 7)" in ln for ln in lines)
    assert any("exp_6" in ln for ln in lines) and not any("exp_1 " in ln for ln in lines)
    assert any(ln.startswith("ADRs: ADR-001 [Accepted]") for ln in lines)
    assert any(ln.startswith("configs/exp: exp_a") for ln in lines)
    assert any("protocols: 1 active / 1 total" in ln for ln in lines)
    assert any("RESEARCH_CONTRACT.md differs" in ln for ln in lines)  # tmp contract != pinned sha
    assert any(ln.startswith("reminder:") and "Research" in ln for ln in lines)


def test_warns_on_disabled_hooks_and_bash_star(tmp_project: TmpProject, tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text('{"disableAllHooks": true}', encoding="utf-8")
    tmp_project.write(".claude/settings.local.json", '{"permissions": {"allow": ["Bash(*)"]}}')
    res = tmp_project.run(
        "session_start",
        {},
        env=dict(tmp_project.env, HOME=str(home), USERPROFILE=str(home)),
    )
    assert res.returncode == 0
    first_two = res.stdout.splitlines()[:2]
    assert any("disableAllHooks" in ln for ln in first_two)
    assert any("Bash(*)" in ln for ln in first_two)


def test_never_fails_without_git_or_stdin(tmp_project: TmpProject) -> None:
    res = tmp_project.run("session_start", None, raw_stdin="")
    assert res.returncode == 0
    assert "branch=?" in res.stdout
    res = tmp_project.run("session_start", None, raw_stdin="garbage")
    assert res.returncode == 0


def test_real_repo_brief(load_fixture) -> None:
    res = run_hook("session_start", load_fixture("session_start.json", REPO_ROOT))
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert lines[0].startswith("[pad-harness] branch=") or "WARNING" in lines[0]
    assert len(lines) <= 45
    assert not any("RESEARCH_CONTRACT.md differs" in ln for ln in lines), (
        "contract sha drifted from the pinned value"
    )
