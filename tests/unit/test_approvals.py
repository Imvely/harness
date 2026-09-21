"""Human approval for a full run, in both forms (ADR-005, ADR-011).

The property under test throughout is the same: an approval covers exactly one scientific
configuration, and anything else — a different experiment, an edited protocol, a forged or
stale token — reads as "not approved" rather than as an error the gate might mishandle.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from pad_research.experiments.approvals import (
    TOKEN_ENV_VAR,
    ApprovalKeyMissingError,
    ApprovalToken,
    create_key,
    mint_pasteable,
    read_token,
    resolve_approval,
    token_path,
    verify_pasteable,
    write_token,
)

SCIENCE = "a" * 64
OTHER_SCIENCE = "b" * 64
GIT_SHA = "c" * 40


@pytest.fixture
def key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PAD_APPROVAL_KEY_FILE", str(tmp_path / "key"))
    return create_key()


# --- file form -----------------------------------------------------------------------------


def test_a_written_token_reads_back(tmp_path: Path) -> None:
    path = write_token("exp_a", SCIENCE, GIT_SHA, tmp_path)
    assert path == token_path("exp_a", SCIENCE, tmp_path)
    token = read_token("exp_a", SCIENCE, tmp_path)
    assert token is not None
    assert token.science_hash == SCIENCE
    assert token.git_sha == GIT_SHA


def test_a_token_for_another_experiment_does_not_apply(tmp_path: Path) -> None:
    write_token("exp_a", SCIENCE, GIT_SHA, tmp_path)
    assert read_token("exp_b", SCIENCE, tmp_path) is None


def test_a_token_whose_contents_were_edited_is_refused(tmp_path: Path) -> None:
    # Renaming the file is not enough to move an approval to another experiment.
    write_token("exp_a", SCIENCE, GIT_SHA, tmp_path)
    path = token_path("exp_a", SCIENCE, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["science_hash"] = OTHER_SCIENCE
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert read_token("exp_a", SCIENCE, tmp_path) is None


def test_file_approvals_now_expire(tmp_path: Path) -> None:
    """The weakness the paste form was asked for: an approval from March still worked in June.

    A file written with a lifetime stops applying on its own, so an old approval cannot quietly
    authorise a rerun months later.
    """
    write_token("exp_a", SCIENCE, GIT_SHA, tmp_path, ttl_hours=-1)
    assert read_token("exp_a", SCIENCE, tmp_path) is None
    write_token("exp_a", SCIENCE, GIT_SHA, tmp_path, ttl_hours=1)
    assert read_token("exp_a", SCIENCE, tmp_path) is not None


def test_a_token_written_before_expiry_existed_still_works(tmp_path: Path) -> None:
    # Backwards compatibility: expires_at is absent in tokens written before ADR-011.
    path = token_path("exp_a", SCIENCE, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "experiment_id": "exp_a",
                "science_hash": SCIENCE,
                "git_sha": GIT_SHA,
                "approved_at": "2026-01-01T00:00:00+00:00",
                "approved_by": "someone",
            }
        ),
        encoding="utf-8",
    )
    assert read_token("exp_a", SCIENCE, tmp_path) is not None


def test_an_unparseable_deadline_counts_as_passed_not_as_absent() -> None:
    # Failing open here would turn a corrupted file into a permanent approval.
    token = ApprovalToken(
        experiment_id="exp_a",
        science_hash=SCIENCE,
        git_sha=None,
        approved_at="2026-01-01T00:00:00+00:00",
        approved_by="someone",
        expires_at="not-a-date",
    )
    assert token.expired()


# --- paste form ----------------------------------------------------------------------------


def test_a_minted_token_verifies_for_its_own_experiment(key: Path) -> None:
    token = mint_pasteable("exp_a", SCIENCE, GIT_SHA)
    verified = verify_pasteable(token, "exp_a", SCIENCE)
    assert verified is not None
    assert verified.git_sha == GIT_SHA
    assert verified.expires_at is not None


def test_a_token_does_not_carry_over_to_another_experiment(key: Path) -> None:
    # The binding that matters: approving one experiment must not approve the next one.
    token = mint_pasteable("exp_a", SCIENCE, GIT_SHA)
    assert verify_pasteable(token, "exp_b", SCIENCE) is None


def test_editing_the_science_configuration_voids_the_token(key: Path) -> None:
    # science_hash changes when the protocol, model or seed changes, so an approval cannot
    # survive an edit to the thing that was approved.
    token = mint_pasteable("exp_a", SCIENCE, GIT_SHA)
    assert verify_pasteable(token, "exp_a", OTHER_SCIENCE) is None


def test_a_tampered_payload_fails_its_signature(key: Path) -> None:
    import base64

    prefix, body, signature = mint_pasteable("exp_a", SCIENCE, GIT_SHA).split(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload["experiment_id"] = "exp_b"
    forged = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    assert verify_pasteable(f"{prefix}.{forged}.{signature}", "exp_b", SCIENCE) is None


def test_a_token_signed_with_another_key_is_refused(
    tmp_path: Path, key: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = mint_pasteable("exp_a", SCIENCE, GIT_SHA)
    monkeypatch.setenv("PAD_APPROVAL_KEY_FILE", str(tmp_path / "other_key"))
    create_key()
    assert verify_pasteable(token, "exp_a", SCIENCE) is None


def test_an_expired_token_stops_approving(key: Path) -> None:
    token = mint_pasteable("exp_a", SCIENCE, GIT_SHA, ttl_minutes=-1)
    assert verify_pasteable(token, "exp_a", SCIENCE) is None


def test_garbage_reads_as_no_approval_rather_than_raising(key: Path) -> None:
    # This runs inside the gate, where the answer for anything unusable is "not approved".
    for text in ["", "   ", "nonsense", "pad1.only-two", "pad2.a.b", "pad1.!!!.!!!"]:
        assert verify_pasteable(text, "exp_a", SCIENCE) is None


def test_minting_without_a_key_says_how_to_make_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAD_APPROVAL_KEY_FILE", str(tmp_path / "absent"))
    with pytest.raises(ApprovalKeyMissingError, match="--init-key"):
        mint_pasteable("exp_a", SCIENCE, GIT_SHA)


def test_the_signing_key_is_readable_only_by_its_owner(key: Path) -> None:
    # Anyone who can read the key can mint approvals for every experiment.
    assert key.stat().st_mode & 0o077 == 0


def test_creating_a_key_twice_keeps_the_first_one(key: Path) -> None:
    # Overwriting would silently invalidate tokens already pasted into running shells.
    original = key.read_text(encoding="utf-8")
    assert create_key().read_text(encoding="utf-8") == original


# --- either form ---------------------------------------------------------------------------


def test_resolution_reports_which_route_approved_the_run(tmp_path: Path, key: Path) -> None:
    # The run records this as approved_by, so a reader can tell a standing file approval from
    # a token someone pasted for this launch.
    token = mint_pasteable("exp_a", SCIENCE, GIT_SHA)
    resolved = resolve_approval("exp_a", SCIENCE, tmp_path, env={TOKEN_ENV_VAR: token})
    assert resolved is not None and resolved[1] == "paste"

    write_token("exp_a", SCIENCE, GIT_SHA, tmp_path)
    resolved = resolve_approval("exp_a", SCIENCE, tmp_path, env={TOKEN_ENV_VAR: token})
    assert resolved is not None and resolved[1] == "file"


def test_no_file_and_no_variable_means_no_approval(tmp_path: Path, key: Path) -> None:
    assert resolve_approval("exp_a", SCIENCE, tmp_path, env={}) is None


def test_a_stale_pasted_variable_does_not_approve_a_new_experiment(
    tmp_path: Path, key: Path
) -> None:
    # A token left exported in a long-lived shell must not approve whatever runs next.
    token = mint_pasteable("exp_a", SCIENCE, GIT_SHA)
    assert resolve_approval("exp_b", SCIENCE, tmp_path, env={TOKEN_ENV_VAR: token}) is None


def test_the_deadline_is_timezone_aware() -> None:
    # A naive timestamp compared against an aware "now" raises TypeError, which inside the
    # gate would be an approval failing for the wrong reason.
    token = ApprovalToken(
        experiment_id="exp_a",
        science_hash=SCIENCE,
        git_sha=None,
        approved_at="2026-01-01T00:00:00",
        approved_by="someone",
        expires_at="2099-01-01T00:00:00",  # no offset
    )
    assert token.expired(now=_dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)) is False
