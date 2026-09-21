"""Human approval for a full run: a file on disk, or a string the person pastes (ADR-011).

Both forms answer the same question — *did a person look at this experiment and agree to spend
the GPU on it?* — and both are bound to ``science_hash``, so an approval covers one scientific
configuration and nothing else. Editing the protocol, the model or the seed changes the hash
and voids the approval automatically. Neither form can be produced by Claude Code, which is
denied the script, the approvals directory and the signing key (``permissions.deny`` plus the
``guard_destructive`` hook).

**File form** (ADR-005, still the default). ``scripts/approve_full_run.py`` writes
``experiments/approvals/<exp_id>.<science12>.json`` in the person's own terminal. The launch
hook turns ``ask`` into ``allow`` when a matching token exists.

**Paste form** (ADR-011). ``--print`` mints a signed one-line string instead, which the person
pastes into the launching shell as ``PAD_APPROVAL_TOKEN``. It exists because the file form has
no expiry: a token written in March still approves the same experiment in June, and nothing on
screen says so. A pasted token carries a deadline and disappears when the shell closes.

What the paste form does *not* do is put the approval beyond Claude's reach. Claude runs as the
same operating-system user here, so both forms rest on policy rather than on file permissions,
and a token pasted into a command Claude launches is visible to Claude for as long as it is
valid. Its value is the deadline and the narrow binding (one experiment, one science_hash, one
commit), not secrecy — see ADR-011 "Risks".
"""

from __future__ import annotations

import base64
import datetime as _dt
import getpass
import hmac
import json
import os
import secrets
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pad_research import paths

#: Environment variable the launching shell carries a pasted token in.
TOKEN_ENV_VAR = "PAD_APPROVAL_TOKEN"

#: Overrides the signing key location, for tests and for a shared lab account.
KEY_ENV_VAR = "PAD_APPROVAL_KEY_FILE"

#: Prefix, so a mistyped paste fails with "not an approval token" and not a decode traceback.
_PREFIX = "pad1"

#: Default lifetime of a pasted token. Long enough to freeze, smoke and launch; short enough
#: that a token left in a scrollback is not an open approval next week.
DEFAULT_TTL_MINUTES = 120

#: Default lifetime of a file token. It had none, which is the weakness the paste form was
#: asked for; a day covers the normal "approve now, launch after the queue clears".
DEFAULT_FILE_TTL_HOURS = 24


def _now() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.UTC)


def _iso(moment: _dt.datetime) -> str:
    return moment.isoformat(timespec="seconds")


class ApprovalToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    science_hash: str
    git_sha: str | None
    approved_at: str
    approved_by: str
    #: ISO timestamp after which this approval is refused. ``None`` means it never expires,
    #: which is how tokens written before ADR-011 behave.
    expires_at: str | None = None

    def expired(self, now: _dt.datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        try:
            deadline = _dt.datetime.fromisoformat(self.expires_at)
        except ValueError:
            return True  # an unparseable deadline is treated as passed, never as absent
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=_dt.UTC)
        return (now or _now()) >= deadline


# --- file form -----------------------------------------------------------------------------


def token_path(experiment_id: str, science_hash: str, approvals_dir: Path | None = None) -> Path:
    return (approvals_dir or paths.approvals_dir()) / f"{experiment_id}.{science_hash[:12]}.json"


def read_token(
    experiment_id: str, science_hash: str, approvals_dir: Path | None = None
) -> ApprovalToken | None:
    path = token_path(experiment_id, science_hash, approvals_dir)
    if not path.is_file():
        return None
    try:
        tok = ApprovalToken.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if tok.experiment_id != experiment_id or tok.science_hash != science_hash:
        return None
    if tok.expired():
        return None
    return tok


