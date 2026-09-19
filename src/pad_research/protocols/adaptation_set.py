"""Deterministic selection of the target adaptation set (contract §6.1, §15, ADR-004).

``select_adaptation_set`` is a pure function of (protocol, target manifest): sorting plus a
seeded ``random.Random`` makes the selection reproducible on any machine.
``materialize_adaptation_set`` is the only function that writes to disk and is called at
run start (``train.py``/``adapt.py``) or explicitly via ``validate_protocol.py --materialize``;
validators never write.
"""

from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pad_research.data.manifest import Label, Manifest, ManifestRecord
from pad_research.protocols.hashing import protocol_hash, short_hash
from pad_research.protocols.schema import ProtocolSpec
from pad_research.utils.canonical_json import canonical_json, sha256_text


class InsufficientCandidatesError(ValueError):
    """Fewer eligible target samples than the protocol budget requests."""


class AdaptationSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_id: str
    protocol_hash: str
    dataset_id: str
    sample_ids: list[str]
    subject_ids: list[str]
    adaptation_set_hash: str

    @property
    def file_name(self) -> str:
        return f"{self.protocol_id}.{short_hash(self.adaptation_set_hash)}.jsonl"


def _eligible(records: list[ManifestRecord], supervision: str) -> list[ManifestRecord]:
    if supervision == "bona_fide_only":
        return [r for r in records if r.label == Label.bona_fide]
    if supervision == "bona_fide_and_spoof_fewshot":
        return list(records)
    return []


def select_adaptation_set(p: ProtocolSpec, target: Manifest) -> AdaptationSelection:
    """Choose the adaptation samples for ``p`` from ``target`` deterministically."""
    ta = p.target_adaptation
    if not ta.enabled:
        raise ValueError("protocol has target_adaptation.enabled = false")
    candidates = sorted(
        _eligible(target.by_split(ta.source_split), ta.supervision),
        key=lambda r: (r.subject_id, r.sample_id),
    )
    rng = random.Random(ta.selection_seed)
    chosen: list[ManifestRecord]
    if ta.total_samples is not None:
        if len(candidates) < ta.total_samples:
            raise InsufficientCandidatesError(
                f"requested total_samples={ta.total_samples} but only {len(candidates)} eligible "
                f"records exist in {target.meta.dataset_id}/{ta.source_split}"
            )
        chosen = rng.sample(candidates, ta.total_samples)
    else:
        k = ta.shots_per_subject or 0
        by_subject: dict[str, list[ManifestRecord]] = defaultdict(list)
        for r in candidates:
            by_subject[r.subject_id].append(r)
        chosen = []
        for subject in sorted(by_subject):
            recs = by_subject[subject]
            if len(recs) < k:
                raise InsufficientCandidatesError(
                    f"subject {subject} has {len(recs)} eligible records < shots_per_subject={k}"
                )
            rng.shuffle(recs)
            chosen.extend(recs[:k])
    sample_ids = sorted(r.sample_id for r in chosen)
    subject_ids = sorted({r.subject_id for r in chosen})
    ph = protocol_hash(p)
    payload = {"protocol_hash": ph, "dataset_id": target.meta.dataset_id, "sample_ids": sample_ids}
    return AdaptationSelection(
        protocol_id=p.protocol_id,
        protocol_hash=ph,
        dataset_id=target.meta.dataset_id,
        sample_ids=sample_ids,
        subject_ids=subject_ids,
        adaptation_set_hash=sha256_text(canonical_json(payload)),
    )


def selection_lines(sel: AdaptationSelection, target: Manifest) -> str:
    subject_of = {r.sample_id: r.subject_id for r in target.records}
    return "".join(
        canonical_json({"sample_id": s, "subject_id": subject_of[s]}) + "\n" for s in sel.sample_ids
    )


def materialize_adaptation_set(sel: AdaptationSelection, out_dir: Path, target: Manifest) -> Path:
    """Write ``<protocol_id>.<hash12>.jsonl`` under ``out_dir`` (idempotent, byte-stable)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / sel.file_name
    content = selection_lines(sel, target)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return path
    path.write_text(content, encoding="utf-8")
    return path
