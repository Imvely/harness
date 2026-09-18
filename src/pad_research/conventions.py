"""Project-wide label and score conventions.

These constants are the single source of truth for how labels and attack scores are
interpreted everywhere in the harness (metrics, thresholds, reports).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

LABEL_BONA_FIDE = 0
LABEL_SPOOF = 1

ATTACK_SCORE_CONVENTION = "attack_score = sigmoid(logit) = P(spoof); higher = more spoof-like"

#: sha256 of docs/RESEARCH_CONTRACT.md at the time the harness was written. Validators compare
#: it against the file on disk so that silent contract edits are detected.
CONTRACT_SHA256 = "0562540579b17857205945eb5584d6fda07852c52c48c020d4ff3de2a632d35d"


def decide_spoof(score: npt.ArrayLike, tau: float) -> npt.NDArray[np.bool_]:
    """Return the boolean spoof decision ``score >= tau`` (True = predicted attack)."""
    return np.asarray(score, dtype=np.float64) >= tau
