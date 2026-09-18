#!/usr/bin/env python3
# ruff: noqa: E501  (project ruff config ignores E501; hooks are linted with --isolated)
"""Shared helpers for the pad-research Claude Code hooks.

Constraints (see docs/RESEARCH_CONTRACT.md section 24 and the hook refuter report):
  * stdlib only, Python 3.8-compatible syntax (the H100 host may run an old system python3)
  * every hook wraps main() in try/except BaseException and fails SAFE, because Claude Code
    treats exit 1 / uncaught exceptions as NON-blocking (fail-open)
  * a hook never reads a PAD_* environment switch; behaviour is fixed by code + files only
  * a hook only emits `allow` for a single simple command segment (a hook `allow` applies to
    the whole tool call, so `train ... && git push` must never inherit an allow)

Command parsing (D15, revised): shlex with punctuation_chars keeps quotes intact, so
`python -c "a; b"` stays one segment. Segments are split on ; && || | |& & ( ) and newlines.
Wrappers (sudo/env/time/nohup/nice/ionice/stdbuf/command/builtin/exec/setsid/timeout N/VAR=)
are stripped, `bash -c STR` and `eval STR` are re-parsed one level deep, and targets that
contain `$`, `~` or a backtick are reported as unresolvable so the caller can `ask`.

Run `python3 .claude/hooks/_common.py --rules-table` to print the rule table used by the
docs (.claude/rules/experiment-safety.md must stay in sync).
"""
import fnmatch
import json
import os
import re
import shlex
import sys
from typing import Any, Dict, List, Optional, Tuple

HOOK_EVENT = "PreToolUse"

# ---------------------------------------------------------------------------
# stream setup (Korean/UTF-8 reasons must never raise UnicodeEncodeError -> exit 1 -> fail-open)
# ---------------------------------------------------------------------------


