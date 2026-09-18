"""Protocol comparability (contract §15.1): same hash, or an explicit justification."""

from __future__ import annotations

from enum import StrEnum

from pad_research.errors import ProtocolMismatchError

__all__ = ["Comparability", "ProtocolMismatchError", "assert_comparable"]


class Comparability(StrEnum):
    same_hash = "same_hash"
    justified_diff = "justified_diff"


def assert_comparable(a_hash: str, b_hash: str, justify: str | None) -> Comparability:
    """Return how two runs may be compared, or raise :class:`ProtocolMismatchError`.

    Equal hashes allow a direct comparison.  Different hashes are only comparable when a
    non-empty ``justify`` string is given (recorded next to the comparison); otherwise the
    comparison is refused.
    """
    if a_hash == b_hash:
        return Comparability.same_hash
    if justify is not None and justify.strip():
        return Comparability.justified_diff
    raise ProtocolMismatchError(
        f"protocol hash mismatch: {a_hash[:12]} != {b_hash[:12]}; results under different "
        "protocols are not directly comparable (contract §15.1). Provide a justification to "
        "record a justified comparison."
    )
