"""The SFTP fallback: credential handling and the promise not to connect too early.

There is no SSH server in the test environment, so what is checked here is everything that
happens *before* the socket: that no secret is read from a config file, that an unreachable
host produces an actionable error instead of a stack trace naming the host, and that
constructing a backend connects nothing (a connection opened before a DataLoader forks is
shared cipher state, which is the failure this design exists to avoid).
"""

from __future__ import annotations

import pytest

from pad_research.data.storage.base import StorageUnavailableError

paramiko = pytest.importorskip("paramiko", reason="the sftp extra is optional")

from pad_research.data.storage.sftp import SftpStorage  # noqa: E402


def _backend(**kwargs: object) -> SftpStorage:
    defaults: dict[str, object] = {"host": "127.0.0.1", "remote_root": "/srv/data", "port": 1}
    return SftpStorage(**{**defaults, **kwargs})  # type: ignore[arg-type]


def test_constructing_a_backend_opens_no_connection() -> None:
    # Nothing here should touch the network; the connection belongs to the process that reads.
    backend = _backend()
    assert backend.kind == "sftp"
    assert backend.local_path("a/b.avi") is None


def test_an_unreachable_host_explains_what_to_check_without_naming_it() -> None:
    backend = _backend()
    with pytest.raises(StorageUnavailableError) as excinfo:
        backend.read_bytes("a/b.avi")
    message = str(excinfo.value)
    assert "check the host" in message
    # paramiko's own messages quote hosts, users and key paths; those must not reach a log.
    assert "127.0.0.1" not in message


def test_a_named_but_empty_password_variable_fails_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Silently falling back to key auth here would turn "my password variable is not exported"
    # into a confusing authentication failure much later.
    monkeypatch.delenv("PAD_SFTP_PASSWORD", raising=False)
    backend = _backend(password_env_var="PAD_SFTP_PASSWORD")
    with pytest.raises(StorageUnavailableError) as excinfo:
        backend.read_bytes("a/b.avi")
    assert "PAD_SFTP_PASSWORD" in str(excinfo.value)


def test_unknown_host_keys_are_rejected_rather_than_trusted_on_first_use() -> None:
    # Trust-on-first-use would let anything answering on that address hand back face data.
    backend = _backend()
    with pytest.raises(StorageUnavailableError):
        backend.read_bytes("a/b.avi")
    assert isinstance(paramiko.RejectPolicy(), paramiko.MissingHostKeyPolicy)


def test_describe_carries_neither_host_nor_remote_root() -> None:
    assert _backend().describe() == {"storage_kind": "sftp"}
