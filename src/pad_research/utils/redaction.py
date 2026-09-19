"""Redaction helpers for values that may leave the local machine.

The harness stores MLflow tags, registry notes and dashboard JSON.  Those channels must
not expose local data roots, checkpoint locations or remote artifact URIs.
"""

from __future__ import annotations

import re
from pathlib import Path

PATH_REDACTION = "[REDACTED_PATH]"
URI_REDACTION = "[REDACTED_URI]"

_URI_RE = re.compile(r"\b(?:https?|s3|gs|ssh|scp|rsync|file)://[^\s\"'`,;)]*", re.I)
_WINDOWS_ABS_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\s\"'`,;)]*")
_UNC_RE = re.compile(r"\\\\[^\s\"'`,;)]*")
_POSIX_ABS_RE = re.compile(
    r"(?<!:)/(?:home|users|mnt|media|data|tmp|var|opt|srv|workspace|root)[^\s\"'`,;)]*",
    re.I,
)
_REL_PROTECTED_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])"
    r"(?:"
    r"data/(?:raw|processed)(?:/[^\s\"'`,;)]*)?"
    r"|checkpoints/[^\s\"'`,;)]*"
    r"|artifacts/[^\s\"'`,;)]*"
    r"|mlruns(?:_artifacts)?(?:\.db|/[^\s\"'`,;)]*)"
    r")"
)


def _normalise(value: str) -> str:
    return value.replace("\\", "/").lower()


def _repo_text(repo_root: Path | None) -> str | None:
    if repo_root is None:
        return None
    try:
        return _normalise(str(repo_root.expanduser().resolve()))
    except OSError:
        return _normalise(str(repo_root.expanduser()))


def is_sensitive_text(value: object, repo_root: Path | None = None) -> bool:
    """Return true when ``value`` looks like a local/remote path that should not be exported."""

    if value is None:
        return False
    text = str(value)
    if not text:
        return False
    repo = _repo_text(repo_root)
    return (
        (repo is not None and repo in _normalise(text))
        or _REL_PROTECTED_RE.search(text.replace("\\", "/")) is not None
        or _URI_RE.search(text) is not None
        or _WINDOWS_ABS_RE.search(text) is not None
        or _UNC_RE.search(text) is not None
        or _POSIX_ABS_RE.search(text) is not None
    )


def redact_text(value: object, repo_root: Path | None = None) -> str:
    """Redact path-like substrings while preserving the surrounding diagnostic message."""

    if value is None:
        return ""
    text = str(value)
    repo = _repo_text(repo_root)
    if repo:
        text = text.replace(repo, PATH_REDACTION)
        text = text.replace(repo.replace("/", "\\"), PATH_REDACTION)
    text = _URI_RE.sub(URI_REDACTION, text)
    text = _WINDOWS_ABS_RE.sub(PATH_REDACTION, text)
    text = _UNC_RE.sub(PATH_REDACTION, text)
    text = _POSIX_ABS_RE.sub(PATH_REDACTION, text)
    text = _REL_PROTECTED_RE.sub(PATH_REDACTION, text.replace("\\", "/"))
    return text


def redact_tag_value(value: object, repo_root: Path | None = None) -> str:
    """Return a safe one-line tag value."""

    text = str(value)
    return PATH_REDACTION if is_sensitive_text(text, repo_root) else text


__all__ = ["PATH_REDACTION", "URI_REDACTION", "is_sensitive_text", "redact_tag_value", "redact_text"]
