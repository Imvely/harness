"""Build our own frame store from a source tree: decide what goes in, then write it.

The lab's store cannot answer our question, because what it left out cannot be read back
(ADR-016). So we pack our own from the raw trees, which are readable. This module is that
build, and it is split in two on purpose:

* :func:`plan_build` decides **what** is packed and records why everything else was not. It
  reads no pixels, so it is cheap enough to run before every build and to print for review.
* :func:`write_store` copies the bytes of a plan into a sink and returns the manifest records.

Three rules from the measurements are enforced here rather than left to a caller:

**A key comes from the path.** ``<sample_id>/<frame_index:05d>``, where ``sample_id`` is built
from the source path. Two recordings with the same file name cannot collide — the mistake that
overwrote 79,091 Replay-Attack frames (ADR-013).

**A duplicate key fails the build.** The whole key set is checked before a single byte is
written, because a silent overwrite is exactly how those frames were lost.

**A camera that recorded only one class is dropped.** When a camera separates the classes by
itself, a model scores perfectly without looking at a face and no metric shows it. The rule is
arithmetic on the clips, not a test on a dataset name (contract section 27.3): it empties
aihub114 and keeps SR305 in aihub115.

What is written stays a fact-recording operation: every recording condition the source carried
(device, lighting, the dataset's own class name) lands in the manifest, and nothing is
renamed. The sink is injected, so a build can be planned, priced and tested without an LMDB.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pad_research.data.manifest import (
    PAI,
    PAI_FLAT,
    PAI_ON_FACE,
    PAI_THREE_D,
    Label,
    ManifestRecord,
    MediaType,
)
from pad_research.data.pai_map import BONA_FIDE_CLASSES, PaiMappingError, pai_for
from pad_research.data.sources.aihub_tree import SourceClip

#: Frame index width in a key. Zero-padded so byte order is capture order, which is what makes
#: a prefix scan return a clip in the order it was recorded.
FRAME_INDEX_WIDTH = 5


class PaiGroup(StrEnum):
    """A switchable family of attacks. iBeta Level 1 is the current target, so ``flat`` is on
    and ``three_d`` is off by default; a protocol turns a group on rather than naming PAIs."""

    flat = "flat"
    three_d = "three_d"
    on_face = "on_face"


PAI_GROUPS: dict[PaiGroup, frozenset[PAI]] = {
    PaiGroup.flat: PAI_FLAT,
    PaiGroup.three_d: PAI_THREE_D,
    PaiGroup.on_face: PAI_ON_FACE,
}
#: Groups packed unless a caller says otherwise: the flat attacks this project targets first.
DEFAULT_PAI_GROUPS: frozenset[PaiGroup] = frozenset({PaiGroup.flat})


class DropReason(StrEnum):
    """Why a clip is not in the store. Every clip the scan found is either kept or has one."""

    #: The camera recorded only bona fide, or only attacks. Its clips cannot support a claim.
    camera_recorded_one_class = "camera_recorded_one_class"
    #: The attack's PAI belongs to a group this build has switched off.
    pai_group_off = "pai_group_off"
    #: The clip has no frames under it.
    no_frames = "no_frames"


class BuildError(RuntimeError):
    """The build cannot proceed: a duplicate key, an empty plan, a path outside the output."""


def allowed_pai(groups: Iterable[PaiGroup | str]) -> frozenset[PAI]:
    """The PAIs a build accepts. ``none`` is always in: bona fide is never switched off."""
    allowed = {PAI.none}
    for group in groups:
        allowed |= PAI_GROUPS[PaiGroup(group)]
    return frozenset(allowed)


def frame_key(sample_id: str, frame_index: int) -> str:
    """The store key of one frame. ``frame_index`` is the position within the clip, from 0."""
    if frame_index < 0:
        raise ValueError("frame_index must not be negative")
    return f"{sample_id}/{frame_index:0{FRAME_INDEX_WIDTH}d}"


@dataclass(frozen=True)
class PlannedClip:
    """One clip that will be packed, with the label decision already made and recorded."""

    clip: SourceClip
    label: Label
    pai: PAI

    @property
    def sample_id(self) -> str:
        return self.clip.sample_id

    def frame_keys(self) -> tuple[str, ...]:
        return tuple(frame_key(self.sample_id, i) for i in range(len(self.clip.frames)))


@dataclass(frozen=True)
class BuildPlan:
    """What a build will pack, and the reason for every clip it will not."""

    dataset_id: str
    kept: tuple[PlannedClip, ...]
    dropped: tuple[tuple[SourceClip, DropReason], ...] = ()
    #: Cameras that recorded both classes — the set the keep rule is built on.
    devices_recording_both: frozenset[str] = frozenset()
    pai_groups: frozenset[PaiGroup] = DEFAULT_PAI_GROUPS

    @property
    def n_frames(self) -> int:
        return sum(len(planned.clip.frames) for planned in self.kept)

    def frame_keys(self) -> list[str]:
        return [key for planned in self.kept for key in planned.frame_keys()]

    def drop_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, reason in self.dropped:
            counts[reason.value] = counts.get(reason.value, 0) + 1
        return dict(sorted(counts.items()))

    def duplicate_keys(self) -> list[str]:
        """Keys that two clips would both write. Non-empty means the build must not run."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for key in self.frame_keys():
            if key in seen:
                duplicates.add(key)
            seen.add(key)
        return sorted(duplicates)

    def classes_per_label(self) -> dict[str, list[str]]:
        """The dataset's own class names that ended up under each label, for the build report."""
        found: dict[str, set[str]] = {}
        for planned in self.kept:
            found.setdefault(planned.label.value, set()).add(planned.clip.class_name)
        return {label: sorted(names) for label, names in sorted(found.items())}