def reconfigure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            reconf = getattr(stream, "reconfigure", None)
            if reconf is not None:
                reconf(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover - best effort only
            pass


reconfigure_streams()

# ---------------------------------------------------------------------------
# protected path sets (relative to the project root, POSIX separators)
# ---------------------------------------------------------------------------

# rm -r of exactly these (or of the project root / its parents) -> DG-01 deny
PROTECTED_ROOTS = {
    "",  # project root itself
    "data",
    "data/raw",
    "data/processed",
    "data/manifests",
    "checkpoints",
    "artifacts",
    "research",
    "experiments",
    "configs",
    "src",
    "docs",
    "tests",
    "scripts",
    ".git",
    ".claude",
    ".github",
}

# any path at or below these is irreversible research state -> rm (any form) deny
DENY_TREES = (
    "data/raw",
    "data/processed",
    "data/manifests",
    "checkpoints",
    ".git",
    "research/claims",
    "research/decisions",
    "experiments/specs",
    "experiments/approvals",
    "experiments/reports",
    "configs/protocol",
)

# rm -r of these needs no decision (they are all in .gitignore and regenerable). Keep this list
# identical to the ephemeral entries of .gitignore.
EPHEMERAL_BASENAMES = {".pytest_cache", ".ruff_cache", ".mypy_cache", "__pycache__", ".hydra"}
EPHEMERAL_PREFIXES = ("outputs", "multirun", "build", "dist")

# Edit/Write/Bash edits of these -> ask (PF-xx / DG-12)
PROTECTED_FILES = (
    "CLAUDE.md",
    "docs/RESEARCH_CONTRACT.md",
    "data/manifests/**",
    "research/claims/**",
    "configs/protocol/**",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/hooks/**",
    ".claude/rules/**",
    ".claude/agents/**",
    ".claude/skills/**",
    ".claude/commands/**",
    "uv.lock",
    "experiments/specs/**",
)

# Edit/Write/Bash edits of these -> deny (only scripts / the human write them)
DENY_FILES = (
    "experiments/registry.jsonl",
    "experiments/approvals/**",
)

# sources whose upload to a remote is governed by contract sections 22/34
UPLOAD_PROTECTED = ("data/raw", "data/processed", "data/manifests", "checkpoints", "artifacts")

# env names a Bash segment must not (re)define (would redirect the harness' own state)
GUARDED_ENV_NAMES = {"PAD_REPO_ROOT", "PAD_REGISTRY_PATH", "MLFLOW_TRACKING_URI", "CLAUDE_PROJECT_DIR"}

SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
WRAPPERS = {
    "sudo",
    "doas",
    "env",
    "time",
    "nohup",
    "nice",
    "ionice",
    "stdbuf",
    "command",
    "builtin",
    "exec",
    "setsid",
}
# wrapper options that consume the following token
WRAPPER_VALUE_OPTS = {"-u", "-g", "-n", "-c", "-o", "-e", "-i", "-C", "-S", "-p"}
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SEP_CHARS = set(";&|()<>\n")
_REDIRECT_CHARS = set("<>&")

# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def read_input() -> Optional[Dict[str, Any]]:
    """Parse the hook's stdin JSON. Returns None when it is missing or not an object."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return None
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def decide(decision: str, reason: str, event: str = HOOK_EVENT) -> None:
    """Emit the PreToolUse decision JSON and exit 0. deny also mirrors the reason to stderr."""
    if decision not in ("allow", "deny", "ask"):
        decision = "ask"
    out = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=True) + "\n")
    sys.stdout.flush()
    if decision == "deny":
        sys.stderr.write(reason + "\n")
        sys.stderr.flush()
    sys.exit(0)


def ask(reason: str) -> None:
    decide("ask", reason)


def deny(reason: str) -> None:
    decide("deny", reason)


def allow(reason: str) -> None:
    decide("allow", reason)


def no_decision() -> None:
    sys.exit(0)


# ---------------------------------------------------------------------------
# project root / path helpers
# ---------------------------------------------------------------------------


def project_root() -> str:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return os.path.abspath(env)
    cur = os.getcwd()
    while True:
        if os.path.exists(os.path.join(cur, "pyproject.toml")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.getcwd()
        cur = parent


def _real_root() -> str:
    return os.path.realpath(project_root())


def rel_project_path(path: str, cwd: Optional[str] = None) -> Optional[str]:
    """Return `path` relative to the real project root ('' for the root), or None if outside."""
    if cwd is None:
        cwd = os.getcwd()
    absolute = path if os.path.isabs(path) else os.path.join(cwd, path)
    real = os.path.realpath(absolute)
    root = _real_root()
    if real == root:
        return ""
    if real.startswith(root + os.sep):
        return real[len(root) + 1 :].replace(os.sep, "/")
    return None


def is_root_or_parent(path: str, cwd: Optional[str] = None) -> bool:
    """True when `path` resolves to the project root or one of its ancestors (incl. '/')."""
    if cwd is None:
        cwd = os.getcwd()
    absolute = path if os.path.isabs(path) else os.path.join(cwd, path)
    real = os.path.realpath(absolute)
    root = _real_root()
    if real == root:
        return True
    return root.startswith(real.rstrip(os.sep) + os.sep)


def under_tmp(path: str, cwd: Optional[str] = None) -> bool:
    if cwd is None:
        cwd = os.getcwd()
    absolute = path if os.path.isabs(path) else os.path.join(cwd, path)
    real = os.path.realpath(absolute)
    return real.startswith("/tmp/") or real.startswith("/var/tmp/")


def matches_glob(rel: str, pattern: str) -> bool:
    """fnmatch-based glob with directory-prefix semantics for `dir/**` patterns."""
    if rel is None:
        return False
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
        return fnmatch.fnmatchcase(rel, pattern)
    if fnmatch.fnmatchcase(rel, pattern):
        return True
    return False


def matches_any(rel: Optional[str], patterns) -> Optional[str]:
    if rel is None:
        return None
    for pat in patterns:
        if matches_glob(rel, pat):
            return pat
    return None


def under_tree(rel: Optional[str], trees) -> Optional[str]:
    """Return the tree that `rel` is at or below (prefix match on path components)."""
    if rel is None:
        return None
    for tree in trees:
        if rel == tree or rel.startswith(tree + "/"):
            return tree
    return None


def covers_tree(rel: Optional[str], trees) -> Optional[str]:
    """Return a tree that `rel` is at/below OR that lies below `rel` (rel is an ancestor)."""
    hit = under_tree(rel, trees)
    if hit is not None:
        return hit
    if rel is None:
        return None
    for tree in trees:
        if rel == "" or tree.startswith(rel + "/"):
            return tree
    return None


def is_mlruns(rel: Optional[str]) -> bool:
    if not rel:
        return False
    first = rel.split("/", 1)[0]
    return first.startswith("mlruns")


def is_ephemeral(rel: Optional[str]) -> bool:
    if rel is None or rel == "":
        return False
    parts = rel.split("/")
    if any(p in EPHEMERAL_BASENAMES for p in parts):
        return True
    if parts[0] in EPHEMERAL_PREFIXES:
        return True
    if any(p.endswith(".egg-info") for p in parts):
        return True
    return False


def is_protected_file(rel: Optional[str]) -> Optional[str]:
    return matches_any(rel, PROTECTED_FILES)


def is_deny_file(rel: Optional[str]) -> Optional[str]:
    return matches_any(rel, DENY_FILES)


# ---------------------------------------------------------------------------
# command parsing
# ---------------------------------------------------------------------------


class Segment(object):
    """One simple command after wrapper stripping."""

    def __init__(self) -> None:
        self.argv = []  # type: List[str]
        self.env_names = []  # type: List[str]
        self.redirects = []  # type: List[str]  (output redirection targets)
        self.sep = None  # type: Optional[str]  separator BEFORE this segment
        self.after_cd = False
        self.indirect = False  # via xargs / depth exceeded: targets cannot be trusted
        self.depth = 0

    @property
    def argv0(self) -> str:
        return normalize_argv0(self.argv[0]) if self.argv else ""

    def args(self) -> List[str]:
        return self.argv[1:]

    def positional(self) -> List[str]:
        return [a for a in self.argv[1:] if not a.startswith("-")]

    def __repr__(self) -> str:  # pragma: no cover
        return "Segment(%r, sep=%r, cd=%r, redirects=%r)" % (
            self.argv,
            self.sep,
            self.after_cd,
            self.redirects,
        )


class ParsedCommand(object):
    def __init__(self) -> None:
        self.segments = []  # type: List[Segment]
        self.has_redirect = False
        self.has_background = False
        self.has_subshell = False
        self.lex_failed = False
        self.depth_exceeded = False
        self.has_indirect = False

    @property
    def n_segments(self) -> int:
        return len(self.segments)

    @property
    def is_simple(self) -> bool:
        """Exactly one segment, no redirection/background/subshell, cleanly tokenized."""
        return (
            self.n_segments == 1
            and not self.has_redirect
            and not self.has_background
            and not self.has_subshell
            and not self.lex_failed
            and not self.depth_exceeded
            and not self.has_indirect
            and not self.segments[0].env_names
        )

    def flags(self) -> Dict[str, Any]:
        return {
            "has_redirect": self.has_redirect,
            "has_background": self.has_background,
            "has_subshell": self.has_subshell,
            "n_segments": self.n_segments,
            "lex_failed": self.lex_failed,
            "depth_exceeded": self.depth_exceeded,
            "has_indirect": self.has_indirect,
        }


def normalize_argv0(tok: str) -> str:
    tok = tok.lstrip("\\")
    return os.path.basename(tok) if "/" in tok else tok


def _tokenize(cmd: str) -> Tuple[List[str], bool]:
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    try:
        return list(lex), False
    except ValueError:
        return cmd.split(), True


def _is_sep_token(tok: str) -> bool:
    return bool(tok) and all(c in _SEP_CHARS for c in tok)


def _is_redirect_op(tok: str) -> bool:
    return bool(tok) and all(c in _REDIRECT_CHARS for c in tok) and ("<" in tok or ">" in tok)


def _split_tokens(tokens: List[str], parsed: ParsedCommand) -> List[Tuple[Optional[str], List[str], List[str]]]:
    """Split a token stream into (separator, raw_argv, redirect_targets) groups."""
    groups = []  # type: List[Tuple[Optional[str], List[str], List[str]]]
    cur = []  # type: List[str]
    redirects = []  # type: List[str]
    sep = None  # type: Optional[str]
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if _is_redirect_op(tok):
            parsed.has_redirect = True
            if "<<" in tok:
                parsed.has_subshell = True
            # a lone single digit right before the operator is a file descriptor, not an arg
            if cur and re.match(r"^\d$", cur[-1]):
                cur.pop()
            if i + 1 < n:
                target = tokens[i + 1]
                i += 2
                if tok in (">&", "<&") and re.match(r"^\d+$", target):
                    continue
                if ">" in tok:
                    redirects.append(target)
                continue
            i += 1
            continue
        if _is_sep_token(tok):
            if "&" in tok and "|" not in tok and "&&" not in tok:
                parsed.has_background = True
            if cur:
                groups.append((sep, cur, redirects))
            cur = []
            redirects = []
            sep = tok.strip() or ";"
            i += 1
            continue
        if tok == "$":
            parsed.has_subshell = True
        cur.append(tok)
        i += 1
    if cur or redirects:
        groups.append((sep, cur, redirects))
    return groups


def _strip_wrappers(argv: List[str], env_names: List[str]) -> List[str]:
    argv = list(argv)
    while argv:
        head = normalize_argv0(argv[0])
        if _ENV_ASSIGN_RE.match(argv[0]):
            env_names.append(argv[0].split("=", 1)[0])
            argv.pop(0)
            continue
        if head in WRAPPERS:
            argv.pop(0)
            while argv and argv[0].startswith("-") and argv[0] != "--":
                opt = argv.pop(0)
                if opt in WRAPPER_VALUE_OPTS and argv:
                    argv.pop(0)
            if argv and argv[0] == "--":
                argv.pop(0)
            continue
        if head == "timeout":
            argv.pop(0)
            while argv and argv[0].startswith("-"):
                opt = argv.pop(0)
                if opt in ("-s", "-k", "--signal", "--kill-after") and argv:
                    argv.pop(0)
            if argv:
                argv.pop(0)  # the duration
            continue
        break
    return argv


def _parse_into(cmd: str, parsed: ParsedCommand, depth: int, inherited_cd: bool, inherited_sep: Optional[str]) -> List[Segment]:
    cmd = re.sub(r"\\\r?\n", " ", cmd)
    if "$(" in cmd or "`" in cmd or "<<" in cmd or "${" in cmd:
        parsed.has_subshell = True
    tokens, failed = _tokenize(cmd)
    if failed:
        parsed.lex_failed = True
    groups = _split_tokens(tokens, parsed)
    segments = []  # type: List[Segment]
    seen_cd = inherited_cd
    first = True
    for sep, raw_argv, redirects in groups:
        env_names = []  # type: List[str]
        argv = _strip_wrappers(raw_argv, env_names)
        if first:
            sep = inherited_sep
            first = False
        if not argv:
            if redirects or env_names:
                seg = Segment()
                seg.env_names = env_names
                seg.redirects = redirects
                seg.sep = sep
                seg.after_cd = seen_cd
                seg.depth = depth
                segments.append(seg)
            continue
        head = normalize_argv0(argv[0])
        # one-level recursion into `bash -c STR` / `eval STR`
        inner = None  # type: Optional[str]
        if head in SHELLS:
            for idx, tok in enumerate(argv[1:], start=1):
                if tok == "-c" and idx + 1 < len(argv):
                    inner = argv[idx + 1]
                    break
                if tok.startswith("-") and "c" in tok and idx + 1 < len(argv) and not tok.startswith("--"):
                    inner = argv[idx + 1]
                    break
        elif head == "eval":
            inner = " ".join(argv[1:])
        if inner is not None:
            if depth >= 1:
                parsed.depth_exceeded = True
                seg = Segment()
                seg.argv = argv
                seg.env_names = env_names
                seg.redirects = redirects
                seg.sep = sep
                seg.after_cd = seen_cd
                seg.indirect = True
                seg.depth = depth
                parsed.has_indirect = True
                segments.append(seg)
                continue
            inner_segments = _parse_into(inner, parsed, depth + 1, seen_cd, sep)
            for s in inner_segments:
                s.env_names = env_names + s.env_names
            if inner_segments:
                inner_segments[-1].redirects = inner_segments[-1].redirects + redirects
            segments.extend(inner_segments)
            if any(normalize_argv0(s.argv[0]) in ("cd", "pushd") for s in inner_segments if s.argv):
                seen_cd = True
            continue
        indirect = False
        if head == "xargs":
            parsed.has_indirect = True
            indirect = True
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                opt = argv.pop(0)
                if opt in ("-I", "-n", "-P", "-L", "-d", "-a", "-s", "-E") and argv:
                    argv.pop(0)
            if not argv:
                argv = ["xargs"]
        seg = Segment()
        seg.argv = argv
        seg.env_names = env_names
        seg.redirects = redirects
        seg.sep = sep
        seg.after_cd = seen_cd
        seg.indirect = indirect
        seg.depth = depth
        segments.append(seg)
        if normalize_argv0(argv[0]) in ("cd", "pushd"):
            seen_cd = True
    return segments


def split_commands(cmd: str) -> ParsedCommand:
    parsed = ParsedCommand()
    if not isinstance(cmd, str):
        parsed.lex_failed = True
        return parsed
    parsed.segments = _parse_into(cmd, parsed, 0, False, None)
    return parsed


# ---------------------------------------------------------------------------
# target classification
# ---------------------------------------------------------------------------

UNRESOLVABLE = "unresolvable"
INSIDE = "inside"
OUTSIDE = "outside"


class Target(object):
    def __init__(self, raw: str, kind: str, rel: Optional[str], wildcard: bool) -> None:
        self.raw = raw
        self.kind = kind
        self.rel = rel  # project-relative path when kind == INSIDE
        self.wildcard = wildcard

    def __repr__(self) -> str:  # pragma: no cover
        return "Target(%r, %s, %r)" % (self.raw, self.kind, self.rel)


def classify_target(tok: str, cwd: str, seg: Optional[Segment] = None) -> Target:
    """Resolve a path-like token to a project-relative path, or flag it unresolvable."""
    if tok is None:
        return Target("", UNRESOLVABLE, None, False)
    if "$" in tok or "`" in tok or tok.startswith("~") or "/~" in tok:
        if tok in ("~", "~/"):
            return Target(tok, OUTSIDE, None, False)
        return Target(tok, UNRESOLVABLE, None, False)
    if seg is not None and (seg.indirect or seg.after_cd) and not os.path.isabs(tok):
        return Target(tok, UNRESOLVABLE, None, False)
    wildcard = False
    stripped = tok
    if any(c in stripped for c in "*?["):
        wildcard = True
        # `dir/*` deletes the content of dir: judge the directory itself
        base = os.path.basename(stripped)
        if base and any(c in base for c in "*?["):
            stripped = os.path.dirname(stripped) or "."
    rel = rel_project_path(stripped, cwd)
    if rel is None:
        return Target(tok, OUTSIDE, None, wildcard)
    return Target(tok, INSIDE, rel, wildcard)


def is_remote(tok: str) -> bool:
    if "://" in tok:
        return True
    return bool(re.match(r"^([A-Za-z0-9._-]+@)?[A-Za-z0-9._-]+:", tok)) and not os.path.exists(tok)


def is_public_hub(tok: str) -> bool:
    low = tok.lower()
    return "huggingface.co" in low or low.startswith("hf://") or "wandb.ai" in low or "gist.github.com" in low


# ---------------------------------------------------------------------------
# rule registry (single source for the docs table)
# ---------------------------------------------------------------------------

RULES = [
    ("HK-00", "guard/protect", "stdin JSON missing or invalid", "ask"),
    ("HK-02", "guard", "xargs / source / eval-depth exceeded with a destructive command family", "ask"),
    ("HK-03", "guard", "target contains $ ~ or backtick (cannot be resolved statically) in a destructive family", "ask"),
    ("HK-04", "guard/gate", "segment assigns PAD_REPO_ROOT / PAD_REGISTRY_PATH / MLFLOW_TRACKING_URI / CLAUDE_PROJECT_DIR", "ask"),
    ("HK-99", "all", "internal hook error (fail-safe)", "ask (gate: deny if train/adapt seen)"),
    ("DG-01", "guard", "rm -r of a protected root (data, checkpoints, mlruns*, research, .git, project root, / ...)", "deny"),
    ("DG-02", "guard", "rm -r elsewhere (ephemeral caches/outputs: no decision; .venv and others: ask)", "ask"),
    ("DG-03", "guard", "rm of a protected/deny file or of irreversible data (data/raw, manifests, claims, specs ...)", "deny"),
    ("DG-04", "guard", "git filter-branch/filter-repo, push --force to main|master", "deny"),
    ("DG-04", "guard", "git reset --hard, clean -f/-d/-x, branch -D, push --force (other), stash drop|clear, checkout/restore/rm of protected paths", "ask"),
    ("DG-05", "guard", "dvc destroy | dvc gc", "deny"),
    ("DG-05", "guard", "dvc remove | dvc checkout --force", "ask"),
    ("DG-06", "guard", "find -delete/-exec rm from a protected root or '.', truncate/shred/dd of= protected", "deny"),
    ("DG-07", "guard", "mlflow gc | experiments delete | runs delete; python -c delete_run/delete_experiment; sqlite3 mlruns.db DELETE/DROP/UPDATE (section 35)", "deny"),
    ("DG-08", "guard", "upload of data/raw, data/processed, checkpoints, artifacts, mlruns* to a public hub (huggingface, gist/release, wandb)", "deny"),
    ("DG-08", "guard", "upload of the same sources to any other remote (scp/rsync/aws/gsutil/rclone/curl -T ...); downloads and --dry-run pass", "ask"),
    ("DG-09", "guard", "pipeline: cat/tar/zip/dd of protected data piped into ssh/nc/socat/curl/wget", "ask"),
    ("DG-12", "guard", "Bash edit (redirect, sed -i, tee, cp/mv/install, python open(w)) of a protected file", "ask"),
    ("DG-12", "guard", "Bash edit of experiments/registry.jsonl or experiments/approvals/**, or running scripts/approve_full_run.py", "deny"),
    ("DG-13", "guard", "cat/head/tail/base64/xxd/... of data/raw/** or data/processed/** (section 34: no raw frames in context)", "ask"),
    ("DG-14", "guard", "curl|wget piped into sh/bash/python", "ask"),
    ("EXP-01", "gate", "execution.* CLI override (except the demotion execution.mode=smoke)", "deny"),
    ("EXP-02", "gate", "-m / --multirun / hydra.sweeper (section 20: no blind sweeps)", "ask"),
    ("EXP-03", "gate", "train.py/adapt.py without +exp=<name> (section 16)", "deny"),
    ("EXP-04", "gate", "validate_spec --for-launch failed, timed out or returned no JSON", "deny"),
    ("EXP-05", "gate", "valid spec, mode smoke, single simple command", "allow"),
    ("EXP-06", "gate", "valid spec, mode full: allow only with approval token (approval_token_ok) and a single simple command", "allow / ask"),
    ("EXP-07", "gate", "make smoke|smoke-video|smoke-adapt|full|train|adapt|freeze (hook cannot inspect Makefile)", "ask"),
    ("EXP-08", "gate", "-cd/--config-dir/-cp/--config-path/-cn/--config-name/hydra.searchpath (only tests/fixtures/configs allowed)", "deny"),
    ("EXP-09", "gate", "tracking_uri_scheme not sqlite/file (remote MLflow artifact upload)", "ask (smoke) / noted (full)"),
    ("PF-01", "protect", "CLAUDE.md, docs/RESEARCH_CONTRACT.md", "ask"),
    ("PF-02", "protect", "data/manifests/**", "ask"),
    ("PF-03", "protect", "configs/protocol/** (+ changed top-level keys)", "ask"),
    ("PF-04", "protect", "research/claims/**", "ask"),
    ("PF-05", "protect", ".claude/settings*.json, hooks/**, rules/**, agents/**, skills/**, commands/**", "ask"),
    ("PF-06", "protect", "uv.lock", "ask"),
    ("PF-07", "protect", "existing research/decisions/ADR-*.md (new ADR passes)", "ask"),
    ("PF-08", "protect", "experiments/registry.jsonl, experiments/approvals/**", "deny"),
    ("PF-09", "protect", "experiments/specs/*.resolved.yaml (deny) / other experiments/specs/** (ask)", "deny / ask"),
    ("PF-10", "protect", "configs/exp/**, configs/config.yaml: execution.* key changes only", "ask"),
    ("PF-11", "protect", "~/.claude/** (user-level settings/hooks)", "ask"),
]


def rules_table() -> str:
    lines = ["| ID | Hook | Pattern | Decision |", "|---|---|---|---|"]
    for rid, hook, pattern, decision in RULES:
        lines.append("| %s | %s | %s | %s |" % (rid, hook, pattern.replace("|", "\\|"), decision))
    return "\n".join(lines)


def _main() -> int:
    if "--rules-table" in sys.argv[1:]:
        sys.stdout.write(rules_table() + "\n")
        return 0
    sys.stdout.write(__doc__ or "")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
