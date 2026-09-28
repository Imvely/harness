"""Exceptions shared across sub-packages (kept dependency free)."""

from __future__ import annotations


class ProtocolMismatchError(RuntimeError):
    """Two runs with different protocol hashes were compared without justification."""


class GateBlockedError(RuntimeError):
    """A launch gate refused to let an experiment run."""


class CheckpointProtocolMismatchError(RuntimeError):
    """A checkpoint was trained under a protocol that differs from the requested one."""
