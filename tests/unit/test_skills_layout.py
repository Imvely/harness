"""Layout checks for the Claude Code skills and routine commands under .claude/.

Stdlib + PyYAML only; no project imports so this test runs without torch/mlflow.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"

VENDORED_SKILLS = {
    "verifying-before-completion",
    "debugging-systematically",
    "designing-experiments",
    "recording-adrs",
    "handoff",
    "fetching-paper-source",
}
COMMAND_SKILLS = {
    "start-day",
    "end-day",
    "new-exp",
    "smoke",
    "review-run",
    "paper",
    "adr",
}
BACKGROUND_SKILLS = {"using-hydra-mlflow-dvc"}
EXPECTED_SKILLS = VENDORED_SKILLS | COMMAND_SKILLS | BACKGROUND_SKILLS
COMMAND_ALIASES = {"출근.md": "/start-day", "퇴근.md": "/end-day", "인수인계.md": "/handoff"}
MAX_SKILL_LINES = 400
FORBIDDEN_SUBSTRING = "superpowers:"


def _skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


def _frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill_md}: missing YAML frontmatter opener"
    end = text.find("\n---", 4)
    assert end != -1, f"{skill_md}: frontmatter never closed"
    data = yaml.safe_load(text[4:end])
    assert isinstance(data, dict), f"{skill_md}: frontmatter is not a mapping"
    return data


def _skill_ids() -> list[str]:
    return [p.name for p in _skill_dirs()] if SKILLS_DIR.is_dir() else []


def test_expected_skill_directories_exist() -> None:
    present = set(_skill_ids())
    missing = EXPECTED_SKILLS - present
    assert not missing, f"missing skill directories: {sorted(missing)}"


@pytest.mark.parametrize("skill", _skill_ids())
def test_skill_has_frontmatter_name_and_description(skill: str) -> None:
    skill_md = SKILLS_DIR / skill / "SKILL.md"
    assert skill_md.is_file(), f"{skill}: SKILL.md missing"
    fm = _frontmatter(skill_md)
    assert isinstance(fm.get("name"), str) and fm["name"].strip(), f"{skill}: name missing"
    desc = fm.get("description")
    assert isinstance(desc, str) and desc.strip(), f"{skill}: description missing"
    budget = len(desc) + len(str(fm.get("when_to_use", "")))
    assert budget < 1536, f"{skill}: description+when_to_use is {budget} chars (limit 1536)"


@pytest.mark.parametrize("skill", sorted(COMMAND_SKILLS))
def test_command_skill_is_slash_only(skill: str) -> None:
    fm = _frontmatter(SKILLS_DIR / skill / "SKILL.md")
    assert fm.get("disable-model-invocation") is True, (
        f"{skill}: command skills must set disable-model-invocation: true"
    )


@pytest.mark.parametrize("skill", sorted(BACKGROUND_SKILLS))
def test_background_skill_is_not_user_invocable(skill: str) -> None:
    fm = _frontmatter(SKILLS_DIR / skill / "SKILL.md")
    assert fm.get("user-invocable") is False
    assert isinstance(fm.get("paths"), list) and fm["paths"], f"{skill}: paths gating missing"


@pytest.mark.parametrize("skill", sorted(VENDORED_SKILLS))
def test_vendored_skill_has_attribution_license_and_origin(skill: str) -> None:
    folder = SKILLS_DIR / skill
    attribution = folder / "ATTRIBUTION.md"
    license_file = folder / "LICENSE"
    assert attribution.is_file(), f"{skill}: ATTRIBUTION.md missing"
    assert license_file.is_file(), f"{skill}: LICENSE missing"
    attribution_text = attribution.read_text(encoding="utf-8")
    for token in ("Source URL", "Commit SHA", "License", "Modifications"):
        assert token in attribution_text, f"{skill}: ATTRIBUTION.md lacks '{token}'"
    fm = _frontmatter(folder / "SKILL.md")
    metadata = fm.get("metadata")
    assert isinstance(metadata, dict), f"{skill}: metadata block missing"
    origin = metadata.get("origin")
    assert isinstance(origin, str) and origin.startswith("https://"), f"{skill}: metadata.origin"
    assert origin in attribution_text, f"{skill}: metadata.origin not repeated in ATTRIBUTION.md"
    assert str(metadata.get("commit", "")) in attribution_text, f"{skill}: commit not in ATTRIBUTION"
    assert metadata.get("license") == "MIT", f"{skill}: only MIT sources are vendored"
    license_text = license_file.read_text(encoding="utf-8")
    assert "MIT License" in license_text and "Permission is hereby granted" in license_text


@pytest.mark.parametrize("skill", _skill_ids())
def test_any_attribution_folder_is_fully_attributed(skill: str) -> None:
    folder = SKILLS_DIR / skill
    if not (folder / "ATTRIBUTION.md").is_file():
        pytest.skip("not a vendored skill")
    assert (folder / "LICENSE").is_file(), f"{skill}: ATTRIBUTION.md present but LICENSE missing"
    assert "origin" in (_frontmatter(folder / "SKILL.md").get("metadata") or {}), (
        f"{skill}: vendored skill without metadata.origin"
    )


@pytest.mark.parametrize("skill", _skill_ids())
def test_skill_md_line_budget(skill: str) -> None:
    n_lines = len((SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8").splitlines())
    assert n_lines <= MAX_SKILL_LINES, f"{skill}: SKILL.md has {n_lines} lines (> {MAX_SKILL_LINES})"


def test_no_upstream_plugin_cross_references() -> None:
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in SKILLS_DIR.rglob("*")
        if p.is_file() and FORBIDDEN_SUBSTRING in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, f"files still referencing the upstream plugin namespace: {offenders}"


def test_forked_commands_declare_agent_and_no_write_tools() -> None:
    for skill, agent in (("review-run", "research-reviewer"), ("paper", "paper-researcher")):
        fm = _frontmatter(SKILLS_DIR / skill / "SKILL.md")
        assert fm.get("context") == "fork", f"{skill}: context must be fork"
        assert fm.get("agent") == agent, f"{skill}: agent must be {agent}"
        assert fm.get("background") is False, f"{skill}: background must be false"
        disallowed = fm.get("disallowed-tools")
        assert isinstance(disallowed, list) and {"Write", "Edit"} <= set(disallowed), (
            f"{skill}: Write and Edit must be disallowed"
        )


def test_argument_skills_declare_arguments() -> None:
    expected = {
        "new-exp": ["exp_name", "hypothesis_id"],
        "smoke": ["exp_name"],
        "review-run": ["experiment_id"],
        "paper": ["reference"],
        "adr": ["slug"],
    }
    for skill, args in expected.items():
        fm = _frontmatter(SKILLS_DIR / skill / "SKILL.md")
        declared = fm.get("arguments")
        assert isinstance(declared, list) and declared[: len(args)] == args, (
            f"{skill}: arguments must start with {args}, got {declared}"
        )


def test_dynamic_injections_are_fail_safe() -> None:
    for skill in ("start-day", "end-day"):
        body = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
        injections = [line for line in body.splitlines() if line.startswith("!`")]
        assert injections, f"{skill}: expected at least one !`...` injection"
        for line in injections:
            assert line.rstrip().endswith("|| true`"), f"{skill}: injection lacks '|| true': {line}"


def test_command_aliases_exist_and_point_at_skills() -> None:
    assert COMMANDS_DIR.is_dir(), ".claude/commands missing"
    for alias, target in COMMAND_ALIASES.items():
        path = COMMANDS_DIR / alias
        assert path.is_file(), f"alias {alias} missing"
        text = path.read_text(encoding="utf-8").strip()
        assert target in text, f"{alias} must delegate to {target}"
        assert len(text.splitlines()) == 1, f"{alias} must be a single line"
        assert (SKILLS_DIR / target.lstrip("/")).is_dir(), f"{alias}: target skill folder missing"
