"""Read an AI Hub face-PAD directory tree as clips, without deciding anything about them.

The two AI Hub domains share a shape:

    <root>/<purpose>/<subject>/<capture device>/<lighting>/<class>/color/image/*.jpg

``purpose`` is ``training`` or ``validation``; ``class`` is the dataset's own name for what was
presented (``real_01_phone``, ``attack_03_replay_phone``). Every level is a fact the recording
carries, and each one can become a shortcut a model learns instead of the face, so this module
keeps them all and throws none away: what to include is a research decision made elsewhere
(ADR-013, ADR-016), and a scanner that silently dropped a lighting condition would hide it.

Nothing here reads an image. It lists names.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pad_research.data.manifest import Split

#: Directory under a class that holds the RGB frames. The tree also carries depth and IR for
#: some devices; this project is RGB-first (contract section 0).
COLOR_SUBPATH = ("color", "image")
FRAME_SUFFIX = ".jpg"
#: The dataset's own word for a split. `validation` is our dev set: a threshold may be fitted
#: on it, which `test` must never be (contract section 14).
PURPOSE_SPLITS: dict[str, Split] = {"training": Split.train, "validation": Split.dev}

_DIGITS = re.compile(r"(\d+)")


def _frame_order(name: str) -> tuple[object, ...]:
    """Sort `2.jpg` before `10.jpg`; the tree does not zero-pad."""
    return tuple(int(p) if p.isdigit() else p.lower() for p in _DIGITS.split(name))


@dataclass(frozen=True)
class SourceClip:
    """One recording: a class, presented under one lighting, captured by one device."""

    subject_id: str
    split: Split
    class_name: str
    capture_device: str
    lighting: str
    #: Path of the frame directory relative to the dataset root, '/'-separated.
    rel_dir: str
    #: Frame file names in capture order.
    frames: tuple[str, ...]

    @property
    def sample_id(self) -> str:
        """A name unique within the dataset, derived from the path it came from.

        Built from the path rather than the class name, so two recordings can never collide —
        the mistake that cost Replay-Attack 79,091 frames (ADR-013).
        """
        parts = (
            self.split.value,
            self.subject_id,
            self.capture_device,
            self.lighting,
            self.class_name,
        )
        return "__".join(re.sub(r"[^A-Za-z0-9_.-]+", "-", part).strip("-") for part in parts)


def scan_aihub_tree(root: Path) -> list[SourceClip]:
    """List every RGB clip under ``root``. Unreadable or empty directories are skipped."""
    clips: list[SourceClip] = []
    for purpose, split in PURPOSE_SPLITS.items():
        purpose_dir = root / purpose
        if not purpose_dir.is_dir():
            continue
        for subject_dir in sorted(p for p in purpose_dir.iterdir() if p.is_dir()):
            for device_dir in sorted(p for p in subject_dir.iterdir() if p.is_dir()):
                for lighting_dir in sorted(p for p in device_dir.iterdir() if p.is_dir()):
                    for class_dir in sorted(p for p in lighting_dir.iterdir() if p.is_dir()):
                        image_dir = class_dir.joinpath(*COLOR_SUBPATH)
                        if not image_dir.is_dir():
                            continue
                        frames = tuple(
                            sorted(
                                (
                                    p.name
                                    for p in image_dir.iterdir()
                                    if p.suffix.lower() == FRAME_SUFFIX
                                ),
                                key=_frame_order,
                            )
                        )
                        if not frames:
                            continue
                        clips.append(
                            SourceClip(
                                subject_id=subject_dir.name,
                                split=split,
                                class_name=class_dir.name,
                                capture_device=device_dir.name,
                                lighting=lighting_dir.name,
                                rel_dir=image_dir.relative_to(root).as_posix(),
                                frames=frames,
                            )
                        )
    return clips


def classes_per_device(clips: Iterable[SourceClip]) -> dict[str, set[str]]:
    """Which classes each capture device recorded."""
    found: dict[str, set[str]] = {}
    for clip in clips:
        found.setdefault(clip.capture_device, set()).add(clip.class_name)
    return found


def devices_recording_both(
    clips: Iterable[SourceClip], bona_fide_classes: Iterable[str]
) -> set[str]:
    """Capture devices that recorded both bona fide and attack clips.

    This is the question that decides whether a domain can support a claim about faces. When no
    device recorded both, the camera alone separates the classes: a model reaches a perfect
    score without looking at a face, and no metric shows it (ADR-013). A domain like that is
    excluded by the protocol rather than quietly trained on.
    """
    bona_fide = set(bona_fide_classes)
    both: set[str] = set()
    for device, classes in classes_per_device(clips).items():
        if classes & bona_fide and classes - bona_fide:
            both.add(device)
    return both


__all__ = [
    "COLOR_SUBPATH",
    "PURPOSE_SPLITS",
    "SourceClip",
    "classes_per_device",
    "devices_recording_both",
    "scan_aihub_tree",
]