def _classes_per_device(clips: Iterable[SourceClip]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for clip in clips:
        found.setdefault(clip.capture_device, set()).add(clip.class_name)
    return found


def plan_build(
    clips: Sequence[SourceClip],
    dataset_id: str,
    *,
    pai_groups: Iterable[PaiGroup | str] = DEFAULT_PAI_GROUPS,
    require_camera_recorded_both: bool = True,
) -> BuildPlan:
    """Decide which clips are packed. Reads no pixels; an unmapped class name raises.

    A class the PAI table does not cover stops the plan (:class:`~pad_research.data.pai_map`
    .PaiMappingError) instead of becoming ``other``, so a source that grew a new attack type is
    a decision to make rather than a silent relabelling (contract section 27.2).
    """
    groups = frozenset(PaiGroup(group) for group in pai_groups)
    accepted = allowed_pai(groups)
    bona_fide_classes = BONA_FIDE_CLASSES.get(dataset_id, frozenset())
    both = {
        device
        for device, classes in _classes_per_device(clips).items()
        if classes & bona_fide_classes and classes - bona_fide_classes
    }

    kept: list[PlannedClip] = []
    dropped: list[tuple[SourceClip, DropReason]] = []
    for clip in clips:
        if not clip.frames:
            dropped.append((clip, DropReason.no_frames))
            continue
        label, pai = pai_for(dataset_id, clip.class_name)
        if pai not in accepted:
            dropped.append((clip, DropReason.pai_group_off))
            continue
        if require_camera_recorded_both and clip.capture_device not in both:
            dropped.append((clip, DropReason.camera_recorded_one_class))
            continue
        kept.append(PlannedClip(clip=clip, label=label, pai=pai))

    return BuildPlan(
        dataset_id=dataset_id,
        kept=tuple(kept),
        dropped=tuple(dropped),
        devices_recording_both=frozenset(both),
        pai_groups=groups,
    )


def estimate_bytes(plan: BuildPlan, source_root: Path) -> int:
    """Size of the frames a plan would copy, from directory entries only.

    ADR-016 names capacity as the first thing to check, and this answers it without reading a
    frame: the sizes come from ``stat``, which the filesystem already has.
    """
    total = 0
    for planned in plan.kept:
        clip_dir = source_root / planned.clip.rel_dir
        for name in planned.clip.frames:
            try:
                total += (clip_dir / name).stat().st_size
            except OSError:
                continue
    return total


class FrameSink(Protocol):
    """Where the copied frames go. Injected so a build can be tested without writing an LMDB."""

    def put(self, key: str, value: bytes) -> None: ...

    def close(self) -> None: ...


@dataclass
class MemorySink:
    """A sink that keeps the bytes in a dict. For tests and for a dry run that reads sizes."""

    written: dict[str, bytes] = field(default_factory=dict)

    def put(self, key: str, value: bytes) -> None:
        if key in self.written:
            raise BuildError(f"key {key!r} written twice")
        self.written[key] = value

    def close(self) -> None:
        return None


def _record_for(
    planned: PlannedClip,
    dataset_id: str,
    *,
    reencoded: bool,
    time_source: str,
    source_fps: float | None,
) -> ManifestRecord:
    clip = planned.clip
    extra: dict[str, str | int | float | bool] = {
        # Where these bytes came from, so a record can be traced back to the source tree
        # without the tree itself being part of the hash-relevant path.
        "source_rel_dir": clip.rel_dir,
        "source_first_frame": clip.frames[0],
        "lighting": clip.lighting,
        # Nothing in an AI Hub tree says when a frame was taken, and the distributed frames are
        # already thinned, so no interval may be assumed (ADR-014 decision 3).
        "time_source": time_source,
        "reencoded": reencoded,
        "frame_index_width": FRAME_INDEX_WIDTH,
    }
    if source_fps is not None:
        extra["source_fps"] = source_fps
        extra["dt_seconds"] = 1.0 / source_fps
    return ManifestRecord(
        dataset_id=dataset_id,
        sample_id=planned.sample_id,
        subject_id=clip.subject_id,
        split=clip.split,
        label=planned.label,
        pai=planned.pai,
        # The dataset's own name for what was presented, kept so a mapping can be re-made.
        pai_detail=clip.class_name,
        relative_path=planned.sample_id,
        media_type=MediaType.frames_dir,
        fps=source_fps,
        n_frames=len(clip.frames),
        capture_device=clip.capture_device,
        environment=clip.lighting,
        extra=extra,
    )


def build_records(
    plan: BuildPlan,
    *,
    reencoded: bool = False,
    time_source: str = "unknown",
    source_fps: float | None = None,
) -> list[ManifestRecord]:
    """The manifest records a plan stands for, without touching any bytes."""
    return [
        _record_for(
            planned,
            plan.dataset_id,
            reencoded=reencoded,
            time_source=time_source,
            source_fps=source_fps,
        )
        for planned in plan.kept
    ]


def write_store(
    plan: BuildPlan,
    source_root: Path,
    sink: FrameSink,
    *,
    reencoded: bool = False,
    time_source: str = "unknown",
    source_fps: float | None = None,
    on_clip: Callable[[PlannedClip], None] | None = None,
) -> list[ManifestRecord]:
    """Copy a plan's frames into ``sink`` and return the manifest records.

    Bytes are copied, not decoded and re-encoded: the source JPEG lands in the store
    unchanged, so a spatial-frequency result is not comparing our compressor against the
    dataset's (ADR-013 records which domains the lab re-compressed).

    Duplicate keys are checked before the first write, and the source root is never written to.
    """
    if not plan.kept:
        raise BuildError(
            f"{plan.dataset_id}: nothing to pack — "
            f"{plan.drop_counts() or 'the scan found no clips'}"
        )
    duplicates = plan.duplicate_keys()
    if duplicates:
        raise BuildError(
            f"{plan.dataset_id}: {len(duplicates)} duplicate keys, e.g. {duplicates[:3]}; "
            "refusing to write because the later frame would overwrite the earlier one"
        )

    for planned in plan.kept:
        clip_dir = source_root / planned.clip.rel_dir
        for index, name in enumerate(planned.clip.frames):
            sink.put(frame_key(planned.sample_id, index), (clip_dir / name).read_bytes())
        if on_clip is not None:
            on_clip(planned)
    sink.close()
    return build_records(plan, reencoded=reencoded, time_source=time_source, source_fps=source_fps)


def build_meta(
    plan: BuildPlan,
    *,
    version: str,
    license_: str,
    pii_policy: str,
    adapter: str,
) -> dict[str, object]:
    """The adapter-owned half of ``ManifestMeta``, with the selection rules recorded in it.

    Which cameras, lightings and attack groups were packed is part of the dataset's identity
    (ADR-016 decision 7), so it travels with the manifest and changes the ``manifest_hash``
    when it changes.
    """
    return {
        "dataset_id": plan.dataset_id,
        "version": version,
        "adapter": adapter,
        "license": license_,
        "pii_policy": pii_policy,
        # Frames are kept, but nothing records when each was taken, so no temporal claim may
        # rest on this build (ADR-014).
        "temporal_valid": False,
    }


def plan_report(plan: BuildPlan, source_root: Path | None = None) -> dict[str, object]:
    """A reviewable summary of a plan: what is in, what is out, and how much disk it needs."""
    report: dict[str, object] = {
        "dataset_id": plan.dataset_id,
        "pai_groups": sorted(group.value for group in plan.pai_groups),
        "n_clips_kept": len(plan.kept),
        "n_frames": plan.n_frames,
        "devices_recording_both": sorted(plan.devices_recording_both),
        "dropped": plan.drop_counts(),
        "classes_per_label": plan.classes_per_label(),
        "duplicate_keys": plan.duplicate_keys()[:10],
    }
    if source_root is not None:
        report["estimated_bytes"] = estimate_bytes(plan, source_root)
    return report


def check_output_root(out_root: Path, env_var: str = "PAD_MY_ROOT") -> Path:
    """Resolve where the store may be written, and refuse anywhere else.

    The raw trees and the lab's store are read-only for us, and they sit on the same shared
    volume as our own space. A build writes only under the root named by ``env_var`` so a wrong
    argument cannot reach a teammate's directory (ADR-016 decision 1).
    """
    allowed = os.environ.get(env_var)
    if not allowed:
        raise BuildError(
            f"{env_var} is not set; it must name the directory this build may write to "
            "(the path itself is never committed, contract section 34)"
        )
    root = Path(allowed).expanduser().resolve()
    target = Path(out_root).expanduser().resolve()
    if target != root and root not in target.parents:
        raise BuildError(f"the output directory is not under {env_var}; refusing to write")
    return target


def unmapped_classes(clips: Iterable[SourceClip], dataset_id: str) -> list[str]:
    """Class names the PAI table does not cover. Empty means a plan will not raise."""
    known: set[str] = set(BONA_FIDE_CLASSES.get(dataset_id, frozenset()))
    missing: set[str] = set()
    for clip in clips:
        if clip.class_name in known:
            continue
        try:
            pai_for(dataset_id, clip.class_name)
        except PaiMappingError:
            missing.add(clip.class_name)
        else:
            known.add(clip.class_name)
    return sorted(missing)


def frames_per_class(plan: BuildPlan) -> Mapping[str, int]:
    """Frames kept per PAI, the sample sizes a per-PAI APCER will rest on."""
    counts: dict[str, int] = {}
    for planned in plan.kept:
        counts[planned.pai.value] = counts.get(planned.pai.value, 0) + len(planned.clip.frames)
    return dict(sorted(counts.items()))


__all__ = [
    "DEFAULT_PAI_GROUPS",
    "FRAME_INDEX_WIDTH",
    "PAI_GROUPS",
    "BuildError",
    "BuildPlan",
    "DropReason",
    "FrameSink",
    "MemorySink",
    "PaiGroup",
    "PlannedClip",
    "allowed_pai",
    "build_meta",
    "build_records",
    "check_output_root",
    "estimate_bytes",
    "frame_key",
    "frames_per_class",
    "plan_build",
    "plan_report",
    "unmapped_classes",
    "write_store",
]
