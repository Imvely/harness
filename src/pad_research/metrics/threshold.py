"""Threshold policy: fit on the development set once, then keep it fixed.

Contract §41-3 forbids tuning thresholds on the test set.  :meth:`ThresholdPolicy.fit`
only accepts a ``ScoreTable`` whose ``role == "dev"``; anything else raises
:class:`ThresholdLeakageError`.  The fitted policy records where it was fitted
(``fitted_on = "<domain>/dev"``) and the dev-set support so that every reported
metric can be tied to its threshold policy (contract §30).

Rules
-----
* ``eer``: dev-set equal-error-rate threshold (``metrics.pad_metrics.eer_threshold``);
  the cross-dataset HTER convention.
* ``bpcer_at_apcer``: threshold with the lowest dev BPCER subject to
  ``APCER <= rule_param`` (ISO/IEC 30107-3 operating point, e.g. 0.10 or 0.01).
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, model_validator

from pad_research.conventions import decide_spoof
from pad_research.evaluation.scores import ScoreTable
from pad_research.metrics.pad_metrics import bpcer_at_apcer, eer_threshold


class ThresholdLeakageError(RuntimeError):
    """Raised when a threshold would be fitted on anything but a dev-role score table."""


class NotFittedError(RuntimeError):
    """Raised when :meth:`ThresholdPolicy.apply` is called before :meth:`fit`."""


class ThresholdSpec(BaseModel):
    """Declarative threshold configuration (shared with ``protocols.schema``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["dev_set"] = "dev_set"
    policy: Literal["fixed_after_dev"] = "fixed_after_dev"
    rule: Literal["eer", "bpcer_at_apcer"] = "eer"
    rule_param: float | None = None
    dev_domain: Literal["source", "target"] = "source"

    @model_validator(mode="after")
    def _check_rule_param(self) -> ThresholdSpec:
        if self.rule == "bpcer_at_apcer":
            if self.rule_param is None:
                raise ValueError("rule 'bpcer_at_apcer' requires rule_param (target APCER)")
            if not (0.0 < self.rule_param <= 1.0):
                raise ValueError(f"rule_param must be in (0, 1], got {self.rule_param}")
        return self


class ThresholdPolicy(BaseModel):
    """A threshold spec plus, once fitted, the threshold and its dev-set provenance."""

    model_config = ConfigDict(extra="forbid")

    spec: ThresholdSpec
    tau: float | None = None
    fitted_on: str | None = None
    dev_n_bona_fide: int | None = None
    dev_n_attack: int | None = None
    dev_eer: float | None = None

    @property
    def is_fitted(self) -> bool:
        return self.tau is not None

    def fit(self, table: ScoreTable) -> ThresholdPolicy:
        """Return a NEW fitted policy; ``self`` is left untouched.

        Raises :class:`ThresholdLeakageError` unless ``table.role == "dev"``.
        """
        if table.role != "dev":
            raise ThresholdLeakageError(
                f"threshold may only be fitted on a dev table, got role={table.role!r} "
                f"(domain={table.domain!r})"
            )
        score, y_attack, _ = table.to_numpy()
        dev_eer: float | None
        if self.spec.rule == "eer":
            tau, dev_eer = eer_threshold(score, y_attack)
        else:
            assert self.spec.rule_param is not None  # guaranteed by ThresholdSpec validator
            tau, _ = bpcer_at_apcer(score, y_attack, self.spec.rule_param)
            dev_eer = None
        return self.model_copy(
            update={
                "tau": float(tau),
                "fitted_on": f"{table.domain}/{table.role}",
                "dev_n_bona_fide": int(np.sum(~y_attack)),
                "dev_n_attack": int(np.sum(y_attack)),
                "dev_eer": dev_eer,
            }
        )

    def apply(self, score: npt.ArrayLike) -> np.ndarray:
        """Decide ``score >= tau`` (bool array, ``True`` = attack)."""
        if self.tau is None:
            raise NotFittedError("ThresholdPolicy.apply called before fit")
        return decide_spoof(score, self.tau)
