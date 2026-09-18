"""Subprocess tests for .claude/hooks/protect_files.py (PF-xx rules)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from .conftest import TmpProject, edit_payload, run_hook, write_payload

pytestmark = pytest.mark.hooks


def assert_decision(res, decision, rule):
    assert res.returncode == 0, res.stderr
    assert res.decision == decision, res.stdout + res.stderr
    assert rule in res.reason, res.reason
    return res


def assert_none(res):
    assert res.returncode == 0
    assert res.decision is None, res.stdout


def test_matches_absolute_path(tmp_project: TmpProject) -> None:
    path = tmp_project.root / "CLAUDE.md"
    res = tmp_project.run(
        "protect_files", edit_payload(path, "rules", "new rules", cwd=tmp_project.root)
    )
    assert_decision(res, "ask", "PF-01")
    # relative paths (older payload shape) are resolved against cwd too
    res = tmp_project.run(
        "protect_files", edit_payload("CLAUDE.md", "a", "b", cwd=tmp_project.root)
    )
    assert_decision(res, "ask", "PF-01")
    res = tmp_project.run(
        "protect_files", edit_payload(tmp_project.root / "src" / ".." / "CLAUDE.md", "a", "b")
    )
    assert_decision(res, "ask", "PF-01")


def test_resolves_symlink_to_claude_md(tmp_project: TmpProject) -> None:
    link = tmp_project.root / "docs" / "c.md"
    link.symlink_to(tmp_project.root / "CLAUDE.md")
    res = tmp_project.run("protect_files", edit_payload(link, "a", "b"))
    assert_decision(res, "ask", "PF-01")


def test_ignores_outside_project(tmp_project: TmpProject, tmp_path: Path) -> None:
    other = tmp_path / "elsewhere" / "CLAUDE.md"
    other.parent.mkdir()
    assert_none(tmp_project.run("protect_files", write_payload(other, "x")))


def test_user_level_claude_dir_asks(tmp_project: TmpProject, tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = dict(tmp_project.env, HOME=str(home))
    res = tmp_project.run(
        "protect_files", write_payload(home / ".claude" / "settings.json", "{}"), env=env
    )
    assert_decision(res, "ask", "PF-11")
    res = tmp_project.run("protect_files", write_payload(home / "notes.md", "x"), env=env)
    assert_none(res)


@pytest.mark.parametrize(
    "rel,rule",
    [
        ("docs/RESEARCH_CONTRACT.md", "PF-01"),
        ("data/manifests/replay_v1.jsonl", "PF-02"),
        ("data/manifests/adaptation/x.jsonl", "PF-02"),
        ("research/claims/claims.jsonl", "PF-04"),
        (".claude/settings.json", "PF-05"),
        (".claude/settings.local.json", "PF-05"),
        (".claude/hooks/guard_destructive.py", "PF-05"),
        (".claude/rules/x.md", "PF-05"),
        (".claude/agents/x.md", "PF-05"),
        (".claude/skills/x/SKILL.md", "PF-05"),
        (".claude/commands/x.md", "PF-05"),
        ("uv.lock", "PF-06"),
        ("experiments/specs/exp_a.yaml", "PF-09"),
    ],
)
def test_protected_globs_ask(tmp_project: TmpProject, rel: str, rule: str) -> None:
    res = tmp_project.run("protect_files", write_payload(tmp_project.root / rel, "x\n"))
    assert_decision(res, "ask", rule)


@pytest.mark.parametrize(
    "rel,rule",
    [
        ("experiments/registry.jsonl", "PF-08"),
        ("experiments/approvals/exp_a.abcdef123456.json", "PF-08"),
        ("experiments/specs/exp_a.resolved.yaml", "PF-09"),
    ],
)
def test_deny_files(tmp_project: TmpProject, rel: str, rule: str) -> None:
    res = tmp_project.run("protect_files", write_payload(tmp_project.root / rel, "x\n"))
    assert_decision(res, "deny", rule)
    assert rule in res.stderr
    res = tmp_project.run("protect_files", edit_payload(tmp_project.root / rel, "a", "b"))
    assert_decision(res, "deny", rule)


def test_agent_memory_is_not_protected(tmp_project: TmpProject) -> None:
    res = tmp_project.run(
        "protect_files",
        write_payload(tmp_project.root / ".claude" / "agent-memory" / "eng" / "m.md", "x"),
    )
    assert_none(res)


def test_new_adr_passes_existing_adr_asks(tmp_project: TmpProject) -> None:
    new = tmp_project.root / "research" / "decisions" / "ADR-006-new.md"
    assert_none(tmp_project.run("protect_files", write_payload(new, "# ADR-006\n")))
    existing = tmp_project.root / "research" / "decisions" / "ADR-001-existing.md"
    assert_decision(
        tmp_project.run("protect_files", edit_payload(existing, "Accepted", "Rejected")),
        "ask",
        "PF-07",
    )
    assert_decision(
        tmp_project.run("protect_files", write_payload(existing, "# rewritten\n")), "ask", "PF-07"
    )
    readme = tmp_project.root / "research" / "decisions" / "README.md"
    assert_none(tmp_project.run("protect_files", write_payload(readme, "index\n")))


def test_protocol_change_summary_contains_key(tmp_project: TmpProject) -> None:
    path = tmp_project.root / "configs" / "protocol" / "proto.yaml"
    res = tmp_project.run(
        "protect_files", edit_payload(path, "total_samples: 24", "total_samples: 48")
    )
    assert_decision(res, "ask", "PF-03")
    assert "protocol_hash" in res.reason
    assert "splits" in res.reason  # top-level key of the changed line
    assert "status" not in res.reason.split("changed top-level keys:")[1]
    res = tmp_project.run(
        "protect_files", write_payload(path, "protocol_id: proto\nstatus: draft\n")
    )
    assert_decision(res, "ask", "PF-03")
    assert "status" in res.reason


def test_exp_execution_key_change_asks(tmp_project: TmpProject) -> None:
    path = tmp_project.root / "configs" / "exp" / "exp_a.yaml"
    res = tmp_project.run("protect_files", edit_payload(path, "  mode: smoke", "  mode: full"))
    assert_decision(res, "ask", "PF-10")
    assert "execution.mode" in res.reason
    res = tmp_project.run(
        "protect_files",
        edit_payload(path, "  allow_full_gpu_run: false", "  allow_full_gpu_run: true"),
    )
    assert_decision(res, "ask", "PF-10")
    content = path.read_text(encoding="utf-8").replace(
        "require_gpu: false", "require_gpu: false\n  allow_dirty_tree: true"
    )
    assert_decision(tmp_project.run("protect_files", write_payload(path, content)), "ask", "PF-10")
    # MultiEdit payload shape
    payload = edit_payload(path, tool_name="MultiEdit")
    payload["tool_input"] = {
        "file_path": str(path),
        "edits": [{"old_string": "  mode: smoke", "new_string": "  mode: full"}],
    }
    assert_decision(tmp_project.run("protect_files", payload), "ask", "PF-10")
    # new exp file that ships a full-run policy
    new = tmp_project.root / "configs" / "exp" / "exp_b.yaml"
    assert_decision(
        tmp_project.run(
            "protect_files", write_payload(new, "experiment_id: b\nexecution:\n  mode: full\n")
        ),
        "ask",
        "PF-10",
    )
    cfg = tmp_project.root / "configs" / "config.yaml"
    assert_decision(
        tmp_project.run("protect_files", edit_payload(cfg, "  mode: smoke", "  mode: full")),
        "ask",
        "PF-10",
    )


def test_exp_training_key_change_passes(tmp_project: TmpProject) -> None:
    path = tmp_project.root / "configs" / "exp" / "exp_a.yaml"
    assert_none(tmp_project.run("protect_files", edit_payload(path, "  epochs: 1", "  epochs: 3")))
    assert_none(tmp_project.run("protect_files", edit_payload(path, "  lr: 0.001", "  lr: 0.01")))
    content = path.read_text(encoding="utf-8").replace("epochs: 1", "epochs: 2")
    assert_none(tmp_project.run("protect_files", write_payload(path, content)))
    new = tmp_project.root / "configs" / "exp" / "exp_c.yaml"
    assert_none(
        tmp_project.run(
            "protect_files", write_payload(new, "experiment_id: c\ntraining:\n  epochs: 1\n")
        )
    )
    assert_none(
        tmp_project.run(
            "protect_files",
            edit_payload(
                tmp_project.root / "configs" / "config.yaml", "  epochs: 1", "  epochs: 2"
            ),
        )
    )


def test_unprotected_files_pass(tmp_project: TmpProject) -> None:
    for rel in (
        "src/pad_research/paths.py",
        "tests/unit/test_x.py",
        "README.md",
        "configs/data/x.yaml",
        "research/hypotheses/h1.md",
    ):
        assert_none(tmp_project.run("protect_files", write_payload(tmp_project.root / rel, "x")))


def test_other_tools_ignored_and_bad_input_asks(tmp_project: TmpProject) -> None:
    assert_none(
        tmp_project.run("protect_files", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    )
    res = tmp_project.run("protect_files", None, raw_stdin="nope")
    assert_decision(res, "ask", "HK-00")
    res = tmp_project.run("protect_files", {"tool_name": "Edit", "tool_input": 5})
    assert_decision(res, "ask", "HK-00")
    res = tmp_project.run("protect_files", {"tool_name": "Write", "tool_input": {"content": "x"}})
    assert_decision(res, "ask", "HK-00")


def test_notebook_edit_uses_notebook_path(tmp_project: TmpProject) -> None:
    payload = {
        "tool_name": "NotebookEdit",
        "cwd": str(tmp_project.root),
        "tool_input": {
            "notebook_path": str(tmp_project.root / "research" / "claims" / "x.ipynb"),
            "new_source": "1",
        },
    }
    assert_decision(tmp_project.run("protect_files", payload), "ask", "PF-04")


def test_fixture_payloads(tmp_project: TmpProject, load_fixture) -> None:
    res = run_hook(
        "protect_files",
        load_fixture("edit_claude_md.json", tmp_project.root),
        env=tmp_project.env,
        cwd=tmp_project.root,
    )
    assert_decision(res, "ask", "PF-01")
    res = run_hook(
        "protect_files",
        load_fixture("write_registry.json", tmp_project.root),
        env=tmp_project.env,
        cwd=tmp_project.root,
    )
    assert_decision(res, "deny", "PF-08")
    assert os.path.isabs(
        load_fixture("edit_claude_md.json", tmp_project.root)["tool_input"]["file_path"]
    )
