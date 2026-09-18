"""Protocol validation against the dataset manifests (contract §6.1, §15, §41-3).

Pure: never writes to the filesystem. Every finding is a :class:`ValidationIssue` with a
stable ``code`` so tests, hooks and reports can match on it.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from pad_research.data.manifest import (
    PAI,
    Label,
    Manifest,
    ManifestNotFoundError,
    ManifestRecord,
    ManifestTamperedError,
    Split,
    load_manifest,
)
from pad_research.protocols.adaptation_set import (
    AdaptationSelection,
    InsufficientCandidatesError,
    select_adaptation_set,
)
from pad_research.protocols.hashing import protocol_hash
from pad_research.protocols.schema import ProtocolSpec, pai_matches

Severity = Literal["error", "warning"]


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Severity
    message: str
    details: dict[str, Any] = {}


class ProtocolValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: str
    protocol_hash: str
    status: str
    manifest_hashes: dict[str, str]
    adaptation_set_hash: str | None
    research_claim_allowed: bool
    issues: list[ValidationIssue]

    @property
    def ok(self) -> bool:
        return not self.errors()

    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def codes(self) -> set[str]:
        return {i.code for i in self.issues}


def _attack_records(records: list[ManifestRecord], pai: PAI) -> list[ManifestRecord]:
    return [r for r in records if r.label == Label.spoof and pai_matches(pai, r.pai)]


def _check_manifest(m: Manifest, p: ProtocolSpec, frames: int, out: list[ValidationIssue]) -> None:
    ds = m.meta.dataset_id
    subject_splits: dict[str, set[str]] = defaultdict(set)
    for r in m.records:
        subject_splits[r.subject_id].add(r.split.value)
        bona = r.label == Label.bona_fide
        if bona != (r.pai == PAI.none):
            out.append(
                ValidationIssue(
                    code="LABEL_PAI_INCONSISTENT",
                    severity="error",
                    message=f"{ds}/{r.sample_id}: label {r.label} but pai {r.pai}",
                )
            )
    leaked = sorted(s for s, splits in subject_splits.items() if len(splits) > 1)
    if leaked:
        out.append(
            ValidationIssue(
                code="SUBJECT_OVERLAP_SPLITS",
                severity="error",
                message=f"{ds}: {len(leaked)} subject(s) appear in more than one split",
                details={"dataset_id": ds, "subjects": leaked[:20]},
            )
        )
    if not m.meta.temporal_valid and frames > 1 and not p.allow_image_dataset_as_clip:
        out.append(
            ValidationIssue(
                code="IMAGE_DATASET_AS_CLIP",
                severity="error",
                message=(
                    f"{ds} is image-only (temporal_valid=false) but the model uses {frames} "
                    "frames; set allow_image_dataset_as_clip for an explicit ablation (§6.1)"
                ),
            )
        )


def validate_protocol(
    p: ProtocolSpec,
    manifests_dir: Path,
    *,
    frames: int = 1,
    require_manifests: bool | None = None,
) -> ProtocolValidation:
    """Validate ``p`` against the manifests in ``manifests_dir`` without side effects."""
    issues: list[ValidationIssue] = []
    require = p.status == "active" if require_manifests is None else require_manifests
    loaded: dict[str, Manifest] = {}
    hashes: dict[str, str] = {}
    for ds in [*p.source_datasets, *p.target_dataset]:
        try:
            m = load_manifest(ds, manifests_dir)
        except ManifestNotFoundError:
            issues.append(
                ValidationIssue(
                    code="MISSING_MANIFEST",
                    severity="error" if require else "warning",
                    message=f"manifest for {ds} not found in {manifests_dir}",
                    details={"dataset_id": ds},
                )
            )
            continue
        except ManifestTamperedError as exc:
            issues.append(
                ValidationIssue(
                    code="MANIFEST_HASH_MISMATCH",
                    severity="error",
                    message=f"{ds}: {exc}",
                    details={"dataset_id": ds},
                )
            )
            continue
        loaded[ds] = m
        hashes[ds] = m.meta.manifest_hash
        _check_manifest(m, p, frames, issues)

    research_claim_allowed = all(m.meta.pii_policy != "synthetic" for m in loaded.values())

    source_subjects: set[str] = set()
    for ds in p.source_datasets:
        if ds in loaded:
            source_subjects |= loaded[ds].subjects()
    target_subjects: set[str] = set()
    for ds in p.target_dataset:
        if ds in loaded:
            target_subjects |= loaded[ds].subjects()
    overlap = sorted(source_subjects & target_subjects)
    if overlap:
        issues.append(
            ValidationIssue(
                code="SOURCE_TARGET_SUBJECT_OVERLAP",
                severity="error",
                message=f"{len(overlap)} subject id(s) appear in both source and target datasets",
                details={"subjects": overlap[:20]},
            )
        )

    if p.threshold.source != "dev_set":  # defensive: the type already forbids anything else
        issues.append(
            ValidationIssue(
                code="THRESHOLD_SOURCE_NOT_DEV",
                severity="error",
                message="threshold must be chosen on the dev set (§41-3)",
            )
        )

    # Test-split checks: target test split when a target exists, else source test split.
    test_records: list[ManifestRecord] = []
    test_datasets = p.target_dataset or p.source_datasets
    test_split = p.target_test.split if p.target_dataset else Split.test
    for ds in test_datasets:
        if ds in loaded:
            test_records.extend(loaded[ds].by_split(test_split))
    if test_records:
        for pai in p.attack_types:
            n = len(_attack_records(test_records, pai))
            if n == 0:
                issues.append(
                    ValidationIssue(
                        code="ATTACK_TYPE_ABSENT_IN_TEST",
                        severity="error",
                        message=f"attack type {pai} has no samples in the {test_split} split",
                        details={"pai": pai.value},
                    )
                )
            elif n < p.security_gate.min_attack_samples_per_pai:
                issues.append(
                    ValidationIssue(
                        code="SMALL_PAI_SUPPORT",
                        severity="warning",
                        message=(
                            f"attack type {pai} has {n} test samples < "
                            f"min_attack_samples_per_pai={p.security_gate.min_attack_samples_per_pai}"
                            " (gate will be inconclusive)"
                        ),
                        details={"pai": pai.value, "n": n},
                    )
                )

    if p.threshold.dev_domain == "target" and p.target_dataset:
        dev_records = [
            r for ds in p.target_dataset if ds in loaded for r in loaded[ds].by_split(Split.dev)
        ]
        if dev_records and not any(r.label == Label.spoof for r in dev_records):
            issues.append(
                ValidationIssue(
                    code="DEV_DOMAIN_TARGET_WITHOUT_SPOOF",
                    severity="warning",
                    message="threshold.dev_domain=target but the target dev split has no spoof",
                )
            )

    adaptation_hash: str | None = None
    ta = p.target_adaptation
    if ta.enabled:
        if ta.source_split == p.target_test.split:
            issues.append(
                ValidationIssue(
                    code="ADAPT_FROM_TEST_SPLIT",
                    severity="error",
                    message="adaptation samples must not come from the test split (§6.1)",
                )
            )
        if not p.target_test.exclude_adaptation_samples:
            issues.append(
                ValidationIssue(
                    code="ADAPT_TEST_NOT_EXCLUDED",
                    severity="error",
                    message="target_test.exclude_adaptation_samples must be true (§6.1)",
                )
            )
        if len(p.target_dataset) > 1:
            issues.append(
                ValidationIssue(
                    code="ADAPT_MULTI_TARGET_UNSUPPORTED",
                    severity="error",
                    message="Phase 0 supports a single target dataset for adaptation",
                )
            )
        target_id = p.target_dataset[0] if p.target_dataset else None
        if target_id is not None and target_id in loaded and len(p.target_dataset) == 1:
            target = loaded[target_id]
            sel: AdaptationSelection | None = None
            try:
                sel = select_adaptation_set(p, target)
            except InsufficientCandidatesError as exc:
                issues.append(
                    ValidationIssue(
                        code="ADAPT_INSUFFICIENT_CANDIDATES", severity="error", message=str(exc)
                    )
                )
            if sel is not None:
                adaptation_hash = sel.adaptation_set_hash
                by_id = {r.sample_id: r for r in target.records}
                if ta.supervision == "bona_fide_only" and any(
                    by_id[s].label != Label.bona_fide for s in sel.sample_ids
                ):
                    issues.append(
                        ValidationIssue(
                            code="ADAPT_SUPERVISION_LABEL_MISMATCH",
                            severity="error",
                            message="bona_fide_only adaptation set contains spoof samples",
                        )
                    )
                test_ids = {r.sample_id for r in target.by_split(p.target_test.split)}
                sample_overlap = sorted(set(sel.sample_ids) & test_ids)
                if sample_overlap:
                    issues.append(
                        ValidationIssue(
                            code="ADAPT_TEST_SAMPLE_OVERLAP",
                            severity="error",
                            message=f"{len(sample_overlap)} adaptation sample(s) are in the test split",
                            details={"sample_ids": sample_overlap[:20]},
                        )
                    )
                if ta.subject_disjoint_from_test:
                    subj_overlap = sorted(
                        set(sel.subject_ids) & target.subjects(p.target_test.split)
                    )
                    if subj_overlap:
                        issues.append(
                            ValidationIssue(
                                code="ADAPT_TEST_SUBJECT_OVERLAP",
                                severity="error",
                                message=(
                                    f"{len(subj_overlap)} adaptation subject(s) also appear in the "
                                    "test split"
                                ),
                                details={"subjects": subj_overlap[:20]},
                            )
                        )

    return ProtocolValidation(
        protocol_id=p.protocol_id,
        protocol_hash=protocol_hash(p),
        status=p.status,
        manifest_hashes=hashes,
        adaptation_set_hash=adaptation_hash,
        research_claim_allowed=research_claim_allowed,
        issues=issues,
    )
