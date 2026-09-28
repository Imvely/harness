#!/usr/bin/env python3
# ruff: noqa: E501  (project ruff config ignores E501; hooks are linted with --isolated)
"""PreToolUse(Edit|MultiEdit|Write|NotebookEdit) protection of research-semantic files.

Contract section 24.4: protected files may be edited, but the diff must be reviewed by the
human when research semantics change. Rule IDs PF-01..PF-11 (see _common.RULES).
file_path is absolute in real Claude Code payloads; it is resolved (realpath, symlinks) and
made project-relative before matching. Files outside the project are ignored except
~/.claude/** (PF-11). Fail-safe: any internal error -> ask("HK-99 ...").
"""
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as C  # noqa: E402

EDIT_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
EXECUTION_KEYS = (
    "mode",
    "allow_full_gpu_run",
    "allow_dirty_tree",
    "require_gpu",
    "expected_gpu",
    "smoke_test_first",
    "smoke",
)
PF05_PATTERNS = (
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/hooks/**",
    ".claude/rules/**",
    ".claude/agents/**",
    ".claude/skills/**",
    ".claude/commands/**",
)


# ---------------------------------------------------------------------------
# diff helpers (line based, no yaml parser: hooks are stdlib only)
# ---------------------------------------------------------------------------


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def old_new_texts(tool_name, tool_input, abs_path):
    """Return (old_text, new_text, context_known) for the edit."""
    existing = _read_text(abs_path)
    if tool_name == "Write":
        return existing or "", str(tool_input.get("content") or ""), existing is not None
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits")
        if not isinstance(edits, list):
            edits = []
        if existing is not None:
            new = existing
            for e in edits:
                if isinstance(e, dict):
                    new = new.replace(str(e.get("old_string") or ""), str(e.get("new_string") or ""), 1)
            return existing, new, True
        old = "\n".join(str(e.get("old_string") or "") for e in edits if isinstance(e, dict))
        new = "\n".join(str(e.get("new_string") or "") for e in edits if isinstance(e, dict))
        return old, new, False
    if tool_name == "NotebookEdit":
        return "", str(tool_input.get("new_source") or ""), False
    old = str(tool_input.get("old_string") or "")
    new = str(tool_input.get("new_string") or "")
    if existing is not None and old and old in existing:
        return existing, existing.replace(old, new, 1), True
    return old, new, False


def _key_paths(text):
    """For each line return (line, [top_key, sub_key...]) based on indentation."""
    out = []
    stack = []  # list of (indent, key)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out.append((line, [k for _, k in stack]))
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = stripped[2:] if stripped.startswith("- ") else stripped
        key = None
        if ":" in body and not body.startswith("{") and not body.startswith("["):
            cand = body.split(":", 1)[0].strip().strip("'\"")
            if cand and " " not in cand and not cand.startswith("$"):
                key = cand
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = [k for _, k in stack]
        if key is not None:
            path = path + [key]
            stack.append((indent, key))
        out.append((line, path))
    return out


def changed_key_paths(old, new):
    """Key paths (lists) of every line that differs between old and new."""
    old_kp = _key_paths(old)
    new_kp = _key_paths(new)
    sm = difflib.SequenceMatcher(a=[ln for ln, _ in old_kp], b=[ln for ln, _ in new_kp])
    paths = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        for _, p in old_kp[i1:i2]:
            paths.append(p)
        for _, p in new_kp[j1:j2]:
            paths.append(p)
    return paths


def changed_top_keys(old, new):
    keys = []
    for p in changed_key_paths(old, new):
        k = p[0] if p else "(top)"
        if k not in keys:
            keys.append(k)
    return keys


def execution_change(old, new, context_known):
    """Describe an execution.* change or return None."""
    hits = []
    for p in changed_key_paths(old, new):
        if not p:
            continue
        if p[0] == "execution":
            hits.append(".".join(p))
        elif not context_known and p[-1] in EXECUTION_KEYS and p[0] in EXECUTION_KEYS:
            # fragment without file context: an indented `mode:` line is likely execution.mode
            hits.append("execution?." + ".".join(p))
    if not hits:
        return None
    uniq = []
    for h in hits:
        if h not in uniq:
            uniq.append(h)
    return ", ".join(uniq[:6])


def summarize(old, new):
    keys = changed_top_keys(old, new)
    return "old %d chars -> new %d chars; changed top-level keys: %s" % (
        len(old),
        len(new),
        ", ".join(keys[:8]) if keys else "(none detected)",
    )


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------


def evaluate(tool_name, tool_input, cwd):
    """Return (decision or None, reason)."""
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(path, str) or not path:
        return "ask", "HK-00 tool_input.file_path missing"
    abs_path = path if os.path.isabs(path) else os.path.join(cwd, path)
    rel = C.rel_project_path(abs_path, cwd)
    if rel is None:
        real = os.path.realpath(abs_path)
        home_claude = os.path.realpath(os.path.join(os.path.expanduser("~"), ".claude"))
        if real == home_claude or real.startswith(home_claude + os.sep):
            return "ask", "PF-11 user-level Claude settings (%s) can disable the project guards; confirm this change" % real
        return None, ""
    # deny list: only scripts / the human write these
    if rel == "experiments/registry.jsonl":
        return "deny", "PF-08 experiments/registry.jsonl is a derived index written only by the training scripts (MLflow is the source of truth)"
    if C.matches_glob(rel, "experiments/approvals/**"):
        return "deny", "PF-08 experiments/approvals/** is written only by the human via scripts/approve_full_run.py"
    if C.matches_glob(rel, "experiments/specs/**") and rel.endswith(".resolved.yaml"):
        return "deny", "PF-09 %s is generated by `validate_spec --freeze`; never hand-edit a frozen spec" % rel
    old, new, context_known = old_new_texts(tool_name, tool_input, abs_path)
    if rel in ("CLAUDE.md", "docs/RESEARCH_CONTRACT.md"):
        return "ask", "PF-01 %s is the research constitution; approved revisions are recorded in an ADR and the pinned sha updated" % rel
    if C.matches_glob(rel, "data/manifests/**"):
        return "ask", "PF-02 %s: manifests are built by scripts/build_manifest.py; a manifest_hash change disconnects existing runs (section 15)" % rel
    if C.matches_glob(rel, "configs/protocol/**"):
        return "ask", "PF-03 %s: protocol_hash changes -> existing runs not comparable (section 15). %s" % (rel, summarize(old, new))
    if C.matches_glob(rel, "research/claims/**"):
        return "ask", "PF-04 %s: claims need a primary source; value stays null until verified (section 8)" % rel
    if C.matches_any(rel, PF05_PATTERNS):
        return "ask", "PF-05 %s is part of the guard rails (settings/hooks/rules/agents); confirm the change" % rel
    if rel == "uv.lock":
        return "ask", "PF-06 uv.lock change alters lock_hash recorded on every run; regenerate with `uv lock`, do not hand-edit"
    if C.matches_glob(rel, "experiments/specs/**"):
        return "ask", "PF-09 %s: frozen specs are produced by validate_spec --freeze" % rel
    if C.matches_glob(rel, "research/decisions/**") and os.path.basename(rel).startswith("ADR-") and rel.endswith(".md"):
        if os.path.exists(abs_path):
            return "ask", "PF-07 %s: existing ADRs are immutable history; add a new ADR that supersedes it" % rel
        return None, ""
    if C.matches_glob(rel, "configs/exp/**") or rel == "configs/config.yaml":
        change = execution_change(old, new, context_known)
        if change:
            return "ask", "PF-10 %s changes the full-run policy block (%s); execution.* decides whether a GPU full run may start (section 16)" % (rel, change)
        return None, ""
    return None, ""


def main():
    data = C.read_input()
    if data is None:
        C.ask("HK-00 hook stdin was not valid JSON; refusing to guess")
    tool_name = data.get("tool_name")
    if tool_name not in EDIT_TOOLS:
        C.no_decision()
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        C.ask("HK-00 tool_input missing or not an object")
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    decision, reason = evaluate(tool_name, tool_input, cwd)
    if decision is None:
        C.no_decision()
    C.decide(decision, reason)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: B036 - fail-safe by design
        try:
            C.ask("HK-99 hook internal error: %s: %s" % (type(exc).__name__, str(exc)[:200]))
        except SystemExit:
            raise
        except BaseException:  # noqa: B036
            sys.stdout.write('{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"HK-99 hook internal error"}}\n')
            sys.exit(0)