def write_token(
    experiment_id: str,
    science_hash: str,
    git_sha: str | None,
    approvals_dir: Path | None = None,
    *,
    ttl_hours: float | None = DEFAULT_FILE_TTL_HOURS,
) -> Path:
    path = token_path(experiment_id, science_hash, approvals_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _now()
    tok = ApprovalToken(
        experiment_id=experiment_id,
        science_hash=science_hash,
        git_sha=git_sha,
        approved_at=_iso(now),
        approved_by=getpass.getuser(),
        expires_at=(_iso(now + _dt.timedelta(hours=ttl_hours)) if ttl_hours is not None else None),
    )
    path.write_text(tok.model_dump_json(indent=1) + "\n", encoding="utf-8")
    return path


# --- paste form ----------------------------------------------------------------------------


class ApprovalKeyMissingError(RuntimeError):
    """No signing key exists yet; the person has to create one in their own terminal."""


def key_path() -> Path:
    override = os.environ.get(KEY_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    # Outside the repository on purpose: nothing in a git checkout should be able to sign an
    # approval, including a worktree Claude can write to.
    return Path.home() / ".config" / "pad_research" / "approval_key"


def create_key(*, overwrite: bool = False) -> Path:
    """Create the signing key, readable only by its owner."""
    path = key_path()
    if path.exists() and not overwrite:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written with 0600 from the start rather than chmod-ed afterwards, so the key is never
    # briefly world-readable.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(secrets.token_hex(32))
    return path


def _read_key() -> bytes:
    path = key_path()
    try:
        material = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ApprovalKeyMissingError(
            "no approval signing key; create one in your own terminal with "
            "`python scripts/approve_full_run.py --init-key`"
        ) from exc
    if not material:
        raise ApprovalKeyMissingError("the approval signing key file is empty")
    return material.encode("utf-8")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes, key: bytes) -> str:
    return _b64(hmac.new(key, payload, sha256).digest())


def mint_pasteable(
    experiment_id: str,
    science_hash: str,
    git_sha: str | None,
    *,
    ttl_minutes: float = DEFAULT_TTL_MINUTES,
) -> str:
    """Return a signed one-line approval for the person to paste into their launching shell."""
    key = _read_key()
    now = _now()
    payload = {
        "experiment_id": experiment_id,
        "science_hash": science_hash,
        "git_sha": git_sha,
        "approved_at": _iso(now),
        "approved_by": getpass.getuser(),
        "expires_at": _iso(now + _dt.timedelta(minutes=ttl_minutes)),
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{_PREFIX}.{_b64(body)}.{_sign(body, key)}"


def verify_pasteable(token: str, experiment_id: str, science_hash: str) -> ApprovalToken | None:
    """Return the approval a pasted token carries, or ``None`` if it does not apply here.

    Every rejection returns ``None`` rather than raising: this runs inside the gate, where the
    answer is "there is no approval" regardless of whether the token was forged, stale, for a
    different experiment, or simply mistyped.
    """
    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] != _PREFIX:
        return None
    try:
        body = _unb64(parts[1])
        key = _read_key()
    except (ValueError, ApprovalKeyMissingError):
        return None
    # compare_digest, so a wrong signature cannot be narrowed down by timing the rejection.
    if not hmac.compare_digest(_sign(body, key), parts[2]):
        return None
    try:
        parsed = ApprovalToken.model_validate_json(body)
    except ValueError:
        return None
    if parsed.experiment_id != experiment_id or parsed.science_hash != science_hash:
        return None
    if parsed.expired():
        return None
    return parsed


# --- either form ---------------------------------------------------------------------------


def resolve_approval(
    experiment_id: str,
    science_hash: str,
    approvals_dir: Path | None = None,
    *,
    env: dict[str, str] | None = None,
) -> tuple[ApprovalToken, str] | None:
    """Return ``(token, source)`` from whichever form approved this run, or ``None``.

    The file is checked first so that an experiment already approved on disk does not depend on
    a variable being exported; ``source`` is ``"file"`` or ``"paste"`` and is recorded on the
    run as ``approved_by`` so a reader can tell which route was used.
    """
    on_disk = read_token(experiment_id, science_hash, approvals_dir)
    if on_disk is not None:
        return on_disk, "file"
    pasted = (env if env is not None else os.environ).get(TOKEN_ENV_VAR, "").strip()
    if not pasted:
        return None
    verified = verify_pasteable(pasted, experiment_id, science_hash)
    return (verified, "paste") if verified is not None else None
