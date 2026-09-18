"""Tests for .claude/hooks/post_edit_check.py (PostToolUse ruff + targeted pytest / yaml)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from .conftest import HOOKS_DIR, TmpProject

pytestmark = pytest.mark.hooks


@pytest.fixture(scope="module")
def pec():
    sys.path.insert(0, str(HOOKS_DIR))
    try:
        return importlib.import_module("post_edit_check")
    finally:
        sys.path.remove(str(HOOKS_DIR))


def post_payload(project: TmpProject, rel: str) -> dict:
    return {
        "session_id": "t",
        "cwd": str(project.root),
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": str(project.root / rel), "old_string": "a", "new_string": "b"},
        "tool_response": {"success": True},
    }


# --- mapping (in-process) -------------------------------------------------------------------


def _fake_tree(root: Path, files: list[str]) -> None:
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")


def test_mapping_module_to_unit_tests(pec, tmp_path: Path) -> None:
    root = tmp_path / "p"
    _fake_tree(
        root,
        [
            "tests/unit/test_metrics.py",
            "tests/unit/test_tracking_mlflow_tracker.py",
            "tests/protocol/test_protocol_hash.py",
            "tests/protocol/test_protocol_schema.py",
            "tests/integration/test_train_smoke.py",
            "tests/integration/test_validate_cli.py",
            "tests/hooks/test_common.py",
            "tests/hooks/test_guard_destructive.py",
        ],
    )
    assert pec.map_tests("src/pad_research/metrics/metrics.py", str(root))[0] == [
        "tests/unit/test_metrics.py"
    ]
    assert pec.map_tests("src/pad_research/tracking/mlflow_tracker.py", str(root))[0] == [
        "tests/unit/test_tracking_mlflow_tracker.py"
    ]
    files, _ = pec.map_tests("src/pad_research/protocols/schema.py", str(root))
    assert files == [
        "tests/protocol/test_protocol_hash.py",
        "tests/protocol/test_protocol_schema.py",
    ]
    assert pec.map_tests("src/pad_research/paths.py", str(root))[0] == []
    assert pec.map_tests(".claude/hooks/_common.py", str(root))[0] == ["tests/hooks/test_common.py"]
    assert pec.map_tests(".claude/hooks/guard_destructive.py", str(root))[0] == [
        "tests/hooks/test_guard_destructive.py"
    ]
    assert pec.map_tests("tests/hooks/test_common.py", str(root))[0] == [
        "tests/hooks/test_common.py"
    ]
    files, note = pec.map_tests("tests/hooks/conftest.py", str(root))
    assert files == [] and "conftest" in note


def test_post_edit_never_selects_integration_tests(pec, tmp_path: Path) -> None:
    root = tmp_path / "p"
    _fake_tree(
        root,
        [
            "tests/integration/test_train_smoke.py",
            "tests/integration/test_train_full_cpu.py",
            "tests/integration/test_validate_cli.py",
            "tests/integration/test_summarize.py",
        ],
    )
    for rel in (
        "scripts/train.py",
        "scripts/adapt.py",
        "scripts/evaluate.py",
        "scripts/summarize_experiment.py",
        "scripts/build_manifest.py",
        "src/pad_research/training/trainer.py",
        "src/pad_research/experiments/registry.py",
        ".claude/hooks/gate_experiment.py",
    ):
        files, note = pec.map_tests(rel, str(root))
        assert not any(f.startswith("tests/integration/") for f in files), (rel, files)
        assert files == [] and note, (rel, files, note)
    for rel in ("scripts/validate_spec.py", "scripts/validate_protocol.py"):
        assert pec.map_tests(rel, str(root))[0] == ["tests/integration/test_validate_cli.py"]


def test_pytest_command_excludes_slow_and_integration(pec) -> None:
    src = (HOOKS_DIR / "post_edit_check.py").read_text(encoding="utf-8")
    assert '"not slow and not integration"' in src
    assert '"--no-sync"' in src
    assert '"no:cacheprovider"' in src
    assert pec.PYTEST_TIMEOUT_S <= 120 - 20  # hook timeout 120 s minus margin


# --- subprocess behaviour ---------------------------------------------------------------------


def test_exit2_on_failing_mapped_test(tmp_project: TmpProject) -> None:
    tmp_project.write("src/pad_research/foo.py", "VALUE = 1\n")
    tmp_project.write("tests/unit/test_foo.py", "def test_foo():\n    assert 1 + 1 == 3\n")
    res = tmp_project.run(
        "post_edit_check", post_payload(tmp_project, "src/pad_research/foo.py"), timeout=150
    )
    assert res.returncode == 2, res.stdout + res.stderr
    assert "test_foo" in res.stderr
    assert "targeted tests failed" in res.stderr
    assert len(res.stderr.splitlines()) <= 20  # concise


def test_exit0_when_mapped_test_passes(tmp_project: TmpProject) -> None:
    tmp_project.write("src/pad_research/bar.py", "VALUE = 1\n")
    tmp_project.write("tests/unit/test_bar.py", "def test_bar():\n    assert 1 + 1 == 2\n")
    res = tmp_project.run(
        "post_edit_check", post_payload(tmp_project, "src/pad_research/bar.py"), timeout=150
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "tests ok" in res.stdout


def test_exit2_on_ruff_error(tmp_project: TmpProject) -> None:
    tmp_project.write("src/pad_research/baz.py", "import os\nx = undefined_name\n")
    res = tmp_project.run(
        "post_edit_check", post_payload(tmp_project, "src/pad_research/baz.py"), timeout=150
    )
    assert res.returncode == 2
    assert "ruff" in res.stderr


def test_exit0_with_note_when_no_mapping(tmp_project: TmpProject) -> None:
    tmp_project.write("scripts/train.py", "print('x')\n")
    res = tmp_project.run(
        "post_edit_check", post_payload(tmp_project, "scripts/train.py"), timeout=150
    )
    assert res.returncode == 0, res.stderr
    assert "make test" in res.stdout


def test_ignores_other_files(tmp_project: TmpProject) -> None:
    tmp_project.write("README.md", "x\n")
    res = tmp_project.run("post_edit_check", post_payload(tmp_project, "README.md"))
    assert res.returncode == 0 and not res.stdout.strip()
    res = tmp_project.run("post_edit_check", post_payload(tmp_project, "does/not/exist.py"))
    assert res.returncode == 0
    res = tmp_project.run("post_edit_check", None, raw_stdin="{bad")
    assert res.returncode == 0


def test_yaml_route(tmp_project: TmpProject) -> None:
    tmp_project.write("configs/data/bad.yaml", "a: [1, 2\n")
    res = tmp_project.run(
        "post_edit_check", post_payload(tmp_project, "configs/data/bad.yaml"), timeout=150
    )
    assert res.returncode == 2
    assert "yaml validation failed" in res.stderr
    tmp_project.write("configs/data/good.yaml", "a: [1, 2]\n")
    res = tmp_project.run(
        "post_edit_check", post_payload(tmp_project, "configs/data/good.yaml"), timeout=150
    )
    assert res.returncode == 0 and "yaml ok" in res.stdout
    # protocol route -> validate_protocol.py --path <f> --schema-only --json
    tmp_project.write(
        "scripts/validate_protocol.py",
        "import json, sys\nopen('proto_argv.json', 'w').write(json.dumps(sys.argv[1:]))\nprint('{}')\n",
    )
    res = tmp_project.run(
        "post_edit_check", post_payload(tmp_project, "configs/protocol/proto.yaml"), timeout=150
    )
    assert res.returncode == 0, res.stderr
    argv = __import__("json").loads((tmp_project.root / "proto_argv.json").read_text())
    assert argv == ["--path", "configs/protocol/proto.yaml", "--schema-only", "--json"]
    # exp route -> validate_spec.py --exp <name> --json (stub records argv)
    res = tmp_project.run(
        "post_edit_check", post_payload(tmp_project, "configs/exp/exp_a.yaml"), timeout=150
    )
    assert res.returncode == 0, res.stderr
    assert tmp_project.stub_argv() == ["--exp", "exp_a", "--json"]
