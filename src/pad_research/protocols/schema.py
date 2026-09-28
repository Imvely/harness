"""Protocol specification schema (research contract §15, §41-2/3).

A :class:`ProtocolSpec` fixes *what* is compared: source/target datasets, the target
adaptation budget, the test split policy, the attack types, the threshold policy and the
security-gate tolerances.  Everything that influences a metric is part of the protocol hash
(:mod:`pad_research.protocols.hashing`); free-text bookkeeping fields (``description``,
``status``, ``parent_protocol_id``, ``change_note``) are not.

Set-like fields (``source_datasets``, ``target_dataset``, ``source_classes``,
``attack_types``) are normalised to sorted unique lists so that the order written in YAML
never changes the hash (ADR-004).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pad_research.data.manifest import PAI, Label, Split
from pad_research.metrics.security_gate import SecurityGateConfig
from pad_research.metrics.threshold import ThresholdSpec

PROTOCOL_ID_PATTERN = r"^[a-z0-9_]+_v\d+$"

Supervision = Literal["none", "bona_fide_only", "bona_fide_and_spoof_fewshot"]


class TargetAdaptation(BaseModel):
    """Target-domain adaptation budget (which target samples a method may see)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    supervision: Supervision = "none"
    shots_per_subject: int | None = Field(default=None, ge=1)
    total_samples: int | None = Field(default=None, ge=1)
    source_split: Split = Split.train
    selection_seed: int = 0
    subject_disjoint_from_test: bool = True

    @model_validator(mode="after")
    def _check_budget(self) -> TargetAdaptation:
        n_budget = (self.shots_per_subject is not None) + (self.total_samples is not None)
        if self.enabled:
            if self.supervision == "none":
                raise ValueError(
                    "ADAPT_SUPERVISION_REQUIRED: target_adaptation.enabled requires "
                    "supervision != 'none'"
                )
            if n_budget != 1:
                raise ValueError(
                    "ADAPT_BUDGET_AMBIGUOUS: exactly one of shots_per_subject / total_samples "
                    f"must be set when adaptation is enabled (got {n_budget})"
                )
        elif self.supervision != "none":
            raise ValueError(
                "ADAPT_SUPERVISION_WITHOUT_ENABLED: supervision must be 'none' when "
                "target_adaptation.enabled is false"
            )
        return self


class TargetTest(BaseModel):
    """Which target split is tested and whether adaptation samples are removed from it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exclude_adaptation_samples: bool = True
    split: Split = Split.test


def _normalize_dataset_list(values: list[str]) -> list[str]:
    normalized = [v.strip().lower() for v in values]
    seen: set[str] = set()
    for v in normalized:
        if not v:
            raise ValueError("EMPTY_DATASET_ID: dataset ids must not be empty")
        if v in seen:
            raise ValueError(f"DUPLICATE_DATASET: dataset id {v!r} listed more than once")
        seen.add(v)
    return sorted(normalized)


class ProtocolSpec(BaseModel):
    """Immutable evaluation protocol; see the module docstring for the hashing policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_id: str = Field(pattern=PROTOCOL_ID_PATTERN)
    schema_version: Literal[1] = 1
    status: Literal["active", "draft"] = "active"
    description: str = ""
    parent_protocol_id: str | None = None
    change_note: str | None = None
    source_datasets: list[str] = Field(min_length=1)
    target_dataset: list[str] = Field(default_factory=list)
    source_classes: list[Label] = Field(default_factory=lambda: [Label.bona_fide, Label.spoof])
    target_adaptation: TargetAdaptation
    target_test: TargetTest = TargetTest()
    attack_types: list[PAI] = Field(min_length=1)
    threshold: ThresholdSpec = ThresholdSpec()
    acer_policy: Literal["max_pai", "pooled"] = "max_pai"
    security_gate: SecurityGateConfig = SecurityGateConfig()
    allow_image_dataset_as_clip: bool = False

    @field_validator("source_datasets", "target_dataset")
    @classmethod
    def _normalize_datasets(cls, values: list[str]) -> list[str]:
        return _normalize_dataset_list(values)

    @field_validator("source_classes")
    @classmethod
    def _normalize_classes(cls, values: list[Label]) -> list[Label]:
        return sorted(set(values), key=lambda x: x.value)

    @field_validator("attack_types")
    @classmethod
    def _normalize_attack_types(cls, values: list[PAI]) -> list[PAI]:
        if PAI.none in values:
            raise ValueError("ATTACK_TYPE_NONE: 'none' is the bona fide marker, not an attack")
        return sorted(set(values), key=lambda x: x.value)

    @model_validator(mode="after")
    def _check_cross_fields(self) -> ProtocolSpec:
        if self.parent_protocol_id is not None and not (self.change_note or "").strip():
            raise ValueError(
                "PARENT_REQUIRES_CHANGE_NOTE: parent_protocol_id is set, so change_note must "
                "describe what changed (contract §15.1)"
            )
        if self.target_adaptation.enabled and not self.target_dataset:
            raise ValueError(
                "TARGET_REQUIRED: target_adaptation.enabled requires a non-empty target_dataset"
            )
        overlap = sorted(set(self.source_datasets) & set(self.target_dataset))
        if overlap:
            raise ValueError(
                f"SOURCE_TARGET_DATASET_OVERLAP: datasets {overlap} appear in both "
                "source_datasets and target_dataset"
            )
        return self


def pai_matches(protocol_pai: PAI, record_pai: PAI) -> bool:
    """Return True when a manifest record's PAI counts towards a protocol attack type.

    ``replay`` is generic and matches every ``replay*`` species; ``display`` matches
    ``replay_display`` and ``display``; anything else requires equality.
    """
    protocol_pai = PAI(protocol_pai)
    record_pai = PAI(record_pai)
    if protocol_pai == PAI.replay:
        return record_pai.value.startswith("replay")
    if protocol_pai == PAI.display:
        return record_pai in (PAI.replay_display, PAI.display)
    return protocol_pai == record_pai
