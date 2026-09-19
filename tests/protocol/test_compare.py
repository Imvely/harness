from __future__ import annotations

import pytest

from pad_research.errors import ProtocolMismatchError
from pad_research.protocols.compare import Comparability, assert_comparable


def test_assert_comparable_same_hash() -> None:
    assert assert_comparable("a", "a", None) == Comparability.same_hash


def test_assert_comparable_raises_without_justify() -> None:
    with pytest.raises(ProtocolMismatchError):
        assert_comparable("a", "b", None)
    with pytest.raises(ProtocolMismatchError):
        assert_comparable("a", "b", "   ")


def test_assert_comparable_justified() -> None:
    assert (
        assert_comparable("a", "b", "ablation: adaptation enabled") == Comparability.justified_diff
    )
