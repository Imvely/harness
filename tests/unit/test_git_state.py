"""Tests for best-effort git state inspection."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pad_research.utils.git import GitState, git_state


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_clean_repo(repo: Path) -> None:
    state = git_state(repo)
    assert isinstance(state, GitState)
    assert state.sha is not None and len(state.sha) == 40
    assert state.short_sha is not None and state.sha.startswith(state.short_sha)
    assert state.branch == "main"
    assert state.dirty is False
    assert state.untracked_count == 0


def test_tracked_modification_is_dirty(repo: Path) -> None:
    (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")
    state = git_state(repo)
    assert state.dirty is True
    assert state.untracked_count == 0


def test_untracked_file_is_not_dirty_but_counted(repo: Path) -> None:
    (repo / "new.txt").write_text("x\n", encoding="utf-8")
    state = git_state(repo)
    assert state.dirty is False
    assert state.untracked_count == 1


def test_non_repo_directory_never_raises(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    state = git_state(plain)
    assert state == GitState(sha=None, short_sha=None, branch=None, dirty=False, untracked_count=0)


def test_missing_directory_never_raises(tmp_path: Path) -> None:
    state = git_state(tmp_path / "does_not_exist")
    assert state.sha is None
    assert state.dirty is False
