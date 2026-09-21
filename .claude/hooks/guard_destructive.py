#!/usr/bin/env python3
# ruff: noqa: E501  (project ruff config ignores E501; hooks are linted with --isolated)
"""PreToolUse(Bash) guard: block or confirm destructive / data-exfiltrating commands.

Rule IDs (DG-xx, HK-xx) are listed in `_common.RULES`; the highest severity wins
(deny > ask > none). This hook NEVER emits `allow` - allowing is left to permissions.
Fail-safe: any internal error -> ask("HK-99 ...") because exit 1 would fail open.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as C  # noqa: E402
from _common import INSIDE, OUTSIDE, UNRESOLVABLE, Segment  # noqa: E402

DENY = 2
ASK = 1

RM_DATA_TREES = C.DENY_TREES
UPLOAD_TOOLS = {
    "scp",
    "sftp",
    "rsync",
    "aws",
    "gsutil",
    "gcloud",
    "az",
    "rclone",
    "azcopy",
    "s3cmd",
    "mc",
    "b2",
    "curl",
    "wget",
    "dvc",
    "git",
    "huggingface-cli",
    "hf",
    "gh",
    "wandb",
}
READ_TOOLS = {"cat", "head", "tail", "less", "more", "base64", "xxd", "hexdump", "od", "strings"}
PIPE_READERS = {"cat", "tar", "zip", "dd", "gzip", "bzip2", "xz", "base64", "cpio"}
NET_SINKS = {"ssh", "nc", "ncat", "socat", "curl", "wget"}
SHELL_SINKS = {"sh", "bash", "zsh", "dash", "ksh", "python", "python3", "python2"}
DANGEROUS_FAMILIES = {
    "rm",
    "git",
    "dvc",
    "find",
    "truncate",
    "shred",
    "dd",
    "mlflow",
    "sqlite3",
    "sed",
    "tee",
    "cp",
    "mv",
    "install",
    "python",
    "python3",
    "uv",
} | UPLOAD_TOOLS


class Verdict(object):
    def __init__(self) -> None:
        self.items = []  # type: list

    def add(self, level: int, rule: str, msg: str) -> None:
        self.items.append((level, rule, msg))

    def deny(self, rule: str, msg: str) -> None:
        self.add(DENY, rule, msg)

    def ask(self, rule: str, msg: str) -> None:
        self.add(ASK, rule, msg)

    def emit(self) -> None:
        if not self.items:
            C.no_decision()
        top = max(i[0] for i in self.items)
        chosen = [i for i in self.items if i[0] == top]
        primary = "%s %s" % (chosen[0][1], chosen[0][2])
        extra = ["%s %s" % (r, m) for _, r, m in chosen[1:]] + [
            "%s %s" % (r, m) for lv, r, m in self.items if lv != top
        ]
        reason = primary
        if extra:
            reason += " | also: " + "; ".join(extra[:4])
        C.decide("deny" if top == DENY else "ask", reason)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _short_flags(args) -> str:
    out = ""
    for a in args:
        if a.startswith("-") and not a.startswith("--") and len(a) > 1:
            out += a[1:]
    return out


def _has_flag(args, short: str = "", longs=()) -> bool:
    if short and short in _short_flags(args):
        return True
    return any(a == lg or a.startswith(lg + "=") for a in args for lg in longs)


def _targets(seg: Segment, cwd: str, toks=None):
    toks = seg.positional() if toks is None else toks
    return [C.classify_target(t, cwd, seg) for t in toks]


def _protected_rm_reason(t) -> str:
    if t.kind == INSIDE:
        return "'%s' (project-relative '%s')" % (t.raw, t.rel or ".")
    return "'%s'" % t.raw


def _python_c_source(seg: Segment):
    """Return the -c source string of a python / uv run python invocation, if any."""
    argv = seg.argv
    if not argv:
        return None
    head = seg.argv0
    start = 0
    if head == "uv":
        if len(argv) < 2 or argv[1] != "run":
            return None
        start = 2
        while start < len(argv) and argv[start].startswith("-"):
            start += 1
        if start >= len(argv) or not C.normalize_argv0(argv[start]).startswith("python"):
            return None
    elif not head.startswith("python"):
        return None
    for i in range(start, len(argv) - 1):
        if argv[i] == "-c":
            return argv[i + 1]
    return None


def _python_script_tokens(seg: Segment):
    """Basenames of *.py tokens in a python / uv run invocation."""
    head = seg.argv0
    if head != "uv" and not head.startswith("python"):
        return []
    return [C.normalize_argv0(t) for t in seg.argv[1:] if t.endswith(".py")]


def _git_subcommand(seg: Segment):
    """Return (subcommand, args_after_subcommand, saw_C) for a git segment."""
    argv = seg.argv[1:]
    i = 0
    saw_c = False
    while i < len(argv):
        a = argv[i]
        if a in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            if a == "-C":
                saw_c = True
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        return a, argv[i + 1 :], saw_c
    return None, [], saw_c


def _pathspecs(args):
    """Paths after `--`, or positional args if no `--`."""
    if "--" in args:
        return args[args.index("--") + 1 :]
    return [a for a in args if not a.startswith("-")]


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------


def check_rm(seg: Segment, cwd: str, v: Verdict) -> None:
    args = seg.args()
    recursive = "r" in _short_flags(args).lower() or "--recursive" in args
    paths = [a for a in args if not a.startswith("-") or a == "-"]
    if "--" in args:
        paths = args[args.index("--") + 1 :]
    for t in _targets(seg, cwd, paths):
        if t.kind == UNRESOLVABLE:
            v.ask("HK-03", "rm target '%s' cannot be resolved statically ($, ~, backtick or after cd)" % t.raw)
            continue
        if t.raw in ("~", "~/"):
            v.deny("DG-01", "rm -r of the home directory")
            continue
        if t.kind == OUTSIDE:
            if C.is_root_or_parent(t.raw, cwd):
                v.deny("DG-01", "rm of the project root or one of its parents (%s)" % t.raw)
            elif recursive and C.under_tmp(t.raw, cwd):
                pass
            elif recursive:
                v.ask("DG-02", "rm -r outside the project: %s" % t.raw)
            continue
        rel = t.rel or ""
        if recursive and rel in C.PROTECTED_ROOTS:
            v.deny("DG-01", "rm -r of protected root %s" % _protected_rm_reason(t))
            continue
        if C.is_deny_file(rel) or C.is_protected_file(rel):
            v.deny("DG-03", "rm of protected file/dir %s (contract sections 24.4/35)" % _protected_rm_reason(t))
            continue
        if C.covers_tree(rel, RM_DATA_TREES) or C.is_mlruns(rel):
            if recursive or C.under_tree(rel, RM_DATA_TREES) or C.is_mlruns(rel):
                v.deny("DG-03" if not recursive else "DG-01", "rm of irreversible research data %s (section 35: failed runs are kept)" % _protected_rm_reason(t))
                continue
        if recursive:
            if rel in C.PROTECTED_ROOTS:
                v.deny("DG-01", "rm -r of protected root %s" % _protected_rm_reason(t))
            elif C.is_ephemeral(rel):
                pass
            elif rel == ".venv" or rel.startswith(".venv/"):
                v.ask("DG-02", "rm -r of .venv (re-create with `uv sync --frozen`)")
            else:
                v.ask("DG-02", "rm -r of %s" % _protected_rm_reason(t))


def check_git(seg: Segment, cwd: str, v: Verdict) -> None:
    sub, args, saw_c = _git_subcommand(seg)
    if sub is None:
        return
    if sub in ("filter-branch", "filter-repo"):
        v.deny("DG-04", "git %s rewrites history irreversibly" % sub)
        return
    if sub == "lfs" and args and args[0] == "push":
        if "--dry-run" in args or "-n" in args:
            return
        v.ask("DG-08", "git lfs push uploads tracked binaries to a remote (sections 22/34)")
        return
    if sub == "push":
        forced = _has_flag(args, "f", ("--force", "--force-with-lease", "--force-if-includes"))
        refspecs = [a for a in args if not a.startswith("-")]
        forced = forced or any(a.startswith("+") for a in refspecs)
        if forced:
            targets_main = False
            for r in refspecs[1:]:
                dst = r.split(":")[-1].lstrip("+")
                if dst in ("main", "master", "refs/heads/main", "refs/heads/master"):
                    targets_main = True
            if targets_main:
                v.deny("DG-04", "git push --force to main/master")
            else:
                v.ask("DG-04", "git push --force (branch history rewrite)")
        return
    if sub == "reset" and "--hard" in args:
        v.ask("DG-04", "git reset --hard discards uncommitted work; check `git status --short` first")
        return
    if sub == "clean":
        if "-n" in args or "--dry-run" in args or "n" in _short_flags(args):
            return
        if _has_flag(args, "f", ("--force",)) or _has_flag(args, "d") or _has_flag(args, "x"):
            v.ask("DG-04", "git clean removes untracked files (use -n first)")
        return
    if sub == "branch":
        if _has_flag(args, "D") or ("--delete" in args and "--force" in args):
            v.ask("DG-04", "git branch -D force-deletes a branch")
        return
    if sub == "stash" and args and args[0] in ("drop", "clear"):
        v.ask("DG-04", "git stash %s discards stashed work" % args[0])
        return
    if sub in ("checkout", "restore", "rm"):
        if sub == "restore" and ("--staged" in args or "-S" in args) and "--worktree" not in args and "-W" not in args:
            return
        specs = _pathspecs(args)
        if sub == "checkout" and "--" not in args:
            # `git checkout <branch>`: only treat existing paths as pathspecs
            specs = [s for s in specs if os.path.exists(os.path.join(cwd, s))]
        if saw_c:
            specs = list(specs)
        for t in _targets(seg, cwd, specs):
            if t.kind == UNRESOLVABLE or saw_c:
                v.ask("HK-03", "git %s target '%s' cannot be resolved statically" % (sub, t.raw))
                continue
            if t.kind == OUTSIDE:
                if C.is_root_or_parent(t.raw, cwd):
                    v.ask("DG-04", "git %s of the whole tree touches protected files" % sub)
                continue
            rel = t.rel or ""
            if rel == "" or C.is_deny_file(rel) or C.is_protected_file(rel) or C.covers_tree(rel, C.DENY_TREES):
                v.ask("DG-04", "git %s overwrites/removes protected path '%s' (worktree change)" % (sub, rel or "."))
        return


def check_dvc(seg: Segment, cwd: str, v: Verdict) -> None:
    args = seg.args()
    sub = next((a for a in args if not a.startswith("-")), None)
    if sub in ("destroy", "gc"):
        v.deny("DG-05", "dvc %s deletes cached data irreversibly" % sub)
    elif sub == "remove":
        v.ask("DG-05", "dvc remove stops tracking data")
    elif sub == "checkout" and ("--force" in args or "f" in _short_flags(args)):
        v.ask("DG-05", "dvc checkout --force overwrites the workspace")
    elif sub == "push":
        if "--dry-run" not in args and "-n" not in args:
            v.ask("DG-08", "dvc push uploads tracked data to the remote (sections 22/34: license/PII policy first)")


def check_find(seg: Segment, cwd: str, v: Verdict) -> None:
    args = seg.args()
    deletes = "-delete" in args
    for i, a in enumerate(args):
        if a in ("-exec", "-execdir", "-ok", "-okdir") and i + 1 < len(args):
            if C.normalize_argv0(args[i + 1]) in ("rm", "shred", "unlink", "rmdir"):
                deletes = True
    if not deletes:
        return
    starts = []
    for a in args:
        if a.startswith("-") or a in ("(", "!", ")"):
            break
        starts.append(a)
    if not starts:
        starts = ["."]
    for t in _targets(seg, cwd, starts):
        if t.kind == UNRESOLVABLE:
            v.ask("HK-03", "find -delete start path '%s' cannot be resolved statically" % t.raw)
        elif t.kind == OUTSIDE:
            if C.is_root_or_parent(t.raw, cwd):
                v.deny("DG-06", "find -delete from '%s' covers the project" % t.raw)
            elif not C.under_tmp(t.raw, cwd):
                v.ask("DG-06", "find -delete outside the project (%s)" % t.raw)
        else:
            rel = t.rel or ""
            if rel in C.PROTECTED_ROOTS or C.covers_tree(rel, C.DENY_TREES) or C.is_mlruns(rel) or C.is_protected_file(rel):
                v.deny("DG-06", "find -delete/-exec rm starting at protected path '%s'" % (rel or "."))
            elif C.is_ephemeral(rel):
                pass
            else:
                v.ask("DG-06", "find -delete under '%s'" % rel)


def _protected_write_target(t) -> str:
    """Classify a write target: 'deny', 'ask', 'unresolvable' or ''."""
    if t.kind == UNRESOLVABLE:
        return "unresolvable"
    if t.kind != INSIDE:
        return ""
    rel = t.rel or ""
    if C.is_deny_file(rel):
        return "deny"
    if C.is_protected_file(rel):
        return "ask"
    return ""


def check_truncate_shred_dd(seg: Segment, cwd: str, v: Verdict) -> None:
    head = seg.argv0
    if head == "dd":
        toks = [a[3:] for a in seg.args() if a.startswith("of=")]
    else:
        args = seg.args()
        toks = []
        skip = False
        for a in args:
            if skip:
                skip = False
                continue
            if a in ("-s", "--size", "-n", "--iterations", "--reference"):
                skip = True
                continue
            if a.startswith("-"):
                continue
            toks.append(a)
    for t in _targets(seg, cwd, toks):
        if t.kind == UNRESOLVABLE:
            v.ask("HK-03", "%s target '%s' cannot be resolved statically" % (head, t.raw))
        elif t.kind == INSIDE:
            rel = t.rel or ""
            if C.is_deny_file(rel) or C.is_protected_file(rel) or C.under_tree(rel, C.DENY_TREES) or C.is_mlruns(rel):
                v.deny("DG-06", "%s destroys protected file '%s'" % (head, rel))


def check_mlflow(seg: Segment, cwd: str, v: Verdict) -> None:
    args = [a for a in seg.args() if not a.startswith("-")]
    joined = " ".join(args[:2])
    if args and args[0] == "gc":
        v.deny("DG-07", "mlflow gc permanently deletes runs (section 35: failed runs are kept)")
    elif joined in ("experiments delete", "runs delete"):
        v.deny("DG-07", "mlflow %s deletes tracked runs (section 35)" % joined)


def check_sqlite(seg: Segment, cwd: str, v: Verdict) -> None:
    if not any(a.endswith("mlruns.db") or "mlruns" in a and a.endswith(".db") for a in seg.args()):
        return
    if any(re.search(r"\b(DELETE|DROP|UPDATE)\b", a, re.IGNORECASE) for a in seg.args()):
        v.deny("DG-07", "sqlite3 mutation of the MLflow store (section 35)")


#: Substrings that name the full-run approval signing key (ADR-011). Anything that can read
#: this file can mint an approval for every experiment, which is the one thing the approval
#: gate exists to keep in a person's hands.
APPROVAL_KEY_MARKERS = ("approval_key", "PAD_APPROVAL_KEY_FILE")


def check_approval_key(seg: Segment, cwd: str, v: Verdict) -> None:
    """Deny any command that touches the approval signing key, whatever it means to do with it.

    Read, copy, print and overwrite are all equally disqualifying: the key's whole purpose is
    that a full run needs a person, and a process that can read it does not need one.
    """
    haystack = " ".join(seg.argv) + " " + " ".join(seg.env_names) + " " + " ".join(seg.redirects)
    for marker in APPROVAL_KEY_MARKERS:
        if marker in haystack:
            v.deny(
                "DG-15",
                "the full-run approval signing key belongs to the human only (ADR-011); "
                "Claude never reads, copies or writes it",
            )
            return


def check_python(seg: Segment, cwd: str, v: Verdict) -> None:
    scripts = _python_script_tokens(seg)
    if "approve_full_run.py" in scripts:
        v.deny("DG-12", "scripts/approve_full_run.py is run by the human in their own terminal, never by Claude")
    src = _python_c_source(seg)
    if src is None:
        return
    if re.search(r"delete_run|delete_experiment|delete_registered_model", src):
        v.deny("DG-07", "python -c deletes MLflow runs/experiments (section 35)")
    for m in re.finditer(r"""open\(\s*['"]([^'"]+)['"]\s*,\s*['"]([wa][^'"]*)['"]""", src):
        t = C.classify_target(m.group(1), cwd, seg)
        cls = _protected_write_target(t)
        if cls == "deny":
            v.deny("DG-12", "python -c writes deny-listed file '%s'" % t.rel)
        elif cls == "ask":
            v.ask("DG-12", "python -c writes protected file '%s'" % t.rel)
        elif cls == "unresolvable":
            v.ask("HK-03", "python -c write target '%s' cannot be resolved statically" % t.raw)
    if re.search(r"requests\.(post|put)|boto3|upload_file|upload_folder|HfApi|storage\.Client", src):
        v.ask("DG-08", "python -c performs a network upload (sections 22/34)")
    if re.search(r"shutil\.rmtree|os\.remove|os\.unlink|\.unlink\(|rmdir", src):
        for m in re.finditer(r"""['"]([^'"]+)['"]""", src):
            t = C.classify_target(m.group(1), cwd, seg)
            if t.kind == INSIDE:
                rel = t.rel or ""
                if rel in C.PROTECTED_ROOTS or C.covers_tree(rel, C.DENY_TREES) or C.is_mlruns(rel) or C.is_protected_file(rel) or C.is_deny_file(rel):
                    v.deny("DG-01", "python -c deletes protected path '%s'" % (rel or "."))


def _upload_src_protected(t) -> bool:
    if t.kind != INSIDE:
        return False
    rel = t.rel or ""
    return bool(C.covers_tree(rel, C.UPLOAD_PROTECTED)) or C.is_mlruns(rel)


def _apply_upload(v: Verdict, tool: str, srcs, dst: str, cwd: str, seg: Segment, public: bool = False) -> None:
    public = public or (dst is not None and C.is_public_hub(dst))
    unresolved = []
    protected = []
    for t in _targets(seg, cwd, srcs):
        if t.kind == UNRESOLVABLE:
            unresolved.append(t.raw)
        elif _upload_src_protected(t):
            protected.append(t.rel or ".")
    if protected:
        if public:
            v.deny("DG-08", "%s uploads protected data (%s) to a public hub (section 34)" % (tool, ", ".join(protected)))
        else:
            v.ask("DG-08", "%s uploads protected data (%s) to a remote (sections 22/34: license/PII policy first)" % (tool, ", ".join(protected)))
    elif unresolved:
        v.ask("HK-03", "%s source '%s' cannot be resolved statically" % (tool, unresolved[0]))


def check_upload(seg: Segment, cwd: str, v: Verdict) -> None:
    head = seg.argv0
    args = seg.args()
    if "--dry-run" in args or "-n" in args or "--dryrun" in args:
        return
    pos = [a for a in args if not a.startswith("-")]
    if head in ("scp", "rsync"):
        # drop option values (-i key, -P port, -o opt, -e ssh)
        cleaned = []
        skip = False
        for a in args:
            if skip:
                skip = False
                continue
            if a in ("-i", "-P", "-o", "-e", "-F", "-J", "-l", "-S", "--rsh", "--exclude", "--include", "--files-from"):
                skip = True
                continue
            if a.startswith("-"):
                continue
            cleaned.append(a)
        if len(cleaned) < 2:
            return
        dst = cleaned[-1]
        srcs = cleaned[:-1]
        if C.is_remote(dst):
            _apply_upload(v, head, srcs, dst, cwd, seg)
        elif not any(C.is_remote(s) for s in srcs) and head == "rsync":
            _check_local_copy(seg, cwd, v, srcs, dst)
        return
    if head == "sftp":
        _apply_upload(v, head, pos, "remote:", cwd, seg)
        return
    if head == "aws":
        if len(pos) >= 4 and pos[0] == "s3" and pos[1] in ("cp", "sync", "mv"):
            src, dst = pos[2], pos[3]
            if C.is_remote(dst) and not C.is_remote(src):
                _apply_upload(v, "aws s3 %s" % pos[1], [src], dst, cwd, seg)
        elif len(pos) >= 2 and pos[0] == "s3api" and pos[1] == "put-object" and "--body" in args:
            body = args[args.index("--body") + 1] if args.index("--body") + 1 < len(args) else None
            if body:
                _apply_upload(v, "aws s3api put-object", [body], "s3://", cwd, seg)
        return
    if head in ("gsutil", "rclone", "s3cmd", "azcopy", "mc"):
        verbs = {"cp", "rsync", "mv", "sync", "copy", "move", "copyto", "moveto", "put", "mirror"}
        idx = next((i for i, a in enumerate(pos) if a in verbs), None)
        if idx is None or len(pos) < idx + 3:
            return
        src, dst = pos[idx + 1 : -1], pos[-1]
        if head == "mc" or C.is_remote(dst) or ":" in dst:
            _apply_upload(v, "%s %s" % (head, pos[idx]), src, dst, cwd, seg)
        return
    if head == "gcloud":
        if len(pos) >= 4 and pos[0] == "storage" and pos[1] in ("cp", "rsync", "mv"):
            src, dst = pos[2:-1], pos[-1]
            if C.is_remote(dst):
                _apply_upload(v, "gcloud storage %s" % pos[1], src, dst, cwd, seg)
        return
    if head == "az":
        if pos and pos[0] == "storage":
            files = []
            for flag in ("--file", "-f", "--source", "-s"):
                if flag in args and args.index(flag) + 1 < len(args):
                    files.append(args[args.index(flag) + 1])
            if files:
                _apply_upload(v, "az storage", files, "az://", cwd, seg)
        return
    if head == "b2":
        if pos and pos[0] in ("upload-file", "upload_file", "sync") and len(pos) >= 3:
            _apply_upload(v, "b2 %s" % pos[0], [pos[2] if pos[0] != "sync" else pos[1]], "b2://", cwd, seg)
        return
    if head == "curl":
        files = []
        url = next((a for a in pos if "://" in a), None)
        for i, a in enumerate(args):
            if a in ("-T", "--upload-file") and i + 1 < len(args):
                files.append(args[i + 1])
            elif a.startswith("--upload-file="):
                files.append(a.split("=", 1)[1])
            elif a in ("-F", "--form", "--data-binary", "-d", "--data", "--data-raw") and i + 1 < len(args):
                val = args[i + 1]
                if "@" in val and a != "--data-raw":
                    files.append(val.split("@", 1)[1].split(";")[0])
        if files:
            _apply_upload(v, "curl upload", files, url or "remote://", cwd, seg)
        return
    if head == "wget":
        files = [a.split("=", 1)[1] for a in args if a.startswith("--post-file=")]
        for i, a in enumerate(args):
            if a == "--post-file" and i + 1 < len(args):
                files.append(args[i + 1])
        if files:
            _apply_upload(v, "wget --post-file", files, next((a for a in pos if "://" in a), "remote://"), cwd, seg)
        return
    if head in ("huggingface-cli", "hf"):
        if pos and pos[0] in ("upload", "upload-large-folder"):
            srcs = pos[2:3] if len(pos) >= 3 else ["."]
            _apply_upload(v, "%s upload" % head, srcs, "hf://", cwd, seg, public=True)
            if not any(_upload_src_protected(t) for t in _targets(seg, cwd, srcs)):
                v.ask("DG-08", "%s upload publishes files to huggingface.co (section 34)" % head)
        return
    if head == "gh":
        if len(pos) >= 2 and ((pos[0] == "release" and pos[1] == "upload") or (pos[0] == "gist" and pos[1] == "create")):
            srcs = pos[3:] if pos[0] == "release" else pos[2:]
            _apply_upload(v, "gh %s %s" % (pos[0], pos[1]), srcs, "https://github.com", cwd, seg, public=True)
            if not any(_upload_src_protected(t) for t in _targets(seg, cwd, srcs)):
                v.ask("DG-08", "gh %s %s publishes files publicly (section 34)" % (pos[0], pos[1]))
        return
    if head == "wandb":
        if pos and pos[0] == "sync":
            srcs = pos[1:] or ["."]
            _apply_upload(v, "wandb sync", srcs, "wandb.ai", cwd, seg, public=True)
            if not any(_upload_src_protected(t) for t in _targets(seg, cwd, srcs)):
                v.ask("DG-08", "wandb sync uploads run data to wandb.ai (section 34)")
        return


def _check_local_copy(seg: Segment, cwd: str, v: Verdict, srcs, dst: str) -> None:
    t = C.classify_target(dst, cwd, seg)
    cls = _protected_write_target(t)
    tool = seg.argv0
    if cls == "deny":
        v.deny("DG-12", "%s overwrites deny-listed path '%s'" % (tool, t.rel))
    elif cls == "ask":
        v.ask("DG-12", "%s overwrites protected path '%s' (use the Edit tool so the diff is reviewed)" % (tool, t.rel))
    elif cls == "unresolvable":
        v.ask("HK-03", "%s destination '%s' cannot be resolved statically" % (tool, t.raw))


def check_bash_edits(seg: Segment, cwd: str, v: Verdict) -> None:
    head = seg.argv0
    targets = []
    if head == "sed":
        args = seg.args()
        inplace = any(a == "-i" or a.startswith("-i.") or a == "--in-place" or a.startswith("--in-place=") or (a.startswith("-") and not a.startswith("--") and "i" in a[1:] and "-e" != a) for a in args)
        if inplace:
            files = []
            skip = False
            saw_script = "-e" in args or "-f" in args or any(a.startswith("--expression") for a in args)
            for a in args:
                if skip:
                    skip = False
                    continue
                if a in ("-e", "-f", "--expression", "--file"):
                    skip = True
                    continue
                if a.startswith("-"):
                    continue
                if not saw_script:
                    saw_script = True  # first positional is the script
                    continue
                files.append(a)
            targets.extend(files)
    elif head == "tee":
        targets.extend(seg.positional())
    elif head in ("cp", "mv", "install"):
        pos = seg.positional()
        if len(pos) >= 2:
            targets.append(pos[-1])
    elif head == "ln":
        pos = seg.positional()
        if len(pos) >= 2:
            targets.append(pos[-1])
    for tok in seg.redirects:
        targets.append(tok)
    for t in _targets(seg, cwd, targets):
        cls = _protected_write_target(t)
        if cls == "deny":
            v.deny("DG-12", "Bash write to deny-listed path '%s' (only scripts/the human write it)" % t.rel)
        elif cls == "ask":
            v.ask("DG-12", "Bash write to protected path '%s' (use the Edit tool so the diff is reviewed)" % t.rel)
        elif cls == "unresolvable" and head in ("sed", "tee", "cp", "mv", "install"):
            v.ask("HK-03", "%s target '%s' cannot be resolved statically" % (head, t.raw))


def check_reads(seg: Segment, cwd: str, v: Verdict) -> None:
    for t in _targets(seg, cwd):
        if t.kind == INSIDE and C.under_tree(t.rel, ("data/raw", "data/processed")):
            v.ask("DG-13", "%s of '%s' puts raw biometric data into the context (section 34); use manifests/scripts for statistics" % (seg.argv0, t.rel))
            return


def check_pipelines(segments, cwd: str, v: Verdict) -> None:
    for i, seg in enumerate(segments):
        if not seg.argv:
            continue
        head = seg.argv0
        # DG-14: curl|wget ... | sh
        if head in ("curl", "wget"):
            j = i + 1
            while j < len(segments) and segments[j].sep in ("|", "|&"):
                if segments[j].argv and segments[j].argv0 in SHELL_SINKS:
                    v.ask("DG-14", "%s output piped into %s (remote code execution)" % (head, segments[j].argv0))
                    break
                j += 1
        # DG-09: cat data/raw/... | ssh host
        if head in PIPE_READERS:
            toks = list(seg.positional())
            if head == "dd":
                toks = [a[3:] for a in seg.args() if a.startswith("if=")]
            reads_protected = False
            for t in _targets(seg, cwd, toks):
                if t.kind == INSIDE and (C.covers_tree(t.rel, C.UPLOAD_PROTECTED) or C.is_mlruns(t.rel)):
                    reads_protected = True
            if reads_protected:
                j = i + 1
                while j < len(segments) and segments[j].sep in ("|", "|&"):
                    if segments[j].argv and segments[j].argv0 in NET_SINKS:
                        v.ask("DG-09", "protected data streamed from %s into %s (sections 22/34)" % (head, segments[j].argv0))
                        break
                    j += 1


def check_segment(seg: Segment, cwd: str, v: Verdict) -> None:
    if set(seg.env_names) & C.GUARDED_ENV_NAMES:
        v.ask("HK-04", "segment redefines %s (harness state must come from files, not env)" % ", ".join(sorted(set(seg.env_names) & C.GUARDED_ENV_NAMES)))
    if not seg.argv:
        check_bash_edits(seg, cwd, v)
        return
    head = seg.argv0
    if head == "export":
        names = [a.split("=", 1)[0] for a in seg.args() if "=" in a]
        if set(names) & C.GUARDED_ENV_NAMES:
            v.ask("HK-04", "export of %s (harness state must come from files, not env)" % ", ".join(sorted(set(names) & C.GUARDED_ENV_NAMES)))
    if seg.indirect and head in DANGEROUS_FAMILIES:
        v.ask("HK-02", "%s reached through xargs/eval nesting: targets cannot be inspected" % head)
    if head in ("source", "."):
        pos = seg.positional()
        if pos:
            t = C.classify_target(pos[0], cwd, seg)
            if t.kind == INSIDE and not (t.rel or "").startswith(".venv/"):
                v.ask("HK-02", "source of '%s' runs commands the hook cannot inspect" % t.rel)
    if head in ("rm", "unlink", "rmdir"):
        check_rm(seg, cwd, v)
    elif head == "git":
        check_git(seg, cwd, v)
    elif head == "dvc":
        check_dvc(seg, cwd, v)
    elif head == "find":
        check_find(seg, cwd, v)
    elif head in ("truncate", "shred", "dd"):
        check_truncate_shred_dd(seg, cwd, v)
    elif head == "mlflow":
        check_mlflow(seg, cwd, v)
    elif head == "sqlite3":
        check_sqlite(seg, cwd, v)
    elif head.startswith("python") or head == "uv":
        check_python(seg, cwd, v)
    elif head in UPLOAD_TOOLS:
        check_upload(seg, cwd, v)
    elif head in READ_TOOLS:
        check_reads(seg, cwd, v)
    # Not tied to a command name: reading the key with cat, copying it with cp, printing it
    # with echo and overwriting it with a redirect are all the same disclosure.
    check_approval_key(seg, cwd, v)
    if head in ("sed", "tee", "cp", "mv", "install", "ln") or seg.redirects:
        check_bash_edits(seg, cwd, v)


def evaluate(command: str, cwd: str) -> Verdict:
    v = Verdict()
    parsed = C.split_commands(command)
    if parsed.lex_failed:
        heads = {s.argv0 for s in parsed.segments if s.argv}
        if heads & DANGEROUS_FAMILIES:
            v.ask("HK-03", "command could not be tokenized (unbalanced quotes) and contains %s" % ", ".join(sorted(heads & DANGEROUS_FAMILIES)))
    for seg in parsed.segments:
        check_segment(seg, cwd, v)
    check_pipelines(parsed.segments, cwd, v)
    return v


def main() -> None:
    data = C.read_input()
    if data is None:
        C.ask("HK-00 hook stdin was not valid JSON; refusing to guess")
    if data.get("tool_name") not in (None, "Bash"):
        C.no_decision()
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        C.ask("HK-00 tool_input missing or not an object")
    command = tool_input.get("command")
    if not isinstance(command, str):
        C.ask("HK-00 tool_input.command missing")
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    evaluate(command, cwd).emit()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: B036 - fail-safe by design (exit 1 would fail open)
        try:
            C.ask("HK-99 hook internal error: %s: %s" % (type(exc).__name__, str(exc)[:200]))
        except SystemExit:
            raise
        except BaseException:  # noqa: B036
            sys.stdout.write('{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"HK-99 hook internal error"}}\n')
            sys.exit(0)
