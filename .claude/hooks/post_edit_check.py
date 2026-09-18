#!/usr/bin/env python3
# ruff: noqa: E501  (project ruff config ignores E501; hooks are linted with --isolated)
"""PostToolUse(Edit|MultiEdit|Write|NotebookEdit): ruff + targeted pytest / yaml validation.

Contract section 24.2: after a Python edit run `ruff check` and the *targeted* tests for the
edited module. Never the full suite, never integration tests (except the cheap
tests/integration/test_validate_cli.py for the two validator scripts).
Failure -> exit 2 + concise stderr (Claude sees it). Missing mapping -> exit 0 + stdout note.
Every subprocess uses `uv run --no-sync` so the hook never re-locks the environment.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as C  # noqa: E402

PY_ROOTS = ("src/", "tests/", "scripts/", ".claude/hooks/")
RUFF_TIMEOUT_S = 60
PYTEST_TIMEOUT_S = 100  # hook timeout in settings.json is 120 s
YAML_TIMEOUT_S = 60
MAX_LINES = 15


def map_tests(rel, root):
    """Explicit mapping edited file -> candidate test files (existing ones only).

    Returns (files, note). note is set when no mapping exists on purpose.
    """
    candidates = []
    note = ""
    if rel.startswith("tests/"):
        base = os.path.basename(rel)
        if base.startswith("test_") and rel.endswith(".py"):
            candidates.append(rel)
        else:
            note = "no direct test for %s (conftest/helper)" % rel
    elif rel.startswith("src/pad_research/"):
        parts = rel[len("src/pad_research/") :].split("/")
        mod = parts[-1][:-3]
        if len(parts) == 1:
            candidates.append("tests/unit/test_%s.py" % mod)
        else:
            pkg = parts[0]
            candidates.append("tests/unit/test_%s.py" % mod)
            candidates.append("tests/unit/test_%s_%s.py" % (pkg, mod))
            if pkg == "protocols":
                proto_dir = os.path.join(root, "tests", "protocol")
                if os.path.isdir(proto_dir):
                    for name in sorted(os.listdir(proto_dir)):
                        if name.startswith("test_") and name.endswith(".py"):
                            candidates.append("tests/protocol/" + name)
    elif rel in ("scripts/validate_spec.py", "scripts/validate_protocol.py"):
        candidates.append("tests/integration/test_validate_cli.py")
    elif rel.startswith("scripts/"):
        note = "no hook test for %s: integration tests run via `make test`, not per edit (section 24.2)" % rel
    elif rel.startswith(".claude/hooks/"):
        name = os.path.basename(rel)[:-3]
        candidates.append("tests/hooks/test_common.py" if name == "_common" else "tests/hooks/test_%s.py" % name)
    files = []
    for c in candidates:
        if os.path.exists(os.path.join(root, c)) and c not in files:
            files.append(c)
    if not files and not note:
        note = "no mapped test file exists for %s (expected %s)" % (rel, ", ".join(candidates) or "n/a")
    return files, note


def _run(cmd, root, timeout):
    try:
        proc = subprocess.run(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %ss: %s" % (timeout, " ".join(cmd))
    except OSError as exc:
        return 127, "", "could not start %s: %s" % (cmd[0], exc)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def _fail(title, out, err):
    lines = [ln for ln in (out + "\n" + err).splitlines() if ln.strip()]
    interesting = [ln for ln in lines if ("FAILED" in ln or "Error" in ln or "error" in ln or "assert" in ln or ".py:" in ln)]
    shown = (interesting or lines)[-MAX_LINES:]
    sys.stderr.write("[post_edit_check] %s\n" % title)
    for ln in shown:
        sys.stderr.write("  %s\n" % ln[:300])
    sys.stderr.flush()
    sys.exit(2)


def check_python(rel, root):
    code, out, err = _run(["uv", "run", "--no-sync", "ruff", "check", "--output-format", "concise", rel], root, RUFF_TIMEOUT_S)
    if code != 0:
        _fail("ruff check failed for %s (fix with `uv run --no-sync ruff check --fix %s`)" % (rel, rel), out, err)
    files, note = map_tests(rel, root)
    if not files:
        sys.stdout.write("[post_edit_check] ruff ok; %s\n" % note)
        return
    cmd = ["uv", "run", "--no-sync", "pytest", "-q", "-x", "-p", "no:cacheprovider", "--timeout", "60", "-m", "not slow and not integration"] + files
    code, out, err = _run(cmd, root, PYTEST_TIMEOUT_S)
    if code == 5:  # no tests collected (all deselected)
        sys.stdout.write("[post_edit_check] ruff ok; no non-slow tests collected in %s\n" % ", ".join(files))
        return
    if code != 0:
        _fail("targeted tests failed for %s -> %s" % (rel, ", ".join(files)), out, err)
    sys.stdout.write("[post_edit_check] ruff ok; tests ok: %s\n" % ", ".join(files))


def check_yaml(rel, root):
    if rel.startswith("configs/protocol/"):
        cmd = ["uv", "run", "--no-sync", "python", "scripts/validate_protocol.py", "--path", rel, "--schema-only", "--json"]
    elif rel.startswith("configs/exp/"):
        name = os.path.basename(rel).rsplit(".", 1)[0]
        cmd = ["uv", "run", "--no-sync", "python", "scripts/validate_spec.py", "--exp", name, "--json"]
    else:
        cmd = ["uv", "run", "--no-sync", "python", "-c", "import sys, yaml; yaml.safe_load(open(sys.argv[1], encoding='utf-8'))", rel]
    if cmd[4] != "-c" and not os.path.exists(os.path.join(root, cmd[4])):
        sys.stdout.write("[post_edit_check] %s not present yet; skipped yaml validation of %s\n" % (cmd[4], rel))
        return
    code, out, err = _run(cmd, root, YAML_TIMEOUT_S)
    if code != 0:
        _fail("yaml validation failed for %s (%s)" % (rel, " ".join(cmd[3:])), out, err)
    sys.stdout.write("[post_edit_check] yaml ok: %s\n" % rel)


def main():
    data = C.read_input()
    if data is None:
        return
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(path, str) or not path:
        return
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    abs_path = path if os.path.isabs(path) else os.path.join(cwd, path)
    rel = C.rel_project_path(abs_path, cwd)
    if rel is None or not os.path.exists(abs_path):
        return
    root = C.project_root()
    if rel.endswith(".py") and any(rel.startswith(p) for p in PY_ROOTS):
        check_python(rel, root)
    elif rel.endswith((".yaml", ".yml")) and rel.startswith("configs/"):
        check_yaml(rel, root)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: B036 - PostToolUse: report, never crash with exit 1
        sys.stderr.write("[post_edit_check] internal error: %s: %s\n" % (type(exc).__name__, str(exc)[:200]))
        sys.exit(0)
