"""Best-effort git state inspection (never raises)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitState:
    """Snapshot of the repository state used for provenance records."""

    sha: str | None
    short_sha: str | None
    branch: str | None
    dirty: bool
    untracked_count: int


def _run_git(root: Path, *args: str) -> str | None:
    """Run ``git -C root args`` and return stdout, or ``None`` on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def git_state(repo_root: Path) -> GitState:
    """Inspect the git repository at ``repo_root``.

    ``dirty`` reflects modifications to *tracked* files only; untracked files are reported
    separately via ``untracked_count``. When ``repo_root`` is not a git repository (or git is
    unavailable) every field is ``None``/``False``/``0``.
    """
    sha_out = _run_git(repo_root, "rev-parse", "HEAD")
    sha = sha_out.strip() if sha_out else None
    if sha is not None and not sha:
        sha = None

    short_out = _run_git(repo_root, "rev-parse", "--short", "HEAD") if sha else None
    short_sha = short_out.strip() if short_out else None

    branch_out = _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD") if sha else None
    branch = branch_out.strip() if branch_out else None
    if branch == "HEAD":  # detached
        branch = None

    inside = _run_git(repo_root, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.strip() != "true":
        return GitState(sha=sha, short_sha=short_sha, branch=branch, dirty=False, untracked_count=0)

    tracked_out = _run_git(repo_root, "status", "--porcelain", "--untracked-files=no")
    dirty = bool(tracked_out and tracked_out.strip())

    all_out = _run_git(repo_root, "status", "--porcelain", "--untracked-files=all")
    untracked_count = 0
    if all_out:
        untracked_count = sum(1 for line in all_out.splitlines() if line.startswith("??"))

    return GitState(
        sha=sha,
        short_sha=short_sha,
        branch=branch,
        dirty=dirty,
        untracked_count=untracked_count,
    )
