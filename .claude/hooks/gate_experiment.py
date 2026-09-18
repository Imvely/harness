#!/usr/bin/env python3
# ruff: noqa: E501  (project ruff config ignores E501; hooks are linted with --isolated)
"""PreToolUse(Bash) experiment launch gate for scripts/train.py and scripts/adapt.py.

Contract section 24.3 / 16: a training run may only start from a validated spec.
The hook never reads the spec itself; it delegates to
`uv run --no-sync python scripts/validate_spec.py --exp NAME --for-launch --json`.

Decisions (see _common.RULES): EXP-01/03/04/08 deny, EXP-02/07/09 ask, EXP-05 allow (smoke,
single simple command), EXP-06 allow only with an approval token, otherwise ask.
`allow` is never emitted for a compound command (a hook allow covers the whole tool call).
Fail-safe: internal error -> deny when a train/adapt invocation was detected, else silent.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as C  # noqa: E402

VALIDATOR_TIMEOUT_S = 45  # module constant: tests override it in-process, never via env
TRAIN_SCRIPTS = {"train.py", "adapt.py"}
MAKE_TARGETS = {"smoke", "smoke-video", "smoke-adapt", "full", "train", "adapt", "freeze"}
CONFIG_FLAGS = ("-cd", "--config-dir", "-cp", "--config-path", "-cn", "--config-name")
FIXTURE_CONFIG_DIR = "tests/fixtures/configs"
ALLOWED_SCHEMES = {"sqlite", "file", ""}

DETECTED = {"value": False}


LAUNCHERS = {"uv", "torchrun", "accelerate", "pdm", "poetry", "pipenv", "hatch", "conda", "mamba", "srun", "sbatch"}


def _find_train_segment(parsed):
    """Locate `... train.py|adapt.py ...` executed directly or via python/uv-like launchers.

    `cat scripts/train.py`, `ruff check scripts/train.py`, `echo train.py` are not launches.
    """
    for seg in parsed.segments:
        if not seg.argv:
            continue
        head = seg.argv0
        launcher = head.startswith("python") or head in LAUNCHERS
        if head == "uv":
            # `uv run [opts] python ...` or `uv run [opts] script.py`; not `uv run ruff/pytest ...`
            rest = [t for t in seg.argv[2:] if not t.startswith("-")] if len(seg.argv) > 1 and seg.argv[1] == "run" else []
            prog = C.normalize_argv0(rest[0]) if rest else ""
            launcher = prog.startswith("python") or prog in TRAIN_SCRIPTS
        for i, tok in enumerate(seg.argv):
            if C.normalize_argv0(tok) not in TRAIN_SCRIPTS:
                continue
            if i == 0 or launcher:
                return seg, i
    return None, -1


def _make_target(parsed):
    for seg in parsed.segments:
        if seg.argv and seg.argv0 == "make":
            for tok in seg.argv[1:]:
                if tok in MAKE_TARGETS:
                    return tok
    return None


def _norm_config_dir(value, cwd):
    rel = C.rel_project_path(value, cwd)
    if rel is not None:
        return rel
    return os.path.normpath(value)


def run_validator(root, exp_name, overrides, fixture_dir):
    cmd = [
        "uv",
        "run",
        "--no-sync",
        "python",
        os.path.join(root, "scripts", "validate_spec.py"),
        "--exp",
        exp_name,
        "--for-launch",
        "--json",
    ]
    if fixture_dir:
        cmd += ["--config-dir", FIXTURE_CONFIG_DIR]
    cmd += ["--"] + list(overrides)
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=VALIDATOR_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "validator timed out after %ss" % VALIDATOR_TIMEOUT_S, None
    except OSError as exc:
        return None, "validator could not start: %s" % exc, None
    stdout = proc.stdout.decode("utf-8", "replace")
    stderr = proc.stderr.decode("utf-8", "replace")
    result = None
    try:
        result = json.loads(stdout)
    except ValueError:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    result = json.loads(line)
                    break
                except ValueError:
                    continue
    if not isinstance(result, dict):
        tail = (stderr.strip() or stdout.strip()).splitlines()[-8:]
        return None, "validator exit %s without JSON: %s" % (proc.returncode, " / ".join(tail)), proc.returncode
    return result, None, proc.returncode


def _error_lines(result, limit=8):
    errors = result.get("errors") if isinstance(result, dict) else None
    if not isinstance(errors, list):
        errors = []
    lines = []
    for e in errors[:limit]:
        if isinstance(e, dict):
            lines.append("%s: %s" % (e.get("code", "ERR"), e.get("message", e)))
        else:
            lines.append(str(e))
    return lines


def _checks_summary(result):
    gate = result.get("gate") if isinstance(result, dict) else None
    if not isinstance(gate, dict):
        return "gate=n/a"
    checks = gate.get("checks")
    parts = []
    if isinstance(checks, dict):
        for name in sorted(checks):
            val = checks[name]
            ok = val.get("ok") if isinstance(val, dict) else bool(val)
            parts.append("%s=%s" % (name, "PASS" if ok else "FAIL"))
    reasons = gate.get("reasons")
    text = "allowed=%s %s" % (gate.get("allowed"), " ".join(parts))
    if isinstance(reasons, list) and reasons:
        text += " reasons: " + "; ".join(str(r) for r in reasons[:4])
    return text


def evaluate(command, cwd):
    """Return (decision or None, reason) for a Bash command. None -> no hook output."""
    parsed = C.split_commands(command)
    seg, idx = _find_train_segment(parsed)
    make_target = _make_target(parsed)
    if seg is None and make_target is None:
        return None, ""
    DETECTED["value"] = True
    if seg is None:
        return "ask", "EXP-07 `make %s` runs train/adapt inside the Makefile where the hook cannot validate the spec; run `uv run python scripts/train.py +exp=<name>` directly" % make_target
    asks = []
    if make_target is not None:
        asks.append("EXP-07 make %s bypasses spec validation" % make_target)
    script = C.normalize_argv0(seg.argv[idx])
    overrides = list(seg.argv[idx + 1 :])
    env_hit = set(seg.env_names) & C.GUARDED_ENV_NAMES
    if env_hit:
        asks.append("HK-04 segment redefines %s" % ", ".join(sorted(env_hit)))
    exp_name = None
    fixture_dir = False
    validator_overrides = []
    i = 0
    while i < len(overrides):
        tok = overrides[i]
        stripped = tok.lstrip("+~")
        key = stripped.split("=", 1)[0]
        # EXP-08: config sources outside configs/
        flag_hit = None
        flag_val = None
        for flag in CONFIG_FLAGS:
            if tok == flag:
                flag_hit = flag
                flag_val = overrides[i + 1] if i + 1 < len(overrides) else ""
                i += 1
                break
            if tok.startswith(flag + "="):
                flag_hit = flag
                flag_val = tok.split("=", 1)[1]
                break
        if flag_hit is not None:
            if flag_hit in ("-cd", "--config-dir") and _norm_config_dir(flag_val, cwd) == FIXTURE_CONFIG_DIR:
                fixture_dir = True
                i += 1
                continue
            return "deny", "EXP-08 %s %s loads configs from outside configs/ (only %s is allowed for tests)" % (flag_hit, flag_val, FIXTURE_CONFIG_DIR)
        if key.startswith("hydra.searchpath") or key.startswith("hydra/searchpath"):
            return "deny", "EXP-08 hydra.searchpath override loads configs from outside configs/"
        # EXP-01: execution.* only from the spec file (demotion to smoke allowed)
        if key == "execution" or key.startswith("execution."):
            if tok != "execution.mode=smoke":
                return "deny", "EXP-01 `%s`: execution.* is set only in configs/exp/<name>.yaml (section 16); the only CLI override allowed is the demotion execution.mode=smoke" % tok
        if tok in ("-m", "--multirun") or key.startswith("hydra.sweeper") or key.startswith("hydra/sweeper"):
            asks.append("EXP-02 multirun/sweep requested (section 20: no blind sweeps)")
            i += 1
            continue
        if key == "exp" and tok.startswith("+exp="):
            exp_name = tok.split("=", 1)[1]
            i += 1
            continue
        validator_overrides.append(tok)
        i += 1
    if not exp_name:
        return "deny", "EXP-03 %s without `+exp=<name>`: every run needs a spec in configs/exp (section 16)" % script
    root = C.project_root()
    result, err, code = run_validator(root, exp_name, validator_overrides, fixture_dir)
    if result is None:
        return "deny", "EXP-04 validate_spec --for-launch failed: %s" % err
    if not result.get("ok") or (code not in (0, None)):
        lines = _error_lines(result) or ["exit_code=%s" % result.get("exit_code", code)]
        return "deny", "EXP-04 validate_spec rejected %s (exit %s): %s" % (exp_name, result.get("exit_code", code), " | ".join(lines))
    mode = str(result.get("mode") or "")
    exp_id = result.get("experiment_id") or exp_name
    proto = str(result.get("protocol_hash") or "")[:12]
    scheme = str(result.get("tracking_uri_scheme") or "")
    remote_note = ""
    if scheme not in ALLOWED_SCHEMES:
        remote_note = "EXP-09 remote MLflow tracking (%s://) uploads artifacts off-host (section 34)" % scheme
        if mode == "smoke":
            asks.append(remote_note)
    if asks:
        return "ask", "; ".join(asks) + " [exp_id=%s protocol_hash=%s mode=%s]" % (exp_id, proto, mode)
    if mode == "smoke":
        if parsed.is_simple:
            return "allow", "EXP-05 smoke run validated: exp_id=%s protocol_hash=%s" % (exp_id, proto)
        sys.stderr.write("gate: EXP-05 smoke run validated but the command is compound; leaving the decision to permissions\n")
        return None, ""
    if mode == "full":
        summary = _checks_summary(result)
        token_ok = bool(result.get("approval_token_ok"))
        if token_ok and parsed.is_simple:
            return "allow", "EXP-06 full run approved by token: exp_id=%s protocol_hash=%s %s" % (exp_id, proto, summary)
        reason = "EXP-06 full run needs human approval: exp_id=%s protocol_hash=%s approval_token_ok=%s %s" % (exp_id, proto, token_ok, summary)
        if remote_note:
            reason += " " + remote_note
        if token_ok and not parsed.is_simple:
            reason += " (compound command: no automatic allow)"
        return "ask", reason
    return "ask", "EXP-06 unknown mode '%s' for exp_id=%s" % (mode, exp_id)


def main():
    data = C.read_input()
    if data is None or data.get("tool_name") not in (None, "Bash"):
        C.no_decision()
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        C.no_decision()
    command = tool_input.get("command")
    if not isinstance(command, str):
        C.no_decision()
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    decision, reason = evaluate(command, cwd)
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
            if DETECTED["value"]:
                C.deny("HK-99 gate internal error while a train/adapt launch was detected: %s: %s" % (type(exc).__name__, str(exc)[:200]))
            sys.exit(0)
        except SystemExit:
            raise
        except BaseException:  # noqa: B036
            sys.stdout.write('{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"HK-99 gate internal error"}}\n')
            sys.exit(0)
