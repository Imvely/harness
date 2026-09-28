"""Per-sample score tables produced by the evaluator.

A :class:`ScoreTable` carries the role of the split it came from (``dev`` /
``test`` / ``adapt``) so that threshold fitting can refuse anything but a dev
table (``ThresholdPolicy.fit`` raises ``ThresholdLeakageError`` otherwise; contract
§41-3: never tune thresholds on test).  Score convention: higher = more
spoof-like; ``y_attack`` ``True`` = spoof.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, model_validator

Role = Literal["dev", "test", "adapt"]
Domain = Literal["source", "target"]

CSV_COLUMNS = ("role", "domain", "sample_id", "subject_id", "score", "y_attack", "pai")


class ScoreTable(BaseModel):
    """Aligned per-sample columns for one evaluation split."""

    model_config = ConfigDict(extra="forbid")

    role: Role
    domain: Domain
    sample_id: list[str]
    subject_id: list[str]
    score: list[float]
    y_attack: list[bool]
    pai: list[str]

    @model_validator(mode="after")
    def _check_lengths(self) -> ScoreTable:
        lengths = {
            "sample_id": len(self.sample_id),
            "subject_id": len(self.subject_id),
            "score": len(self.score),
            "y_attack": len(self.y_attack),
            "pai": len(self.pai),
        }
        if len(set(lengths.values())) != 1:
            raise ValueError(f"ScoreTable columns must have equal length, got {lengths}")
        return self

    @property
    def n(self) -> int:
        """Number of rows."""
        return len(self.score)

    @classmethod
    def from_arrays(
        cls,
        role: Role,
        domain: Domain,
        sample_id: Sequence[str],
        subject_id: Sequence[str],
        score: npt.ArrayLike,
        y_attack: npt.ArrayLike,
        pai: Sequence[str],
    ) -> ScoreTable:
        """Build a table from array-likes (numpy arrays, lists, tensors already on CPU)."""
        score_arr = np.asarray(score, dtype=np.float64).ravel()
        y_arr = np.asarray(y_attack).ravel()
        if y_arr.dtype != np.bool_:
            if not np.all(np.isin(y_arr, (0, 1))):
                raise ValueError("y_attack must be boolean or 0/1")
            y_arr = y_arr.astype(bool)
        return cls(
            role=role,
            domain=domain,
            sample_id=[str(x) for x in sample_id],
            subject_id=[str(x) for x in subject_id],
            score=[float(x) for x in score_arr.tolist()],
            y_attack=[bool(x) for x in y_arr.tolist()],
            pai=[str(x) for x in pai],
        )

    def to_numpy(self) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """Return ``(score float64, y_attack bool, pai list)`` for the metric functions."""
        return (
            np.asarray(self.score, dtype=np.float64),
            np.asarray(self.y_attack, dtype=bool),
            list(self.pai),
        )

    def to_csv(self, path: Path | str) -> Path:
        """Write the table as CSV (columns :data:`CSV_COLUMNS`); scores keep full precision."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(CSV_COLUMNS)
            for i in range(self.n):
                writer.writerow(
                    [
                        self.role,
                        self.domain,
                        self.sample_id[i],
                        self.subject_id[i],
                        repr(self.score[i]),
                        int(self.y_attack[i]),
                        self.pai[i],
                    ]
                )
        return out

    @classmethod
    def from_csv(cls, path: Path | str) -> ScoreTable:
        """Read a CSV written by :meth:`to_csv` (role/domain must be uniform)."""
        src = Path(path)
        with src.open("r", newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            raise ValueError(f"empty score CSV: {src}")
        roles = {r["role"] for r in rows}
        domains = {r["domain"] for r in rows}
        if len(roles) != 1 or len(domains) != 1:
            raise ValueError(f"score CSV must have one role/domain, got {roles}/{domains}")
        role = rows[0]["role"]
        domain = rows[0]["domain"]
        return cls.model_validate(
            {
                "role": role,
                "domain": domain,
                "sample_id": [r["sample_id"] for r in rows],
                "subject_id": [r["subject_id"] for r in rows],
                "score": [float(r["score"]) for r in rows],
                "y_attack": [r["y_attack"].strip().lower() in ("1", "true") for r in rows],
                "pai": [r["pai"] for r in rows],
            }
        )
