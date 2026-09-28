"""Behaviour every storage backend inherits: ordering, path safety, fork safety."""

from __future__ import annotations

import multiprocessing as mp
import os
import pickle

import pytest

from pad_research.data.storage.base import (
    PerProcessResource,
    StorageError,
    check_relative,
    natural_key,
    sort_children,
)


def test_children_sort_numerically_not_lexicographically() -> None:
    # Lexicographic order puts frame_10 before frame_2 and silently scrambles time, which for
    # a temporal PAD model is a wrong answer rather than a slow one.
    unsorted = ["c/frame_10.png", "c/frame_2.png", "c/frame_1.png"]
    assert sort_children(unsorted) == ["c/frame_1.png", "c/frame_2.png", "c/frame_10.png"]


def test_sorting_compares_only_the_last_segment() -> None:
    # An LMDB key range and a directory listing must agree on order even though one carries
    # the whole prefix on every entry.
    assert sort_children(["a/b/9", "a/b/10"]) == ["a/b/9", "a/b/10"]
    assert natural_key("000002") < natural_key("000010")


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "/absolute/path", "a\\b", "../escape", "ds/../../escape"],
)
def test_relative_paths_that_could_escape_the_root_are_refused(bad: str) -> None:
    with pytest.raises(StorageError):
        check_relative(bad)


def test_ordinary_relative_paths_pass_through() -> None:
    assert check_relative("oulu_npu/train/1_1_01_1.avi") == "oulu_npu/train/1_1_01_1.avi"


# --- PerProcessResource ------------------------------------------------------------------


def test_handle_is_reused_within_one_process() -> None:
    resource: PerProcessResource[object] = PerProcessResource()
    opened: list[int] = []

    def factory() -> object:
        opened.append(1)
        return object()

    first = resource.get(factory)
    assert resource.get(factory) is first
    assert len(opened) == 1


def _child(resource: PerProcessResource[tuple[int, int]], queue: mp.Queue) -> None:  # type: ignore[type-arg]
    handle = resource.get(lambda: (os.getpid(), 1))
    queue.put(handle[0])


def test_a_forked_child_opens_its_own_handle() -> None:
    """The reason this class exists: py-lmdb states an environment must not cross a fork().

    A DataLoader worker is a forked process on Linux. If the child kept using the parent's
    handle, the two would share LMDB reader slots and an SSH cipher state — corruption that
    shows up as wrong pixels, not as an exception.
    """
    context = mp.get_context("fork")
    resource: PerProcessResource[tuple[int, int]] = PerProcessResource()
    parent_handle = resource.get(lambda: (os.getpid(), 1))

    queue: mp.Queue = context.Queue()  # type: ignore[type-arg]
    process = context.Process(target=_child, args=(resource, queue))
    process.start()
    child_pid = queue.get(timeout=30)
    process.join(timeout=30)

    assert child_pid != parent_handle[0]
    # The parent's handle survived: the child must not close what it inherited.
    assert resource.get(lambda: (os.getpid(), 2)) == parent_handle


def test_pickling_drops_the_handle_for_spawned_workers() -> None:
    # DataLoader spawns rather than forks on Windows and macOS, so the dataset (and the backend
    # it holds) is pickled. An open handle is not picklable; a dropped one is reopened on use.
    resource: PerProcessResource[object] = PerProcessResource()
    resource.get(object)
    restored = pickle.loads(pickle.dumps(resource))
    opened: list[int] = []
    restored.get(lambda: opened.append(1))
    assert opened == [1]
