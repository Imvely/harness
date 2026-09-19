"""Build protocol-defined train, dev, test and adaptation record splits."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pad_research.data.manifest import Label, Manifest, ManifestRecord, Split
from pad_research.protocols.adaptation_set import AdaptationSelection
from pad_research.protocols.schema import ProtocolSpec, pai_matches


@dataclass(frozen=True)
class ProtocolSplits:
    source_train: list[ManifestRecord]
    source_dev: list[ManifestRecord]
    target_dev: list[ManifestRecord]
    target_test: list[ManifestRecord]
    adaptation: list[ManifestRecord]


def _manifest(manifests: Mapping[str, Manifest], dataset_id: str) -> Manifest:
    key = dataset_id.lower()
    try:
        return manifests[key]
    except KeyError as exc:
        raise KeyError(f"manifest for dataset_id {dataset_id!r} was not supplied") from exc


def _source_records(
    protocol: ProtocolSpec,
    manifests: Mapping[str, Manifest],
    split: Split,
) -> list[ManifestRecord]:
    labels = set(protocol.source_classes)
    return [
        record
        for dataset_id in protocol.source_datasets
        for record in _manifest(manifests, dataset_id).by_split(split)
        if record.label in labels
    ]


def _evaluation_records(
    protocol: ProtocolSpec,
    records: list[ManifestRecord],
) -> list[ManifestRecord]:
    return [
        record
        for record in records
        if record.label == Label.bona_fide
        or any(pai_matches(protocol_pai, record.pai) for protocol_pai in protocol.attack_types)
    ]


def _target_records(
    protocol: ProtocolSpec,
    manifests: Mapping[str, Manifest],
    split: Split,
) -> list[ManifestRecord]:
    dataset_ids = protocol.target_dataset or protocol.source_datasets
    rows = [
        record
        for dataset_id in dataset_ids
        for record in _manifest(manifests, dataset_id).by_split(split)
    ]
    return _evaluation_records(protocol, rows)


def _adaptation_records(
    protocol: ProtocolSpec,
    manifests: Mapping[str, Manifest],
    adaptation_selection: AdaptationSelection | None,
) -> list[ManifestRecord]:
    if adaptation_selection is None:
        return []
    target = _manifest(manifests, adaptation_selection.dataset_id)
    by_id = {record.sample_id: record for record in target.records}
    try:
        return [by_id[sample_id] for sample_id in adaptation_selection.sample_ids]
    except KeyError as exc:
        raise KeyError(
            f"adaptation sample {exc.args[0]!r} is missing from {adaptation_selection.dataset_id!r}"
        ) from exc


def build_splits(
    protocol: ProtocolSpec,
    manifests: Mapping[str, Manifest],
    adaptation_selection: AdaptationSelection | None,
) -> ProtocolSplits:
    """Return protocol splits and assert adaptation/test sample disjointness."""
    source_train = _source_records(protocol, manifests, Split.train)
    source_dev = _evaluation_records(protocol, _source_records(protocol, manifests, Split.dev))
    target_dev = (
        _target_records(protocol, manifests, Split.dev) if protocol.target_dataset else source_dev
    )
    target_test = _target_records(protocol, manifests, protocol.target_test.split)
    adaptation = _adaptation_records(protocol, manifests, adaptation_selection)

    if protocol.target_test.exclude_adaptation_samples and adaptation:
        adaptation_ids = {record.sample_id for record in adaptation}
        target_test = [record for record in target_test if record.sample_id not in adaptation_ids]

    overlap = sorted(
        {record.sample_id for record in adaptation} & {r.sample_id for r in target_test}
    )
    assert not overlap, f"adaptation and target_test overlap: {overlap[:20]}"
    return ProtocolSplits(
        source_train=source_train,
        source_dev=source_dev,
        target_dev=target_dev,
        target_test=target_test,
        adaptation=adaptation,
    )
