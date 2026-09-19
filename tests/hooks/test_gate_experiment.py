"""Subprocess tests for .claude/hooks/gate_experiment.py (EXP-xx rules).

The validator is a stub (tests/hooks/conftest.py::STUB_VALIDATOR) controlled through
<tmp_project>/stub_behavior.json; the hook itself is never configured through env.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from .conftest import HOOKS_DIR, TmpProject, bash_payload, ok_result, run_hook

pytestmark = pytest.mark.hooks

TRAIN = "uv run python scripts/train.py +exp=exp_a"


def assert_decision(res, decision, rule):
    assert res.returncode == 0, res.stderr
    assert res.decision == decision, res.stdout + res.stderr
    assert rule in res.reason, res.reason
    return res


def test_ignores_non_train_commands(tmp_project: TmpProject) -> None:
    for cmd in (
        "ls",
        "uv run pytest -q",
        "uv run python scripts/evaluate.py --run x",
        "echo train.py",
        "cat scripts/train.py",
        "uv run ruff check scripts/train.py",
        "git diff scripts/adapt.py",
    ):
        res = tmp_project.gate(cmd)
        assert res.returncode == 0 and res.decision is None, cmd
    assert not tmp_project.stub_argv()  # validator never called


def test_denies_execution_mode_full(tmp_project: TmpProject) -> None:
    assert_decision(tmp_project.gate(TRAIN + " execution.mode=full"), "deny", "EXP-01")
    assert_decision(tmp_project.gate(TRAIN + " ++execution.mode=full"), "deny", "EXP-01")
    assert_decision(
        tmp_project.gate(TRAIN + " +execution.allow_full_gpu_run=true"), "deny", "EXP-01"
    )
    assert_decision(tmp_project.gate(TRAIN + " ~execution.allow_dirty_tree"), "deny", "EXP-01")
    assert_decision(tmp_project.gate(TRAIN + " execution.mode='full'"), "deny", "EXP-01")
    assert_decision(tmp_project.gate(TRAIN + " execution=full_h100"), "deny", "EXP-01")
    assert not tmp_project.stub_argv()


def test_allows_demotion_to_smoke(tmp_project: TmpProject) -> None:
    res = tmp_project.gate(TRAIN + " execution.mode=smoke")
    assert_decision(res, "allow", "EXP-05")
    assert "execution.mode=smoke" in tmp_project.stub_argv()


def test_denies_missing_exp(tmp_project: TmpProject) -> None:
    assert_decision(tmp_project.gate("uv run python scripts/train.py"), "deny", "EXP-03")
    assert_decision(
        tmp_project.gate("uv run python scripts/adapt.py training.epochs=1"), "deny", "EXP-03"
    )
    assert_decision(tmp_project.gate("uv run python scripts/train.py exp=exp_a"), "deny", "EXP-03")


def test_asks_multirun(tmp_project: TmpProject) -> None:
    assert_decision(tmp_project.gate(TRAIN + " -m training.lr=0.1,0.01"), "ask", "EXP-02")
    assert_decision(tmp_project.gate(TRAIN + " --multirun"), "ask", "EXP-02")
    assert_decision(tmp_project.gate(TRAIN + " hydra.sweeper.params.x=1"), "ask", "EXP-02")


def test_config_dir_rules(tmp_project: TmpProject) -> None:
    assert_decision(tmp_project.gate(TRAIN + " --config-dir /tmp/x"), "deny", "EXP-08")
    assert_decision(tmp_project.gate(TRAIN + " -cd /tmp/x"), "deny", "EXP-08")
    assert_decision(tmp_project.gate(TRAIN + " --config-path=/tmp/x"), "deny", "EXP-08")
    assert_decision(tmp_project.gate(TRAIN + " --config-name other"), "deny", "EXP-08")
    assert_decision(tmp_project.gate(TRAIN + " hydra.searchpath=[file:///tmp/x]"), "deny", "EXP-08")
    res = tmp_project.gate(TRAIN + " --config-dir tests/fixtures/configs")
    assert_decision(res, "allow", "EXP-05")
    argv = tmp_project.stub_argv()
    assert argv[argv.index("--config-dir") + 1] == "tests/fixtures/configs"
    config_dir = (tmp_project.root / "tests" / "fixtures" / "configs").as_posix()
    res = tmp_project.gate(f"{TRAIN} --config-dir {config_dir}")
    assert res.decision == "allow"


def test_allows_valid_smoke_single_segment(tmp_project: TmpProject) -> None:
    res = tmp_project.gate(TRAIN + " training.epochs=1")
    assert_decision(res, "allow", "EXP-05")
    assert "exp_syn_e01_frame_source_only" in res.reason
    assert "c" * 12 in res.reason
    argv = tmp_project.stub_argv()
    assert argv[:6] == [
        "--exp",
        "exp_a",
        "--for-launch",
        "--approval-optional",
        "--json",
        "--",
    ]
    assert "training.epochs=1" in argv
    assert "+exp=exp_a" not in argv


def test_detects_train_through_wrappers(tmp_project: TmpProject) -> None:
    assert_decision(
        tmp_project.gate("bash -c 'uv run python scripts/train.py +exp=x execution.mode=full'"),
        "deny",
        "EXP-01",
    )
    assert_decision(tmp_project.gate("nohup uv run python scripts/train.py"), "deny", "EXP-03")
    assert_decision(tmp_project.gate("./scripts/train.py"), "deny", "EXP-03")
    assert_decision(tmp_project.gate("cd scripts && python train.py"), "deny", "EXP-03")
    # detected through bash -c and valid -> validator ran, but compound => no allow
    res = tmp_project.gate("bash -c 'uv run python scripts/train.py +exp=exp_a'")
    assert res.returncode == 0 and res.decision == "allow"  # single simple segment after recursion


def test_no_allow_for_compound_commands(tmp_project: TmpProject) -> None:
    for cmd in (
        TRAIN + " && git push origin HEAD",
        TRAIN + " > run.log 2>&1",
        TRAIN + " &",
        "cd scripts && uv run python train.py +exp=exp_a",
        TRAIN + "; rm -r outputs",
        "OMP_NUM_THREADS=1 " + TRAIN,
    ):
        res = tmp_project.gate(cmd)
        assert res.returncode == 0
        assert res.decision is None, (cmd, res.stdout)


def test_asks_valid_full_without_token(tmp_project: TmpProject) -> None:
    tmp_project.set_stub({"exit": 0, "json": ok_result("full", approval_token_ok=False)})
    res = tmp_project.gate(TRAIN)
    assert_decision(res, "ask", "EXP-06")
    assert "approval_token_ok=False" in res.reason
    assert "APPROVAL_TOKEN_OK=FAIL" in res.reason
    assert "exp_syn_e01_frame_source_only" in res.reason


def test_allows_valid_full_with_token(tmp_project: TmpProject) -> None:
    result = ok_result("full", approval_token_ok=True)
    result["gate"] = {
        "allowed": True,
        "reasons": [],
        "checks": {"APPROVAL_TOKEN_OK": True, "SMOKE_OK": True},
    }
    tmp_project.set_stub({"exit": 0, "json": result})
    res = tmp_project.gate(TRAIN)
    assert_decision(res, "allow", "EXP-06")
    # compound command: still ask even with the token
    res = tmp_project.gate(TRAIN + " && echo done")
    assert_decision(res, "ask", "EXP-06")


def test_denies_when_validator_fails(tmp_project: TmpProject) -> None:
    bad = ok_result(
        "smoke",
        ok=False,
        exit_code=4,
        errors=[{"code": "SMOKE_OK", "message": "no smoke run"}, "second"],
    )
    bad["gate"] = {"allowed": False, "reasons": ["SMOKE_OK"], "checks": {}}
    tmp_project.set_stub({"exit": 4, "json": bad})
    res = tmp_project.gate(TRAIN)
    assert_decision(res, "deny", "EXP-04")
    assert "SMOKE_OK: no smoke run" in res.reason
    tmp_project.set_stub({"exit": 5, "stdout": "Traceback ...", "stderr": "boom"})
    assert_decision(tmp_project.gate(TRAIN), "deny", "EXP-04")
    tmp_project.set_stub({"exit": 0, "stdout": "not json"})
    assert_decision(tmp_project.gate(TRAIN), "deny", "EXP-04")


def test_denies_when_validator_missing(tmp_project: TmpProject) -> None:
    (tmp_project.root / "scripts" / "validate_spec.py").unlink()
    assert_decision(tmp_project.gate(TRAIN), "deny", "EXP-04")


def test_asks_remote_tracking_scheme(tmp_project: TmpProject) -> None:
    tmp_project.set_stub({"exit": 0, "json": ok_result("smoke", tracking_uri_scheme="http")})
    assert_decision(tmp_project.gate(TRAIN), "ask", "EXP-09")
    tmp_project.set_stub({"exit": 0, "json": ok_result("full", tracking_uri_scheme="https")})
    res = tmp_project.gate(TRAIN)
    assert_decision(res, "ask", "EXP-06")
    assert "EXP-09" in res.reason


def test_asks_make_targets(tmp_project: TmpProject) -> None:
    assert_decision(tmp_project.gate("make smoke"), "ask", "EXP-07")
    assert_decision(tmp_project.gate("make smoke-adapt RUN=abc"), "ask", "EXP-07")
    assert_decision(tmp_project.gate("make full"), "ask", "EXP-07")
    assert tmp_project.gate("make lint").decision is None
    assert tmp_project.gate("make test").decision is None


def test_asks_on_guarded_env(tmp_project: TmpProject) -> None:
    assert_decision(tmp_project.gate("MLFLOW_TRACKING_URI=http://x " + TRAIN), "ask", "HK-04")


def test_invalid_stdin_is_silent(tmp_project: TmpProject) -> None:
    res = tmp_project.run("gate_experiment", None, raw_stdin="{oops")
    assert res.returncode == 0 and res.decision is None
    res = tmp_project.run("gate_experiment", {"tool_name": "Bash", "tool_input": 5})
    assert res.returncode == 0 and res.decision is None


def test_fixture_payload_cli_mode_full(tmp_project: TmpProject, load_fixture) -> None:
    res = tmp_project.run(
        "gate_experiment", load_fixture("bash_train_cli_mode_full.json", tmp_project.root)
    )
    assert_decision(res, "deny", "EXP-01")


@pytest.mark.slow
def test_denies_on_validator_timeout(tmp_project: TmpProject) -> None:
    """VALIDATOR_TIMEOUT_S is a module constant: override it in-process (never via env)."""
    tmp_project.set_stub({"sleep": 10, "exit": 0, "json": ok_result("smoke")})
    code = (
        f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r}); "
        "import gate_experiment as g; g.VALIDATOR_TIMEOUT_S = 2; g.main()"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(bash_payload(TRAIN, cwd=tmp_project.root)),
        capture_output=True,
        text=True,
        cwd=str(tmp_project.root),
        env={**__import__("os").environ, **tmp_project.env},
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "EXP-04" in out["permissionDecisionReason"]
    assert "timed out" in out["permissionDecisionReason"]


def test_gate_runs_validator_from_project_root(tmp_project: TmpProject) -> None:
    sub = tmp_project.root / "scripts"
    res = run_hook(
        "gate_experiment",
        bash_payload("uv run python train.py +exp=exp_a", cwd=sub),
        env=tmp_project.env,
        cwd=sub,
    )
    assert res.decision == "allow", res.stdout + res.stderr
    assert (tmp_project.root / "stub_argv.json").exists()
