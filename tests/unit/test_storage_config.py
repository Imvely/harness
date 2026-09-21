"""The storage config block: a discriminated union, and no location written down."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import TypeAdapter, ValidationError

from pad_research.data.storage.config import (
    LmdbStorageConfig,
    LocalStorageConfig,
    SftpStorageConfig,
    StorageConfig,
)

_STORAGE = TypeAdapter(StorageConfig)
CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "storage"


def test_the_kind_selects_the_model() -> None:
    assert isinstance(_STORAGE.validate_python({"kind": "lmdb"}), LmdbStorageConfig)
    assert isinstance(_STORAGE.validate_python({"kind": "local"}), LocalStorageConfig)
    assert isinstance(_STORAGE.validate_python({"kind": "sftp"}), SftpStorageConfig)


def test_an_unknown_backend_fails_during_composition_not_at_the_first_batch() -> None:
    with pytest.raises(ValidationError):
        _STORAGE.validate_python({"kind": "s3"})


def test_a_misspelled_option_is_refused_rather_than_ignored() -> None:
    # extra="forbid": a silently ignored `key_preifx` would look like a store whose keys do
    # not match, and cost an afternoon.
    with pytest.raises(ValidationError):
        _STORAGE.validate_python({"kind": "lmdb", "key_preifx": "x/"})


@pytest.mark.parametrize("name", ["local", "lmdb", "sftp"])
def test_every_shipped_config_validates(name: str) -> None:
    config = _STORAGE.validate_python(
        yaml.safe_load((CONFIG_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    )
    assert config.kind == name


@pytest.mark.parametrize("name", ["local", "lmdb", "sftp"])
def test_no_shipped_config_contains_a_location(name: str) -> None:
    """configs/ is committed, and so is the frozen resolved spec.

    A literal ``/mnt/nas/faces`` or ``gpu03.lab.internal`` in either is a machine path or a
    hostname in a public git history (contract section 34), and it is also what makes a spec
    unusable on the next person's machine. Locations are variable NAMES; values live in the
    shell.
    """
    raw = yaml.safe_load((CONFIG_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    for key, value in raw.items():
        if not isinstance(value, str):
            continue
        assert not value.startswith(("/", "~", "\\")), f"{key} looks like a path"
        assert "://" not in value, f"{key} looks like a URI"
        assert "@" not in value, f"{key} looks like a credential"


def test_env_vars_lists_what_the_user_must_export() -> None:
    # The UI and the diagnosis CLI both print this list; it has to come from the config
    # itself, or it drifts the first time a field is renamed.
    assert LocalStorageConfig().env_vars() == ["PAD_DATA_ROOT"]
    assert LmdbStorageConfig(kind="lmdb").env_vars() == ["PAD_LMDB_PATH"]
    sftp = SftpStorageConfig(kind="sftp").env_vars()
    assert set(sftp) == {"PAD_SFTP_HOST", "PAD_SFTP_ROOT", "PAD_SFTP_USER"}


def test_optional_variables_are_omitted_when_unset() -> None:
    # An empty password_env_var means key authentication; printing it as something to export
    # would send people looking for a secret they do not need.
    assert "password" not in " ".join(SftpStorageConfig(kind="sftp").env_vars()).lower()
    named = SftpStorageConfig(kind="sftp", password_env_var="MY_PASS").env_vars()
    assert "MY_PASS" in named
