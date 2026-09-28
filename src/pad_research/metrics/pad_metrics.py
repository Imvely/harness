"""ISO/IEC 30107-3 style presentation attack detection (PAD) metrics.

Numpy-only implementations; ``sklearn`` is imported lazily inside :func:`roc_auc`
and :func:`eer_threshold` so that validators can import this package without it.

Conventions (see ``pad_research.conventions``)
---------------------------------------------
* ``y_attack``: bool array, ``True`` = spoof / presentation attack (label 1),
  ``False`` = bona fide (label 0).
* ``score``: float array, higher = more spoof-like (``P(spoof)``).
* ``pai``: list of PAI species names, aligned with ``score``; the PAI of bona-fide
  samples is ignored.
* Decision rule: ``predict_attack = score >= tau`` (a score exactly at the
  threshold is classified as an attack; see ``conventions.decide_spoof``).

Standard facts (verified 2026-09-17 against the ISO/IEC 30107-3 literature)
--------------------------------------------------------------------------
* **APCER** (Attack Presentation Classification Error Rate) is defined *per PAI
  species*: the proportion of attack presentations of one species that are
  wrongly classified as bona fide.  A system-level ("worst case") APCER is the
  **maximum over PAI species**.  :func:`apcer_per_pai` and :func:`apcer_max`
  implement this; :func:`apcer_pooled` (all attacks in one bucket) is provided
  because the academic PAD literature commonly reports it, but it is *not* the
  standard-compliant summary.
* **BPCER** (Bona fide Presentation Classification Error Rate) is the proportion
  of bona-fide presentations wrongly classified as attacks.
* **ACER** = (APCER + BPCER) / 2 is a community convention (it appeared in the
  earlier standard text and was deprecated later); it is kept for comparability
  with published results.  ``acer_policy`` selects whether the APCER term is the
  ISO ``max_pai`` value or the ``pooled`` value.
* **HTER** = (FAR + FRR) / 2 evaluated at a threshold fitted to the EER of the
  *development* set is the cross-dataset convention in the face-PAD literature.
  Here FAR = pooled APCER and FRR = BPCER, so :func:`hter` always uses the
  pooled APCER.
* **BPCER @ APCER = 10% / 1%** are the standard-compliant operating-point
  reports; :func:`bpcer_at_apcer` fits the operating threshold on a dev set.
  ``PadMetrics.bpcer_at_apcer_10`` / ``bpcer_at_apcer_1`` are optional because
  they are dev-set operating points filled in by the evaluator, not by
  :func:`compute_pad_metrics` (which only sees one score table).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict

AcerPolicy = Literal["max_pai", "pooled"]


class EmptyPAIError(ValueError):
    """Raised when a metric needs attack samples but none are present."""


def _as_arrays(score: npt.ArrayLike, y_attack: npt.ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    """Coerce inputs to a float64 score array and a bool attack array of equal length."""
    s = np.asarray(score, dtype=np.float64).ravel()
    y = np.asarray(y_attack, dtype=bool).ravel()
    if s.shape != y.shape:
        raise ValueError(f"score and y_attack length mismatch: {s.shape[0]} != {y.shape[0]}")
    return s, y


def bpcer(score: npt.ArrayLike, y_attack: npt.ArrayLike, tau: float) -> float:
    """Bona fide Presentation Classification Error Rate: ``mean(score[bona] >= tau)``."""
    s, y = _as_arrays(score, y_attack)
    bona = s[~y]
    if bona.size == 0:
        raise ValueError("bpcer requires at least one bona-fide sample")
    return float(np.mean(bona >= tau))


def apcer_pooled(score: npt.ArrayLike, y_attack: npt.ArrayLike, tau: float) -> float:
    """APCER over all attack samples pooled together: ``mean(score[attack] < tau)``."""
    s, y = _as_arrays(score, y_attack)
    attack = s[y]
    if attack.size == 0:
        raise EmptyPAIError("apcer_pooled requires at least one attack sample")
    return float(np.mean(attack < tau))


def apcer_per_pai(
    score: npt.ArrayLike, y_attack: npt.ArrayLike, pai: Sequence[str], tau: float
) -> dict[str, float]:
    """APCER per PAI species (ISO/IEC 30107-3).

    PAI species with zero attack samples are omitted from the result.  Raises
    :class:`EmptyPAIError` when there are no attack samples at all.  Keys are
    returned in sorted order.
    """
    s, y = _as_arrays(score, y_attack)
    pai_arr = np.asarray(list(pai), dtype=object).ravel()
    if pai_arr.shape != s.shape:
        raise ValueError(f"pai length mismatch: {pai_arr.shape[0]} != {s.shape[0]}")
    if not bool(y.any()):
        raise EmptyPAIError("apcer_per_pai requires at least one attack sample")
    out: dict[str, float] = {}
    for species in sorted({str(p) for p in pai_arr[y]}):
        mask = y & (pai_arr == species)
        out[species] = float(np.mean(s[mask] < tau))
    return out


def apcer_max(per_pai: dict[str, float]) -> float:
    """System-level APCER = max over PAI species (ISO/IEC 30107-3)."""
    if not per_pai:
        raise EmptyPAIError("apcer_max requires at least one PAI species")
    return float(max(per_pai.values()))


def acer(apcer_value: float, bpcer_value: float) -> float:
    """Average Classification Error Rate ``(APCER + BPCER) / 2`` (community convention)."""
    return (float(apcer_value) + float(bpcer_value)) / 2.0


def hter(apcer_pooled_value: float, bpcer_value: float) -> float:
    """Half Total Error Rate ``(FAR + FRR) / 2``; the FAR term is always the pooled APCER."""
    return (float(apcer_pooled_value) + float(bpcer_value)) / 2.0


def roc_auc(score: npt.ArrayLike, y_attack: npt.ArrayLike) -> float:
    """ROC AUC with attacks as the positive class (``sklearn.metrics.roc_auc_score``)."""
    from sklearn.metrics import roc_auc_score  # lazy: validators must not need sklearn

    s, y = _as_arrays(score, y_attack)
    if not bool(y.any()) or bool(y.all()):
        raise ValueError("roc_auc requires both bona-fide and attack samples")
    return float(roc_auc_score(y.astype(int), s))


def eer_threshold(score_dev: npt.ArrayLike, y_attack_dev: npt.ArrayLike) -> tuple[float, float]:
    """Equal-error-rate threshold fitted on a *development* set.

    Uses ``roc_curve(drop_intermediate=False)``, drops the sentinel ``+inf``
    threshold, takes the first index minimising ``|FPR - FNR|`` and returns
    ``(tau, eer)`` with ``eer = (FPR + FNR) / 2`` at that index.  Because sklearn
    predicts positive for ``score >= threshold`` this is consistent with the
    package decision rule.
    """
    from sklearn.metrics import roc_curve  # lazy: validators must not need sklearn

    s, y = _as_arrays(score_dev, y_attack_dev)
    if not bool(y.any()) or bool(y.all()):
        raise ValueError("eer_threshold requires both bona-fide and attack samples")
    fpr, tpr, thr = roc_curve(y.astype(int), s, drop_intermediate=False)
    fpr = np.asarray(fpr, dtype=np.float64)
    fnr = 1.0 - np.asarray(tpr, dtype=np.float64)
    thr = np.asarray(thr, dtype=np.float64)
    keep = np.isfinite(thr)
    fpr, fnr, thr = fpr[keep], fnr[keep], thr[keep]
    i = int(np.argmin(np.abs(fpr - fnr)))
    return float(thr[i]), float((fpr[i] + fnr[i]) / 2.0)


def bpcer_at_apcer(
    score_dev: npt.ArrayLike, y_attack_dev: npt.ArrayLike, target_apcer: float
) -> tuple[float, float]:
    """Operating point ``BPCER @ APCER <= target`` fitted on a *development* set.

    Rule
    ----
    Candidate thresholds are the sorted unique dev scores plus ``+inf`` (the
    "reject nothing" threshold: ``score >= inf`` is never true).  Because both
    error rates are piecewise constant between consecutive scores, this set
    covers every distinct operating point.  Among candidates whose
    ``APCER(tau) = mean(attack < tau)`` is ``<= target_apcer`` the threshold with
    the lowest ``BPCER(tau) = mean(bona >= tau)`` is chosen; ties in BPCER are
    broken towards the *smallest* tau (which has the lowest APCER, the
    security-conservative choice).  The minimum score always satisfies
    ``APCER = 0`` so a feasible threshold always exists.  ``+inf`` can only be
    selected when ``target_apcer >= 1``.

    Returns ``(tau, bpcer_at_tau)``.
    """
    s, y = _as_arrays(score_dev, y_attack_dev)
    if not (0.0 <= float(target_apcer) <= 1.0):
        raise ValueError(f"target_apcer must be within [0, 1], got {target_apcer}")
    attack = s[y]
    bona = s[~y]
    if attack.size == 0:
        raise EmptyPAIError("bpcer_at_apcer requires at least one attack sample")
    if bona.size == 0:
        raise ValueError("bpcer_at_apcer requires at least one bona-fide sample")
    candidates = np.concatenate([np.unique(s), np.asarray([np.inf], dtype=np.float64)])
    apcer_c = np.array([np.mean(attack < t) for t in candidates], dtype=np.float64)
    bpcer_c = np.array([np.mean(bona >= t) for t in candidates], dtype=np.float64)
    feasible = apcer_c <= float(target_apcer) + 1e-12
    idx = np.flatnonzero(feasible)
    best_bpcer = float(bpcer_c[idx].min())
    best = idx[bpcer_c[idx] <= best_bpcer + 1e-12]
    i = int(best[0])  # candidates are ascending -> smallest tau among BPCER ties
    return float(candidates[i]), float(bpcer_c[i])


class PadMetrics(BaseModel):
    """Full PAD metric report for one score table at one fixed threshold."""

    model_config = ConfigDict(extra="forbid")

    tau: float
    apcer_per_pai: dict[str, float]
    apcer_max: float
    apcer_pooled: float
    apcer: float
    bpcer: float
    acer: float
    hter: float
    auc: float
    acer_policy: str
    n_bona_fide: int
    n_attack_per_pai: dict[str, int]
    bpcer_at_apcer_10: float | None = None
    bpcer_at_apcer_1: float | None = None


def compute_pad_metrics(
    score: npt.ArrayLike,
    y_attack: npt.ArrayLike,
    pai: Sequence[str],
    tau: float,
    acer_policy: AcerPolicy = "max_pai",
) -> PadMetrics:
    """Compute all PAD metrics at a fixed ``tau`` (fitted elsewhere on a dev set).

    ``apcer`` and ``acer`` follow ``acer_policy`` (``max_pai`` = ISO maximum
    over species, ``pooled`` = all attacks pooled); ``hter`` always uses the
    pooled APCER.  The dev-set operating points ``bpcer_at_apcer_10/_1`` are
    left ``None``; the evaluator fills them.
    """
    if acer_policy not in ("max_pai", "pooled"):
        raise ValueError(f"unknown acer_policy: {acer_policy!r}")
    s, y = _as_arrays(score, y_attack)
    pai_list = [str(p) for p in pai]
    per_pai = apcer_per_pai(s, y, pai_list, tau)
    a_max = apcer_max(per_pai)
    a_pooled = apcer_pooled(s, y, tau)
    b = bpcer(s, y, tau)
    a_sel = a_max if acer_policy == "max_pai" else a_pooled
    pai_arr = np.asarray(pai_list, dtype=object)
    n_attack_per_pai = {k: int(np.sum(y & (pai_arr == k))) for k in per_pai}
    return PadMetrics(
        tau=float(tau),
        apcer_per_pai=per_pai,
        apcer_max=a_max,
        apcer_pooled=a_pooled,
        apcer=a_sel,
        bpcer=b,
        acer=acer(a_sel, b),
        hter=hter(a_pooled, b),
        auc=roc_auc(s, y),
        acer_policy=acer_policy,
        n_bona_fide=int(np.sum(~y)),
        n_attack_per_pai=n_attack_per_pai,
    )
