"""Tests for .claude/hooks/_common.py (parser, path helpers, invariants over all hooks)."""

from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import sys

import pytest

from .conftest import FIXTURE_DIR, HOOK_NAMES, HOOKS_DIR, REPO_ROOT

pytestmark = pytest.mark.hooks


@pytest.fixture(scope="module")
def common():
    sys.path.insert(0, str(HOOKS_DIR))
    try:
        return importlib.import_module("_common")
    finally:
        sys.path.remove(str(HOOKS_DIR))


# --- invariants over every hook file -------------------------------------------------------


@pytest.mark.parametrize("name", HOOK_NAMES)
def test_hooks_compile_py38(name: str) -> None:
    src = (HOOKS_DIR / f"{name}.py").read_text(encoding="utf-8")
    tree = ast.parse(src, filename=name, feature_version=(3, 8))
    # runtime-evaluated PEP 604 / PEP 585 annotations would still break 3.8: forbid them
    for node in ast.walk(tree):
        is_union = isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
        if (
            is_union
            and isinstance(node.left, ast.Name)
            and node.left.id in {"str", "int", "dict", "list"}
        ):
            pytest.fail(f"{name}: `X | Y` annotation is not py3.8 compatible")


@pytest.mark.parametrize("name", HOOK_NAMES)
def test_hooks_have_no_pad_env_switches(name: str) -> None:
    src = (HOOKS_DIR / f"{name}.py").read_text(encoding="utf-8")
    assert not re.search(r"""os\.environ(\.get\(|\[)\s*['"]PAD_""", src), (
        f"{name} reads a PAD_* env switch"
    )
    assert "StrEnum" not in src
    assert "walrus" not in src.lower() or ":=" not in src


@pytest.mark.parametrize("name", HOOK_NAMES)
def test_hooks_are_stdlib_only(name: str) -> None:
    src = (HOOKS_DIR / f"{name}.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    allowed = set(sys.stdlib_module_names) | {"_common"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in allowed, f"{name} imports {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] in allowed, f"{name} imports from {node.module}"


@pytest.mark.parametrize("name", [n for n in HOOK_NAMES if n != "_common"])
def test_hooks_catch_base_exception(name: str) -> None:
    src = (HOOKS_DIR / f"{name}.py").read_text(encoding="utf-8")
    assert "except BaseException" in src, f"{name} must fail safe (exit 1 is fail-open)"
    assert "reconfigure" in (HOOKS_DIR / "_common.py").read_text(encoding="utf-8")


def test_rules_table_prints() -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "_common.py"), "--rules-table"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("| ID | Hook | Pattern | Decision |")
    for rid in ("DG-01", "DG-14", "EXP-01", "EXP-09", "PF-01", "PF-11", "HK-00", "HK-99"):
        assert rid in proc.stdout


def test_fixture_payloads_are_valid_json() -> None:
    files = sorted(FIXTURE_DIR.glob("*.json"))
    assert files, "no fixture payloads"
    for path in files:
        data = json.loads(
            path.read_text(encoding="utf-8").replace("{CLAUDE_PROJECT_DIR}", REPO_ROOT.as_posix())
        )
        assert "hook_event_name" in data


# --- parser ---------------------------------------------------------------------------------


def test_split_keeps_quoted_separators(common) -> None:
    parsed = common.split_commands(
        'uv run python -c "import torch; print(1)" && git commit -m "a; b"'
    )
    assert parsed.n_segments == 2
    assert parsed.segments[0].argv == ["uv", "run", "python", "-c", "import torch; print(1)"]
    assert parsed.segments[1].argv[-1] == "a; b"
    assert parsed.segments[1].sep == "&&"


def test_split_strips_wrappers_and_records_env(common) -> None:
    parsed = common.split_commands(
        "FOO=1 sudo -u root env BAR=2 timeout -s KILL 5 nice -n 10 rm -rf x"
    )
    seg = parsed.segments[0]
    assert seg.argv == ["rm", "-rf", "x"]
    assert seg.env_names == ["FOO", "BAR"]
    assert not parsed.is_simple  # env assignment present


