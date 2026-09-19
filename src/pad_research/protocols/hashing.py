"""Protocol hash: sha256 of the canonical JSON of every metric-relevant protocol field.

Two runs are directly comparable only when their protocol hashes are equal (contract
§15.1).  Bookkeeping fields are excluded so that editing a description or marking a
protocol ``draft``/``active`` never breaks comparability; ``schema_version`` is included so
that a schema change is an explicit, visible hash change (ADR-004).
"""

from __future__ import annotations

from pad_research.protocols.schema import ProtocolSpec
from pad_research.utils.canonical_json import canonical_json, sha256_text

#: Fields that never influence a metric and are therefore left out of the hash.
HASH_EXCLUDED: frozenset[str] = frozenset(
    {"description", "parent_protocol_id", "change_note", "status"}
)


def protocol_hash(p: ProtocolSpec) -> str:
    """Return the full hex sha256 protocol hash of ``p``."""
    payload = p.model_dump(mode="json", exclude=set(HASH_EXCLUDED))
    return sha256_text(canonical_json(payload))


def short_hash(h: str) -> str:
    """Return the 12-character prefix used in file names and log lines."""
    return h[:12]
