"""Security regression gate: per-PAI APCER before vs after adaptation.

Contract §14.3 / §41-5/6: after any domain adaptation the per-PAI APCER (ISO/IEC
30107-3 defines APCER per PAI species) must be compared with the baseline.  A
BPCER improvement or a higher AUC never offsets an APCER regression on any
species; the verdict is ``security_regression`` and the run is not reported as a
success.  Runs measured under different protocols are never compared
(contract §15 / §41-2): a protocol-hash mismatch raises
``ProtocolMismatchError`` unless explicitly justified, in which case the verdict
is ``comparison_blocked``.

Verdict rule
------------
For each PAI present in *both* reports::

    tol       = max(abs_tolerance, rel_tolerance * apcer_before)
    delta     = apcer_after - apcer_before
    regressed = (delta - tol) > 1e-9          # delta == tol passes
    insufficient_support = n_attack_after < min_attack_samples_per_pai

PAIs present on only one side get ``insufficient_support=True`` and ``delta=0``.
Then ``security_regression`` if any PAI regressed with sufficient support, else
``inconclusive`` if any PAI has insufficient support, else ``pass``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pad_research.errors import ProtocolMismatchError
from pad_research.metrics.pad_metrics import PadMetrics

Verdict = Literal["pass", "security_regression", "inconclusive", "comparison_blocked"]


class SecurityGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    abs_tolerance: float = Field(default=0.01, ge=0.0)
    rel_tolerance: float = Field(default=0.0, ge=0.0)
    min_attack_samples_per_pai: int = Field(default=20, ge=0)


class PaiDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pai: str
    apcer_before: float
    apcer_after: float
    delta: float
    n_attack: int
    regressed: bool
    insufficient_support: bool


class SecurityGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    per_pai: list[PaiDelta]
    bpcer_before: float
    bpcer_after: float
    bpcer_delta: float
    bpcer_improved: bool
    auc_before: float
    auc_after: float
    protocol_hash: str | None
    baseline_run_id: str | None = None
    note: str


def _fmt(x: float) -> str:
    return f"{x:.4g}"


def run_security_gate(
    before: PadMetrics,
    after: PadMetrics,
    before_hash: str,
    after_hash: str,
    cfg: SecurityGateConfig,
    justify: str | None = None,
    baseline_run_id: str | None = None,
) -> SecurityGateResult:
    """Compare ``after`` against the baseline ``before`` (see module docstring)."""
    bpcer_delta = after.bpcer - before.bpcer
    bpcer_improved = after.bpcer < before.bpcer  # informational only, never affects verdict

    if before_hash != after_hash:
        if justify is None:
            raise ProtocolMismatchError(
                f"protocol hash mismatch: baseline {before_hash!r} vs candidate {after_hash!r}; "
                "results under different protocols are not comparable (contract §15). "
                "Pass justify=... to record a blocked comparison instead."
            )
        return SecurityGateResult(
            verdict="comparison_blocked",
            per_pai=[],
            bpcer_before=before.bpcer,
            bpcer_after=after.bpcer,
            bpcer_delta=bpcer_delta,
            bpcer_improved=bpcer_improved,
            auc_before=before.auc,
            auc_after=after.auc,
            protocol_hash=None,
            baseline_run_id=baseline_run_id,
            note=(
                f"comparison blocked: protocol hash mismatch ({before_hash[:12]} != "
                f"{after_hash[:12]}); justification: {justify}"
            ),
        )

    per_pai: list[PaiDelta] = []
    messages: list[str] = []
    for pai in sorted(set(before.apcer_per_pai) | set(after.apcer_per_pai)):
        in_before = pai in before.apcer_per_pai
        in_after = pai in after.apcer_per_pai
        n_attack = int(after.n_attack_per_pai.get(pai, 0))
        if not (in_before and in_after):
            side = "baseline" if not in_before else "candidate"
            per_pai.append(
                PaiDelta(
                    pai=pai,
                    apcer_before=before.apcer_per_pai.get(pai, 0.0),
                    apcer_after=after.apcer_per_pai.get(pai, 0.0),
                    delta=0.0,
                    n_attack=n_attack,
                    regressed=False,
                    insufficient_support=True,
                )
            )
            messages.append(f"{pai} missing in {side} -> insufficient support")
            continue
        a_before = before.apcer_per_pai[pai]
        a_after = after.apcer_per_pai[pai]
        delta = a_after - a_before
        tol = max(cfg.abs_tolerance, cfg.rel_tolerance * a_before)
        regressed = (delta - tol) > 1e-9
        insufficient = n_attack < cfg.min_attack_samples_per_pai
        per_pai.append(
            PaiDelta(
                pai=pai,
                apcer_before=a_before,
                apcer_after=a_after,
                delta=delta,
                n_attack=n_attack,
                regressed=regressed,
                insufficient_support=insufficient,
            )
        )
        if regressed:
            messages.append(
                f"{pai} APCER {_fmt(a_before)} -> {_fmt(a_after)} "
                f"({delta:+.4g} > tol {_fmt(tol)})"
                + (
                    f" [n_attack={n_attack} < {cfg.min_attack_samples_per_pai}]"
                    if insufficient
                    else ""
                )
            )
        elif insufficient:
            messages.append(
                f"{pai} n_attack={n_attack} < min {cfg.min_attack_samples_per_pai} -> "
                "insufficient support"
            )

    verdict: Verdict
    if any(d.regressed and not d.insufficient_support for d in per_pai):
        verdict = "security_regression"
    elif any(d.insufficient_support for d in per_pai):
        verdict = "inconclusive"
    else:
        verdict = "pass"

    bpcer_msg = f"BPCER {_fmt(before.bpcer)} -> {_fmt(after.bpcer)} ({bpcer_delta:+.4g})"
    auc_msg = f"AUC {_fmt(before.auc)} -> {_fmt(after.auc)}"
    if not messages:
        messages.append("no per-PAI APCER regression beyond tolerance")
    note = f"{verdict}: " + "; ".join(messages) + f"; {bpcer_msg}; {auc_msg}"

    return SecurityGateResult(
        verdict=verdict,
        per_pai=per_pai,
        bpcer_before=before.bpcer,
        bpcer_after=after.bpcer,
        bpcer_delta=bpcer_delta,
        bpcer_improved=bpcer_improved,
        auc_before=before.auc,
        auc_after=after.auc,
        protocol_hash=after_hash,
        baseline_run_id=baseline_run_id,
        note=note,
    )