def test_split_recurses_one_level_into_bash_c_and_eval(common) -> None:
    parsed = common.split_commands("bash -c 'cd data && rm -rf raw'")
    assert [s.argv0 for s in parsed.segments] == ["cd", "rm"]
    assert parsed.segments[1].after_cd is True
    parsed = common.split_commands('eval "rm -rf data"')
    assert parsed.segments[0].argv == ["rm", "-rf", "data"]
    nested = common.split_commands("bash -c \"bash -c 'rm -rf data'\"")
    assert nested.depth_exceeded and nested.has_indirect


def test_split_flags_redirect_background_subshell(common) -> None:
    p = common.split_commands("echo x >> experiments/registry.jsonl")
    assert p.has_redirect and p.segments[0].redirects == ["experiments/registry.jsonl"]
    assert common.split_commands("sleep 1 &").has_background
    assert common.split_commands("echo $(ls)").has_subshell
    assert common.split_commands("echo `ls`").has_subshell
    assert common.split_commands("cat <<EOF\nx\nEOF").has_subshell
    assert common.split_commands("ls").is_simple
    assert not common.split_commands("ls 2>/dev/null").is_simple


def test_split_fd_before_redirect_is_not_an_argument(common) -> None:
    p = common.split_commands("rm -rf outputs/x 2>/dev/null")
    assert p.segments[0].argv == ["rm", "-rf", "outputs/x"]
    assert p.segments[0].redirects == ["/dev/null"]
    p = common.split_commands("cmd 2>&1")
    assert p.segments[0].argv == ["cmd"] and p.segments[0].redirects == []


def test_split_xargs_marks_indirect(common) -> None:
    p = common.split_commands("cat list | xargs -n 1 rm -rf")
    assert p.segments[1].argv0 == "rm" and p.segments[1].indirect


def test_split_unbalanced_quote_sets_lex_failed(common) -> None:
    p = common.split_commands('echo "unterminated')
    assert p.lex_failed


def test_split_newline_separates_segments(common) -> None:
    p = common.split_commands("ls\nrm -rf data")
    assert [s.argv0 for s in p.segments] == ["ls", "rm"]


# --- path helpers ---------------------------------------------------------------------------


def test_rel_project_path_and_outside(common, monkeypatch, tmp_path) -> None:
    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    assert common.rel_project_path("sub/x.txt", str(root)) == "sub/x.txt"
    assert common.rel_project_path(str(root)) == ""
    assert common.rel_project_path("/tmp/elsewhere", str(root)) is None
    assert common.rel_project_path("../other", str(root)) is None
    assert common.is_root_or_parent("/", str(root))
    assert common.is_root_or_parent("..", str(root))
    assert not common.is_root_or_parent("sub", str(root))


def test_rel_project_path_resolves_symlink(common, monkeypatch, tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "CLAUDE.md").write_text("x", encoding="utf-8")
    (root / "docs").mkdir()
    try:
        (root / "docs" / "c.md").symlink_to(root / "CLAUDE.md")
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable in this test environment: {exc}")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    assert common.rel_project_path(str(root / "docs" / "c.md")) == "CLAUDE.md"


