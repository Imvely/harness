"""Helpers to build small (possibly deliberately invalid) manifests for protocol tests."""

from __future__ import annotations

import json
from pathlib import Path

from pad_research.data.manifest import (
    PAI,
    Label,
    ManifestRecord,
    MediaType,
    Split,
    manifest_hash,
)
from pad_research.protocols.schema import ProtocolSpec, TargetAdaptation
from pad_research.utils.canonical_json import canonical_json


def rec(
    ds: str, subject: int, clip: int, split: Split, pai: PAI, *, subject_id: str | None = None
) -> ManifestRecord:
    label = Label.bona_fide if pai == PAI.none else Label.spoof
    sid = subject_id or f"subj{subject:04d}"
    sample_id = f"{ds}_s{subject:03d}_c{clip:02d}_{pai.value}"
    return ManifestRecord(
        dataset_id=ds,
        sample_id=sample_id,
        subject_id=sid,
        split=split,
        label=label,
        pai=pai,
        relative_path=f"{ds}/{sample_id}.npy",
        media_type=MediaType.npy_clip,
        n_frames=16,
    )


def standard_records(ds: str, subject_offset: int = 0, per_split: int = 3) -> list[ManifestRecord]:
    """per_split subjects per split; each subject has bona x2, print, replay_phone, replay_tablet."""
    out: list[ManifestRecord] = []
    s = subject_offset
    for split in (Split.train, Split.dev, Split.test):
        for _ in range(per_split):
            out += [
                rec(ds, s, 0, split, PAI.none),
                rec(ds, s, 1, split, PAI.none),
                rec(ds, s, 2, split, PAI.print),
                rec(ds, s, 3, split, PAI.replay_phone),
                rec(ds, s, 4, split, PAI.replay_tablet),
            ]
            s += 1
    return out


def write_raw_manifest(
    records: list[ManifestRecord],
    out_dir: Path,
    *,
    pii_policy: str = "internal_only",
    temporal_valid: bool = True,
    corrupt_hash: bool = False,
) -> None:
    """Write manifest files WITHOUT record validation (for leakage negative tests)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ds = records[0].dataset_id
    ordered = sorted(records, key=lambda r: r.sample_id)
    h = manifest_hash(ordered)
    (out_dir / f"{ds}.jsonl").write_text(
        "\n".join(canonical_json(r.model_dump(mode="json")) for r in ordered) + "\n"
    )
    splits: dict[str, dict[str, int]] = {}
    for r in ordered:
        d = splits.setdefault(r.split.value, {"n_records": 0, "n_subjects": 0})
        d["n_records"] += 1
    meta = {
        "dataset_id": ds,
        "version": "test",
        "adapter": "test",
        "license": "test",
        "pii_policy": pii_policy,
        "root_env_var": "PAD_DATA_ROOT",
        "temporal_valid": temporal_valid,
        "manifest_hash": ("0" * 64) if corrupt_hash else h,
        "n_records": len(ordered),
        "n_subjects": len({r.subject_id for r in ordered}),
        "splits": splits,
        "pai_counts": {},
        "created_at": "2026-01-01T00:00:00+00:00",
        "generator_commit": None,
    }
    (out_dir / f"{ds}.meta.json").write_text(json.dumps(meta, indent=1))


def protocol(**overrides: object) -> ProtocolSpec:
    base: dict[str, object] = {
        "protocol_id": "t_src_to_tgt_v1",
        "source_datasets": ["src"],
        "target_dataset": ["tgt"],
        "target_adaptation": TargetAdaptation(
            enabled=True, supervision="bona_fide_only", total_samples=4
        ),
        "attack_types": [PAI.print, PAI.replay_phone, PAI.replay_tablet],
        "security_gate": {
            "abs_tolerance": 0.01,
            "rel_tolerance": 0.0,
            "min_attack_samples_per_pai": 2,
        },
    }
    base.update(overrides)
    return ProtocolSpec.model_validate(base)
