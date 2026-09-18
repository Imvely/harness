#!/usr/bin/env python3
# ruff: noqa: E501  (project ruff config ignores E501; hooks are linted with --isolated)
"""SessionStart(startup|resume|compact): print a <=45 line project brief to stdout.

Nothing here can fail the session: every probe is wrapped and the hook always exits 0.
torch is reported from .venv/**/torch/version.py without importing it (no CUDA probing).
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as C  # noqa: E402

MAX_LINES = 45
CONTRACT_SHA256 = "0562540579b17857205945eb5584d6fda07852c52c48c020d4ff3de2a632d35d"


def _git(root, *args):
    try:
        proc = subprocess.run(["git"] + list(args), cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=False)
        if proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", "replace").rstrip("\n")
    except Exception:
        return None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _torch_version(root):
    for path in glob.glob(os.path.join(root, ".venv", "lib", "python*", "site-packages", "torch", "version.py")):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", text)
            cuda = re.search(r"\bcuda\s*(?::\s*Optional\[str\])?\s*=\s*(None|['\"][^'\"]*['\"])", text)
            return (m.group(1) if m else "?"), (cuda.group(1).strip("'\"") if cuda else "unknown (not imported)")
        except Exception:
            return "?", "unknown (not imported)"
    return "MISSING", "unknown (not imported)"


def _settings_warnings(root):
    warns = []
    for path in (os.path.join(os.path.expanduser("~"), ".claude", "settings.json"), os.path.join(root, ".claude", "settings.local.json")):
        try:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            if "disableAllHooks" in text:
                warns.append("WARNING: %s contains disableAllHooks -> project guards are off" % path)
            if "Bash(*)" in text:
                warns.append("WARNING: %s allows Bash(*) -> permission prompts are bypassed" % path)
        except Exception:
            continue
    return warns


def _adr_lines(root):
    out = []
    for path in sorted(glob.glob(os.path.join(root, "research", "decisions", "ADR-*.md"))):
        name = os.path.basename(path)[:-3]
        status = "?"
        title = ""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
            for i, line in enumerate(lines):
                if not title and line.startswith("# "):
                    title = line[2:].strip()
                if re.match(r"^#+\s*Status", line):
                    for nxt in lines[i + 1 : i + 4]:
                        if nxt.strip():
                            status = nxt.strip().lstrip("-* ").strip()[:20]
                            break
                m = re.match(r"^\*{0,2}Status\*{0,2}\s*[:：]\s*(.+)$", line.strip())
                if m:
                    status = m.group(1).strip()[:20]
        except Exception:
            pass
        short = name.split("-", 2)[:2]
        out.append("%s [%s]" % ("-".join(short) if len(short) == 2 else name, status))
    return out


def _registry_lines(root):
    path = os.path.join(root, "experiments", "registry.jsonl")
    if not os.path.exists(path):
        return ["registry: (none yet)"]
    rows = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    rows.append({"raw": line[:60]})
    except Exception:
        return ["registry: unreadable"]
    out = ["registry (last %d of %d): ts | exp_id | mode | status | run_id | protocol_hash" % (min(5, len(rows)), len(rows))]
    for r in rows[-5:]:
        if "raw" in r:
            out.append("  " + r["raw"])
            continue
        out.append(
            "  %s | %s | %s | %s | %s | %s"
            % (
                str(r.get("timestamp") or r.get("ts") or "")[:19],
                r.get("experiment_id") or r.get("exp_id") or "?",
                r.get("mode") or "?",
                r.get("status") or "?",
                str(r.get("run_id") or "")[:8],
                str(r.get("protocol_hash") or "")[:8],
            )
        )
    return out


def build_lines(root):
    lines = []
    warns = _settings_warnings(root)
    lines.extend(warns)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    sha = _git(root, "rev-parse", "--short=7", "HEAD") or "?"
    status = _git(root, "status", "--short")
    status_lines = [ln for ln in (status or "").splitlines() if ln.strip()]
    dirty = sum(1 for ln in status_lines if not ln.startswith("??"))
    untracked = sum(1 for ln in status_lines if ln.startswith("??"))
    lines.append("[pad-harness] branch=%s sha=%s dirty=%d untracked=%d" % (branch, sha, dirty, untracked))
    for ln in status_lines[:12]:
        lines.append("  " + ln)
    if len(status_lines) > 12:
        lines.append("  ... %d more" % (len(status_lines) - 12))
    try:
        dirs = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)) and not d.startswith("."))
        lines.append("dirs: " + " ".join(dirs[:16]))
    except Exception:
        pass
    torch_v, cuda = _torch_version(root)
    venv = "yes" if os.path.isdir(os.path.join(root, ".venv")) else "no"
    lock = "none"
    lock_path = os.path.join(root, "uv.lock")
    if os.path.exists(lock_path):
        try:
            lock = _sha256(lock_path)[:12]
        except Exception:
            lock = "unreadable"
    lines.append("env: python=%d.%d.%d venv=%s torch=%s cuda=%s lock=%s" % (sys.version_info[0], sys.version_info[1], sys.version_info[2], venv, torch_v, cuda, lock))
    if sys.version_info < (3, 8):
        lines.append("WARNING: hooks need python3 >= 3.8")
    lines.extend(_registry_lines(root))
    adrs = _adr_lines(root)
    lines.append("ADRs: " + (" ".join(adrs[:10]) if adrs else "(none)"))
    specs = len(glob.glob(os.path.join(root, "experiments", "specs", "*.yaml")))
    reports = len(glob.glob(os.path.join(root, "experiments", "reports", "*.md")))
    protos = glob.glob(os.path.join(root, "configs", "protocol", "*.yaml"))
    active = 0
    for p in protos:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                if re.search(r"^status:\s*active", fh.read(), re.MULTILINE):
                    active += 1
        except Exception:
            pass
    lines.append("specs: %d frozen | reports: %d | protocols: %d active / %d total" % (specs, reports, active, len(protos)))
    exps = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(root, "configs", "exp", "*.yaml")))
    lines.append("configs/exp: " + (" ".join(exps[:8]) + (" ..." if len(exps) > 8 else "") if exps else "(none)"))
    contract = os.path.join(root, "docs", "RESEARCH_CONTRACT.md")
    if os.path.exists(contract):
        try:
            if _sha256(contract) != CONTRACT_SHA256:
                lines.append("WARNING: docs/RESEARCH_CONTRACT.md differs from the pinned sha (approved revision? record it in an ADR)")
        except Exception:
            pass
    else:
        lines.append("WARNING: docs/RESEARCH_CONTRACT.md missing")
    lines.append("reminder: classify the request first -> Research / Code / Experiment / Analysis (contract section 36), then read .claude/rules")
    return lines[:MAX_LINES]


def main():
    try:
        C.read_input()
    except Exception:
        pass
    root = C.project_root()
    for line in build_lines(root):
        sys.stdout.write(line + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except BaseException as exc:  # noqa: B036 - the brief must never break a session
        try:
            sys.stdout.write("[pad-harness] session_start error: %s\n" % type(exc).__name__)
        except Exception:
            pass
    sys.exit(0)