def test_classify_target_unresolvable_and_wildcards(common, monkeypatch, tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    assert common.classify_target("$PAD_DATA_ROOT", str(root)).kind == common.UNRESOLVABLE
    assert common.classify_target("~/x", str(root)).kind == common.UNRESOLVABLE
    assert common.classify_target("`pwd`/x", str(root)).kind == common.UNRESOLVABLE
    t = common.classify_target("data/*", str(root))
    assert t.kind == common.INSIDE and t.rel == "data" and t.wildcard
    assert common.classify_target("./*", str(root)).rel == ""
    seg = common.Segment()
    seg.after_cd = True
    assert common.classify_target("raw", str(root), seg).kind == common.UNRESOLVABLE
    assert common.classify_target(str(root / "raw"), str(root), seg).kind == common.INSIDE


def test_glob_helpers(common) -> None:
    assert common.matches_glob("data/manifests/a/b.jsonl", "data/manifests/**")
    assert common.matches_glob("data/manifests", "data/manifests/**")
    assert not common.matches_glob("data/manifestsx", "data/manifests/**")
    assert common.is_protected_file(".claude/hooks/x.py") == ".claude/hooks/**"
    assert common.is_protected_file(".claude/agent-memory/x.md") is None
    assert common.is_deny_file("experiments/approvals/a.json")
    assert common.is_ephemeral("src/pad_research/__pycache__")
    assert common.is_ephemeral("outputs/2026/run")
    assert common.is_ephemeral("build/lib.egg-info")
    assert not common.is_ephemeral("data/raw")
    assert common.is_mlruns("mlruns_artifacts/1")
    assert common.covers_tree("data", common.DENY_TREES) == "data/raw"
    assert common.under_tree("data", common.DENY_TREES) is None


def test_remote_detection(common) -> None:
    assert common.is_remote("host:/y")
    assert common.is_remote("user@h.example.com:")
    assert common.is_remote("s3://bucket/x")
    assert not common.is_remote("data/raw")
    assert common.is_public_hub("https://huggingface.co/x")
    assert not common.is_public_hub("host:")


# --- settings.json wiring (written by another task; validated here when present) --------------

SETTINGS = REPO_ROOT / ".claude" / "settings.json"
ALLOWED_MATCHERS = {
    "PreToolUse": {"Bash", "Edit|MultiEdit|Write|NotebookEdit"},
    "PostToolUse": {"Edit|MultiEdit|Write|NotebookEdit"},
    "SessionStart": {"startup|resume|compact"},
}
MIN_TIMEOUT = {
    "guard_destructive": 10,
    "gate_experiment": 60,
    "protect_files": 10,
    "post_edit_check": 120,
    "session_start": 20,
}


def _settings_hooks() -> dict:
    if not SETTINGS.exists():
        pytest.skip(".claude/settings.json not written yet")
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    if "hooks" not in data:
        pytest.skip(".claude/settings.json has no hooks block yet (T9 wiring pending)")
    return data["hooks"]


def test_settings_json_parses_and_matchers_valid() -> None:
    hooks = _settings_hooks()
    assert set(hooks) >= {"PreToolUse", "PostToolUse", "SessionStart"}
    seen = set()
    for event, groups in hooks.items():
        for group in groups:
            assert group["matcher"] in ALLOWED_MATCHERS[event], (event, group["matcher"])
            for h in group["hooks"]:
                assert h["type"] == "command"
                m = re.search(r"\.claude/hooks/([a-z_]+)\.py", h["command"])
                assert m, h["command"]
                name = m.group(1)
                assert (HOOKS_DIR / f"{name}.py").exists(), name
                assert "${CLAUDE_PROJECT_DIR}" in h["command"]
                assert h.get("timeout", 0) >= MIN_TIMEOUT[name], (name, h.get("timeout"))
                seen.add(name)
    assert seen == set(MIN_TIMEOUT)
    # internal subprocess timeouts must leave >= 20 s margin below the hook timeout
    gate_src = (HOOKS_DIR / "gate_experiment.py").read_text(encoding="utf-8")
    assert int(re.search(r"^VALIDATOR_TIMEOUT_S = (\d+)", gate_src, re.M).group(1)) <= 60 - 15
    pec_src = (HOOKS_DIR / "post_edit_check.py").read_text(encoding="utf-8")
    assert int(re.search(r"^PYTEST_TIMEOUT_S = (\d+)", pec_src, re.M).group(1)) <= 120 - 20
