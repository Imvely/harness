"""The LMDB writer's refusals, and the size it reserves. No store is opened here."""

from __future__ import annotations

from pathlib import Path

import pytest

from pad_research.data.storage.lmdb_writer import (
    MIN_MAP_SIZE,
    LmdbSink,
    LmdbWriteError,
    map_size_for,
)


def test_the_reserved_map_leaves_room_for_keys_and_index_pages() -> None:
    assert map_size_for(1_000_000_000) == 1_250_000_000
    # A tiny build still gets a usable map: LMDB fails outright when the map cannot hold a page.
    assert map_size_for(10) == MIN_MAP_SIZE
    with pytest.raises(ValueError, match="negative"):
        map_size_for(-1)


def test_an_existing_path_is_refused_so_two_builds_cannot_mix(tmp_path: Path) -> None:
    """A second build into one store would blend two selection rules with no way to separate."""
    existing = tmp_path / "aihub115.lmdb"
    existing.mkdir()
    with pytest.raises(LmdbWriteError, match="already exists"):
        LmdbSink(existing, map_size=MIN_MAP_SIZE)


def test_a_batch_size_below_one_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        LmdbSink(tmp_path / "new.lmdb", map_size=MIN_MAP_SIZE, batch_size=0)


def test_nothing_is_opened_until_the_first_write(tmp_path: Path) -> None:
    sink = LmdbSink(tmp_path / "new.lmdb", map_size=MIN_MAP_SIZE)
    assert not (tmp_path / "new.lmdb").exists()
    assert sink.n_written == 0
    # Closing a sink that never wrote is a no-op, not an error, so a dry run can use one.
    sink.close()
    assert not (tmp_path / "new.lmdb").exists()
