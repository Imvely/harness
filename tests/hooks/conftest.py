"""Fixtures for the subprocess hook tests (.claude/hooks/*.py).

Every hook is executed the way Claude Code executes it: `python3 <hook> < payload.json`.
`tmp_project` builds a throw-away project (pyproject.toml + a controllable
scripts/validate_spec.py stub) and points CLAUDE_PROJECT_DIR at it, so no test ever
touches the real registry, MLflow store or validator.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "hook_inputs"
HOOK_NAMES = (
    "_common",
    "guard_destructive",
    "gate_experiment",
    "protect_files",
    "post_edit_check",
    "session_start",
)

STUB_VALIDATOR = textwrap.dedent(
    '''\
    """validate_spec.py stub: behaviour is controlled by <project>/stub_behavior.json."""
    import json
    import os
    import sys
    import time

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(ROOT, "stub_behavior.json"), encoding="utf-8") as fh:
        behavior = json.load(fh)
    with open(os.path.join(ROOT, "stub_argv.json"), "w", encoding="utf-8") as fh:
        json.dump(sys.argv[1:], fh)
    if behavior.get("sleep"):
        time.sleep(float(behavior["sleep"]))
    if behavior.get("json") is not None:
        sys.stdout.write(json.dumps(behavior["json"]) + "\\n")
    elif behavior.get("stdout") is not None:
        sys.stdout.write(str(behavior["stdout"]))
    if behavior.get("stderr"):
        sys.stderr.write(str(behavior["stderr"]))
    sys.exit(int(behavior.get("exit", 0)))
    '''
)

TMP_PYPROJECT = textwrap.dedent(
    """\
    [project]
    name = "hook-tmp-project"
    version = "0.0.0"
    requires-python = ">=3.11"

    [tool.ruff]
    line-length = 100
    extend-exclude = [".claude/hooks"]

    [tool.ruff.lint]
    select = ["E", "F"]

    [tool.pytest.ini_options]
    addopts = "-p no:cacheprovider"
    markers = ["slow: slow", "integration: integration"]
    """
)


def ok_result(mode: str = "smoke", **extra: Any) -> dict[str, Any]:
    """A validate_spec --json object as documented in INTERFACES.md (hook contract)."""
    base = {
        "ok": True,
        "exit_code": 0,
        "errors": [],
        "warnings": [],
        "experiment_id": "exp_syn_e01_frame_source_only",
        "mode": mode,
        "science_hash": "a" * 64,
        "spec_hash": "b" * 64,
        "protocol_id": "syn_a_to_b_v1",
        "protocol_hash": "c" * 64,
        "tracking_uri_scheme": "sqlite",
        "approval_token_ok": False,
        "gate": {
            "allowed": mode == "smoke",
            "reasons": [] if mode == "smoke" else ["APPROVAL_TOKEN_OK: missing"],
            "checks": {"SPEC_FROZEN": True, "SMOKE_OK": True, "APPROVAL_TOKEN_OK": mode == "smoke"},
        },
    }
    base.update(extra)
    return base


@dataclass
class HookResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> dict[str, Any] | None:
        text = self.stdout.strip()
        if not text:
            return None
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None

    @property
    def decision(self) -> str | None:
        out = self.output
        if not out:
            return None
        return out.get("hookSpecificOutput", {}).get("permissionDecision")

    @property
    def reason(self) -> str:
        out = self.output
        if not out:
            return ""
        return out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


def run_hook(
    name: str,
    payload: Any,
    env: dict[str, str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
    timeout: float = 120,
    raw_stdin: str | None = None,
) -> HookResult:
    """Run `.claude/hooks/<name>.py` with `payload` (dict -> JSON) on stdin."""
    script = HOOKS_DIR / (name if name.endswith(".py") else name + ".py")
    full_env = dict(os.environ)
    full_env.setdefault("CLAUDE_PROJECT_DIR", str(REPO_ROOT))
    if env:
        full_env.update(env)
    stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
        env=full_env,
        timeout=timeout,
        check=False,
    )
    return HookResult(proc.returncode, proc.stdout, proc.stderr)


def bash_payload(command: str, cwd: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    return {
        "session_id": "test-session",
        "cwd": str(cwd or REPO_ROOT),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": "toolu_test",
    }


def edit_payload(
    file_path: str | os.PathLike[str],
    old_string: str = "",
    new_string: str = "",
    cwd: str | os.PathLike[str] | None = None,
    tool_name: str = "Edit",
) -> dict[str, Any]:
    return {
        "session_id": "test-session",
        "cwd": str(cwd or REPO_ROOT),
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {
            "file_path": str(file_path),
            "old_string": old_string,
            "new_string": new_string,
        },
        "tool_use_id": "toolu_test",
    }


def write_payload(
    file_path: str | os.PathLike[str], content: str, cwd: str | os.PathLike[str] | None = None
) -> dict[str, Any]:
    return {
        "session_id": "test-session",
        "cwd": str(cwd or REPO_ROOT),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(file_path), "content": content},
        "tool_use_id": "toolu_test",
    }


@dataclass
class TmpProject:
    root: Path
    env: dict[str, str]

    def set_stub(self, behavior: dict[str, Any]) -> None:
        (self.root / "stub_behavior.json").write_text(json.dumps(behavior), encoding="utf-8")

    def stub_argv(self) -> list[str]:
        path = self.root / "stub_argv.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run(self, name: str, payload: Any, **kwargs: Any) -> HookResult:
        kwargs.setdefault("env", self.env)
        kwargs.setdefault("cwd", self.root)
        return run_hook(name, payload, **kwargs)

    def bash(self, command: str) -> HookResult:
        return self.run("guard_destructive", bash_payload(command, cwd=self.root))

    def gate(self, command: str) -> HookResult:
        return self.run("gate_experiment", bash_payload(command, cwd=self.root))


@pytest.fixture
def tmp_project(tmp_path: Path) -> TmpProject:
    root = tmp_path / "proj"
    for d in (
        "scripts",
        "src/pad_research",
        "tests/unit",
        "tests/integration",
        "tests/protocol",
        "tests/hooks",
        "tests/fixtures/configs",
        "configs/exp",
        "configs/protocol",
        "configs/data",
        "data/raw",
        "data/processed",
        "data/manifests",
        "checkpoints",
        "experiments/specs",
        "experiments/approvals",
        "experiments/reports",
        "research/claims",
        "research/decisions",
        "docs",
        ".claude/hooks",
        "outputs/run1",
    ):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(TMP_PYPROJECT, encoding="utf-8")
    (root / "scripts" / "validate_spec.py").write_text(STUB_VALIDATOR, encoding="utf-8")
    (root / "CLAUDE.md").write_text("# CLAUDE\n\nrules\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "docs" / "RESEARCH_CONTRACT.md").write_text("# contract\n", encoding="utf-8")
    (root / "research" / "decisions" / "ADR-001-existing.md").write_text(
        "# ADR-001 existing\n\n## Status\n\nAccepted\n", encoding="utf-8"
    )
    (root / "configs" / "protocol" / "proto.yaml").write_text(
        "protocol_id: proto\nstatus: active\nsplits:\n  train:\n    total_samples: 24\n  test:\n    total_samples: 8\n",
        encoding="utf-8",
    )
    (root / "configs" / "exp" / "exp_a.yaml").write_text(
        "# @package _global_\nexperiment_id: exp_a\ntraining:\n  epochs: 1\n  lr: 0.001\nexecution:\n  mode: smoke\n  allow_full_gpu_run: false\n  require_gpu: false\n",
        encoding="utf-8",
    )
    (root / "configs" / "config.yaml").write_text(
        "defaults:\n  - _self_\nexecution:\n  mode: smoke\ntraining:\n  epochs: 1\n",
        encoding="utf-8",
    )
    (root / "experiments" / "registry.jsonl").write_text("", encoding="utf-8")
    (root / "data" / "raw" / "x.mp4").write_bytes(b"\x00")
    env = {
        "CLAUDE_PROJECT_DIR": str(root),
        # test-only: lets `uv run --no-sync` inside the tmp project reuse the real venv
        "UV_PROJECT_ENVIRONMENT": str(REPO_ROOT / ".venv"),
    }
    project = TmpProject(root=root, env=env)
    project.set_stub({"exit": 0, "json": ok_result("smoke")})
    return project


@pytest.fixture
def hook():
    return run_hook


@pytest.fixture
def load_fixture():
    def _load(name: str, project_dir: str | os.PathLike[str] = REPO_ROOT) -> dict[str, Any]:
        text = (FIXTURE_DIR / name).read_text(encoding="utf-8")
        project_path = Path(project_dir).as_posix()
        return json.loads(text.replace("{CLAUDE_PROJECT_DIR}", project_path))

    return _load
