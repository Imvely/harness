"""Decode manifest media into ``float32 [T,3,H,W]`` arrays in ``[0, 1]``.

Phase 0 only read ``npy_clip``, because the synthetic sanity datasets are the only data the
harness had. The real PAD datasets named by ``configs/protocol/ocim_target_i_v1.yaml``
(Replay-Attack, CASIA-FASD, MSU-MFSD, OULU-NPU) all ship video, and image-only sets such as
CelebA-Spoof ship stills, so Phase 1 needs ``video``, ``frames_dir`` and ``image`` as well.

Reading is split into :func:`probe_n_frames` and :func:`read_frames` on purpose. A Phase 0
reader decoded a whole clip and then threw away all but ``T`` frames, which is harmless for a
16-frame synthetic ``.npy`` and ruinous for a 1080p video of several hundred frames: every
DataLoader worker would hold a full decoded video per item. Probing first lets the sampler
choose indices and the decoder touch only those frames.

This module never logs a path or any pixel content (contract section 34): errors identify a
sample by ``dataset_id`` and ``sample_id``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from pad_research.data.manifest import MEDIA_EXTENSIONS, ManifestRecord, MediaType, resolve_path

#: Suffixes accepted for the stills inside a ``frames_dir``.
_FRAME_SUFFIXES: frozenset[str] = frozenset(MEDIA_EXTENSIONS[MediaType.image])

_DIGITS = re.compile(r"(\d+)")


class MediaReadError(RuntimeError):
    """Raised when a manifest record cannot be decoded."""


def _describe(record: ManifestRecord) -> str:
    """Identify a record without leaking its path (contract section 34)."""
    return f"dataset_id={record.dataset_id} sample_id={record.sample_id}"


def _natural_key(path: Path) -> tuple[object, ...]:
    """Sort ``frame_2.png`` before ``frame_10.png``.

    Plain lexicographic order puts ``frame_10`` first, which silently reorders a clip's
    frames whenever a dataset does not zero-pad its frame numbers. Splitting on digit runs and
    comparing those as integers keeps the temporal order the dataset intended.
    """
    return tuple(int(part) if part.isdigit() else part.lower() for part in _DIGITS.split(path.name))


def _frame_paths(directory: Path) -> list[Path]:
    return sorted(
        (p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _FRAME_SUFFIXES),
        key=_natural_key,
    )


def _to_tchw(arr: np.ndarray) -> np.ndarray:
    """Normalise a decoded array to ``float32 [T,3,H,W]`` in ``[0, 1]``."""
    if arr.ndim != 4:
        raise ValueError(f"clip must have 4 dimensions, got shape {arr.shape}")
    if arr.shape[-1] == 3:
        arr = np.transpose(arr, (0, 3, 1, 2))
    elif arr.shape[1] == 3:
        arr = arr
    else:
        raise ValueError(f"clip must be [T,H,W,3] or [T,3,H,W], got shape {arr.shape}")
    arr = arr.astype(np.float32, copy=False)
    if arr.size and float(np.nanmax(arr)) > 1.0:
        arr = arr / 255.0
    return np.clip(arr, 0.0, 1.0).astype(np.float32, copy=False)


def _media_path(record: ManifestRecord, root: Path | str) -> Path:
    path = resolve_path(record, Path(root))
    expect_dir = record.media_type == MediaType.frames_dir
    if expect_dir and not path.is_dir():
        raise FileNotFoundError(f"frames directory not found for {_describe(record)}")
    if not expect_dir and not path.is_file():
        raise FileNotFoundError(f"media file not found for {_describe(record)}")
    return path


def _video_frame_count(path: Path, record: ManifestRecord) -> int:
    """Frame count of a video, from the container header when it is populated.

    Containers are allowed to report ``0`` frames (many ``.avi`` files written by capture
    tools do), so fall back to counting decoded frames. That fallback is slow, which is why
    adapters should record ``n_frames`` in the manifest at build time.
    """
    import av

    try:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            if stream.frames:
                return int(stream.frames)
            stream.thread_type = "AUTO"
            return sum(1 for _ in container.decode(stream))
    except FileNotFoundError:
        raise
    except Exception as exc:  # PyAV raises a family of container errors
        raise MediaReadError(f"cannot read video for {_describe(record)}: {exc!r}") from exc


def probe_n_frames(record: ManifestRecord, root: Path | str) -> int:
    """Return how many frames ``record`` offers, decoding as little as possible.

    ``ManifestRecord.n_frames`` is authoritative when the adapter filled it in: the manifest
    is built once and read every epoch, so trusting it keeps probing free. Only records that
    leave it unset are inspected on disk.
    """
    if record.n_frames is not None and record.n_frames > 0:
        return int(record.n_frames)

    path = _media_path(record, root)
    if record.media_type == MediaType.npy_clip:
        # mmap reads the .npy header only; the pixels stay on disk.
        return int(np.load(path, allow_pickle=False, mmap_mode="r").shape[0])
    if record.media_type == MediaType.image:
        return 1
    if record.media_type == MediaType.frames_dir:
        count = len(_frame_paths(path))
        if count == 0:
            raise MediaReadError(f"frames directory holds no images for {_describe(record)}")
        return count
    if record.media_type == MediaType.video:
        count = _video_frame_count(path, record)
        if count == 0:
            raise MediaReadError(f"video holds no decodable frames for {_describe(record)}")
        return count
    raise MediaReadError(f"unsupported media_type {record.media_type!r} for {_describe(record)}")


def _read_image_file(path: Path, record: ManifestRecord) -> np.ndarray:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as img:
            return np.asarray(img.convert("RGB"), dtype=np.uint8)
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaReadError(f"cannot read image for {_describe(record)}: {exc!r}") from exc


def _read_video_frames(
    path: Path, record: ManifestRecord, indices: Sequence[int]
) -> list[np.ndarray]:
    """Decode exactly the frames in ``indices`` from a video.

    Frames are collected by decoding forward from the start and keeping the wanted positions,
    stopping once the highest one is reached. Seeking would skip ahead faster, but a seek
    lands on the nearest keyframe and the frames between it and the target still have to be
    decoded to be correct; getting that wrong silently returns the wrong frames, which is a
    far worse failure for a temporal PAD model than a slower read.
    """
    import av

    wanted = set(indices)
    last = max(wanted)
    decoded: dict[int, np.ndarray] = {}
    try:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            for position, frame in enumerate(container.decode(stream)):
                if position in wanted:
                    decoded[position] = frame.to_ndarray(format="rgb24")
                if position >= last:
                    break
    except Exception as exc:  # PyAV raises a family of container errors
        raise MediaReadError(f"cannot decode video for {_describe(record)}: {exc!r}") from exc

    missing = sorted(wanted - decoded.keys())
    if missing:
        raise MediaReadError(
            f"video for {_describe(record)} ended before frame {missing[0]}; "
            f"the manifest claims more frames than the file holds"
        )
    return [decoded[i] for i in indices]


def read_frames(record: ManifestRecord, root: Path | str, indices: Sequence[int]) -> np.ndarray:
    """Decode the frames at ``indices`` as ``float32 [len(indices),3,H,W]`` in ``[0, 1]``.

    ``indices`` may repeat a position; the sampler emits repeats when a clip is shorter than
    the requested temporal length, and an image record is always read as the same frame
    repeated. Order is preserved exactly as given.
    """
    if not indices:
        raise ValueError(f"no frame indices requested for {_describe(record)}")
    if any(i < 0 for i in indices):
        raise ValueError(f"frame indices must be non-negative for {_describe(record)}")

    path = _media_path(record, root)
    media_type = record.media_type

    if media_type == MediaType.npy_clip:
        clip = np.load(path, allow_pickle=False, mmap_mode="r")
        if max(indices) >= clip.shape[0]:
            raise MediaReadError(
                f"npy clip for {_describe(record)} has {clip.shape[0]} frames, "
                f"index {max(indices)} requested"
            )
        return _to_tchw(np.asarray(clip[list(indices)]))

    if media_type == MediaType.image:
        if max(indices) > 0:
            raise MediaReadError(
                f"image record {_describe(record)} has 1 frame, index {max(indices)} requested"
            )
        frame = _read_image_file(path, record)
        return _to_tchw(np.stack([frame] * len(indices), axis=0))

    if media_type == MediaType.frames_dir:
        paths = _frame_paths(path)
        if not paths:
            raise MediaReadError(f"frames directory holds no images for {_describe(record)}")
        if max(indices) >= len(paths):
            raise MediaReadError(
                f"frames directory for {_describe(record)} holds {len(paths)} images, "
                f"index {max(indices)} requested"
            )
        unique = {i: _read_image_file(paths[i], record) for i in sorted(set(indices))}
        return _to_tchw(np.stack([unique[i] for i in indices], axis=0))

    if media_type == MediaType.video:
        frames = _read_video_frames(path, record, indices)
        return _to_tchw(np.stack(frames, axis=0))

    raise MediaReadError(f"unsupported media_type {media_type!r} for {_describe(record)}")


def read_clip(record: ManifestRecord, root: Path | str) -> np.ndarray:
    """Decode every frame of ``record`` as ``float32 [T,3,H,W]`` in ``[0, 1]``.

    Convenience wrapper for small clips and tests. Training reads through
    :func:`probe_n_frames` plus :func:`read_frames` so that it never holds a whole video.
    """
    return read_frames(record, root, range(probe_n_frames(record, root)))


__all__ = [
    "MediaReadError",
    "probe_n_frames",
    "read_clip",
    "read_frames",
]
