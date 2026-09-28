"""Dashboard export data contracts for PAD research runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RunMode = Literal["smoke", "full", "unknown"]
PiiPolicy = Literal["synthetic", "internal_only", "licensed_research", "unknown"]
GateVerdict = Literal[
    "pass", "no_gate", "security_regression", "inconclusive", "comparison_blocked", "unknown"
]
ArtifactKind = Literal[
    "markdown",
    "csv",
    "json",
    "yaml",
    "image",
    "checkpoint-meta",
    "unknown",
]

ClaimBlocker = Literal[
    "mode_not_full",
    "research_claim_not_allowed",
    "dataset_synthetic",
    "dataset_pii_unknown",
    "fewer_than_three_seeds",
    "insufficient_pai_support",
    "threshold_not_from_dev",
    "security_regression",
    "multiple_protocol_hashes",
]
"""Why a run may not back a research claim, as codes rather than prose.

The exporter used to emit English sentences here, and the dashboard printed them verbatim
into a Korean-first UI with no way to translate them — the reader met "research claim is not
allowed by run provenance" in the middle of an otherwise Korean panel. A code is the stable
thing; the wording belongs to whoever is doing the rendering.
"""


class DashboardMetrics(BaseModel):
    """Overall PAD metrics shown by the dashboard."""

    model_config = ConfigDict(extra="forbid")

    apcer: float
    bpcer: float
    acer: float
    hter: float
    auc: float
    tau: float


class DashboardThreshold(BaseModel):
    """Threshold provenance for one run."""

    model_config = ConfigDict(extra="forbid")

    rule: str
    fitted_on: str | None
    tau: float | None
    dev_n_bona_fide: int | None
    dev_n_attack: int | None


class DashboardPerAttack(BaseModel):
    """Per-PAI APCER row with optional baseline context."""

    model_config = ConfigDict(extra="forbid")

    pai: str
    apcer: float
    baseline_apcer: float | None = None
    delta: float | None = None
    n_attack: int
    insufficient_support: bool
    regressed: bool | None = None


class DashboardArtifact(BaseModel):
    """Safe artifact reference without raw media paths or local absolute paths.

    No label: it was an English string on the wire ("Resolved spec", "Evaluation JSON") that the
    dashboard printed as-is. `relative_path` already identifies the artifact, so the renderer
    names it in the reader's own language.
    """

    model_config = ConfigDict(extra="forbid")

    relative_path: str
    kind: ArtifactKind


class ClaimEligibility(BaseModel):
    """Run-level checklist for whether numbers may support a research claim."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    full_mode: bool
    research_claim_allowed: bool
    at_least_three_seeds: bool
    enough_pai_support: bool
    threshold_from_dev: bool
    no_security_regression: bool
    single_protocol_in_experiment: bool
    blockers: list[ClaimBlocker] = Field(default_factory=list)


class DashboardRun(BaseModel):
    """Single run record exported for the research dashboard."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    experiment_id: str
    title: str | None = None
    status: str
    gate_verdict: GateVerdict
    mode: RunMode
    seed: int | None
    started_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None
    model_family: str
    adaptation_method: str
    source_datasets: list[str]
    target_datasets: list[str]
    protocol_id: str
    protocol_hash: str
    science_hash: str
    spec_hash: str
    manifest_hashes: dict[str, str]
    dataset_pii_policies: dict[str, PiiPolicy]
    adaptation_set_hash: str | None = None
    research_claim_allowed: bool
    claim_eligibility: ClaimEligibility
    threshold: DashboardThreshold
    metrics: DashboardMetrics
    per_attack: list[DashboardPerAttack]
    tags: dict[str, str]
    artifacts: list[DashboardArtifact]


class DashboardBundle(BaseModel):
    """Top-level dashboard JSON document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "pad-dashboard.v1"
    generated_at: str
    source: str = "mlflow+registry"
    runs: list[DashboardRun]
