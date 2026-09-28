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

*Where* the bytes come from is not this module's business — that is
:mod:`pad_research.data.storage`. What this module does care about is the difference a
backend can and cannot hide. A backend that has a real file hands over a path, and the
decoder streams from it: ``np.load`` maps the array instead of copying it, and PyAV reads
frames as it needs them. A backend that has no file (LMDB, SFTP) hands over bytes, and the
whole object sits in the worker's memory for the length of the call. Both paths exist below
and the path form is always preferred; the fallback is wrapped in ``BytesIO`` rather than any
other file-like object because PyAV requires a *seekable* stream and raises
``NotImplementedError`` on one that is not.

This module never logs a path or any pixel content (contract section 34): errors identify a
sample by ``dataset_id`` and ``sample_id``.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import BinaryIO

import numpy as np

from pad_research.data.manifest import MEDIA_EXTENSIONS, ManifestRecord, MediaType
from pad_research.data.storage.base import StorageBackend, StorageError
from pad_research.data.storage.registry import as_storage

#: Suffixes accepted for the stills inside a ``frames_dir``.
_FRAME_SUFFIXES: tuple[str, ...] = tuple(MEDIA_EXTENSIONS[MediaType.image])

#: Anything a decoder can be pointed at: a real file, or the bytes of one.
MediaSource = StorageBackend | Path | str


class MediaReadError(RuntimeError):
    """Raised when a manifest record cannot be decoded."""


def _describe(record: ManifestRecord) -> str:
    """Identify a record without leaking its path (contract section 34)."""
    return f"dataset_id={record.dataset_id} sample_id={record.sample_id}"


def _frame_children(storage: StorageBackend, record: ManifestRecord) -> list[str]:
    """Return the relative paths of the stills inside a ``frames_dir``, in temporal order.

    Selection is by name, in two passes, because a name can say three different things. A
    directory tree names its frames ``000001.png``: the extension says "this is an image", and
    those are taken. A stray ``notes.txt`` in the same directory says "this is something else"
    and is dropped — that filter is the only thing standing between a documentation file and a
    clip made of it. An LMDB built from the same dataset may key its frames ``<clip>/000001``,
    where the name says *nothing*; dropping those would leave the clip empty for no reason the
    caller could see. So extension-less children are accepted only when no recognisable still
    was found, and are handed to the image decoder, which identifies a format by content.
    """
    try:
        children = storage.list_children(record.relative_path)
    except StorageError as exc:
        raise MediaReadError(f"cannot list frames for {_describe(record)}: {exc}") from exc
    stills = [c for c in children if c.lower().endswith(_FRAME_SUFFIXES)]
    if stills:
        return stills
    return [c for c in children if not PurePosixPath(c).suffix]


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


def _handle(
    storage: StorageBackend, record: ManifestRecord, relative_path: str
) -> Path | io.BytesIO:
    """Return a streamable path when the backend has one, otherwise the bytes."""
    local = storage.local_path(relative_path)
    if local is not None:
        if not local.is_file():
            raise FileNotFoundError(f"media file not found for {_describe(record)}")
        return local
    try:
        return io.BytesIO(storage.read_bytes(relative_path))
    except StorageError as exc:
        raise MediaReadError(f"cannot fetch media for {_describe(record)}: {exc}") from exc


def _require_dir(storage: StorageBackend, record: ManifestRecord) -> None:
    if not storage.is_dir(record.relative_path):
        raise FileNotFoundError(f"frames directory not found for {_describe(record)}")


def _video_frame_count(source: Path | io.BytesIO, record: ManifestRecord) -> int:
    """Frame count of a video, from the container header when it is populated.

    Containers are allowed to report ``0`` frames (many ``.avi`` files written by capture
    tools do), so fall back to counting decoded frames. That fallback is slow, which is why
    adapters should record ``n_frames`` in the manifest at build time.
    """
    import av

    try:
        with av.open(_av_target(source), mode="r") as container:
            stream = container.streams.video[0]
            if stream.frames:
                return int(stream.frames)
            stream.thread_type = "AUTO"
            return sum(1 for _ in container.decode(stream))
    except FileNotFoundError:
        raise
    except Exception as exc:  # PyAV raises a family of container errors
        raise MediaReadError(f"cannot read video for {_describe(record)}: {exc!r}") from exc


def _av_target(source: Path | io.BytesIO) -> str | BinaryIO:
    """PyAV takes a filename or a seekable file object; rewind the latter before each open."""
    if isinstance(source, Path):
        return str(source)
    source.seek(0)
    return source


def probe_n_frames(record: ManifestRecord, source: MediaSource) -> int:
    """Return how many frames ``record`` offers, decoding as little as possible.

    ``ManifestRecord.n_frames`` is authoritative when the adapter filled it in: the manifest
    is built once and read every epoch, so trusting it keeps probing free. Only records that
    leave it unset are inspected, which for a remote backend also means only those records
    cost a round trip.
    """
    if record.n_frames is not None and record.n_frames > 0:
        return int(record.n_frames)

    storage = as_storage(source)
    media_type = record.media_type
    if media_type == MediaType.image:
        return 1
    if media_type == MediaType.frames_dir:
        _require_dir(storage, record)
        count = len(_frame_children(storage, record))
        if count == 0:
            raise MediaReadError(f"frames directory holds no images for {_describe(record)}")
        return count
    if media_type == MediaType.npy_clip:
        return int(_load_npy(storage, record).shape[0])
    if media_type == MediaType.video:
        count = _video_frame_count(_handle(storage, record, record.relative_path), record)
        if count == 0:
            raise MediaReadError(f"video holds no decodable frames for {_describe(record)}")
        return count
    raise MediaReadError(f"unsupported media_type {media_type!r} for {_describe(record)}")


def _load_npy(storage: StorageBackend, record: ManifestRecord) -> np.ndarray:
    """Load an ``.npy`` clip, memory-mapping it when it is a real file.

    ``mmap_mode="r"`` reads the header and leaves the pixels on disk, so probing a clip costs
    nothing and indexing it touches only the frames asked for. It needs a real path; a backend
    serving bytes falls back to a normal in-memory load.
    """
    handle = _handle(storage, record, record.relative_path)
    if isinstance(handle, Path):
        return np.load(handle, allow_pickle=False, mmap_mode="r")
    return np.load(handle, allow_pickle=False)


def _read_image(source: Path | io.BytesIO, record: ManifestRecord) -> np.ndarray:
    from PIL import Image, UnidentifiedImageError

    if isinstance(source, io.BytesIO):
        source.seek(0)
    try:
        with Image.open(source) as img:
            return np.asarray(img.convert("RGB"), dtype=np.uint8)
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaReadError(f"cannot read image for {_describe(record)}: {exc!r}") from exc


def _read_video_frames(
    source: Path | io.BytesIO, record: ManifestRecord, indices: Sequence[int]
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
        with av.open(_av_target(source), mode="r") as container:
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


def read_frames(record: ManifestRecord, source: MediaSource, indices: Sequence[int]) -> np.ndarray:
    """Decode the frames at ``indices`` as ``float32 [len(indices),3,H,W]`` in ``[0, 1]``.

    ``indices`` may repeat a position; the sampler emits repeats when a clip is shorter than
    the requested temporal length, and an image record is always read as the same frame
    repeated. Order is preserved exactly as given.
    """
    if not indices:
        raise ValueError(f"no frame indices requested for {_describe(record)}")
    if any(i < 0 for i in indices):
        raise ValueError(f"frame indices must be non-negative for {_describe(record)}")

    storage = as_storage(source)
    media_type = record.media_type

    if media_type == MediaType.npy_clip:
        clip = _load_npy(storage, record)
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
        frame = _read_image(_handle(storage, record, record.relative_path), record)
        return _to_tchw(np.stack([frame] * len(indices), axis=0))

    if media_type == MediaType.frames_dir:
        _require_dir(storage, record)
        children = _frame_children(storage, record)
        if not children:
            raise MediaReadError(f"frames directory holds no images for {_describe(record)}")
        if max(indices) >= len(children):
            raise MediaReadError(
                f"frames directory for {_describe(record)} holds {len(children)} images, "
                f"index {max(indices)} requested"
            )
        # Read each distinct position once: a sampler that repeats a frame (short clip) must
        # not turn into repeated I/O, which over SFTP is a repeated round trip.
        unique = {
            i: _read_image(_handle(storage, record, children[i]), record)
            for i in sorted(set(indices))
        }
        return _to_tchw(np.stack([unique[i] for i in indices], axis=0))

    if media_type == MediaType.video:
        handle = _handle(storage, record, record.relative_path)
        frames = _read_video_frames(handle, record, indices)
        return _to_tchw(np.stack(frames, axis=0))

    raise MediaReadError(f"unsupported media_type {media_type!r} for {_describe(record)}")


def read_clip(record: ManifestRecord, source: MediaSource) -> np.ndarray:
    """Decode every frame of ``record`` as ``float32 [T,3,H,W]`` in ``[0, 1]``.

    Convenience wrapper for small clips and tests. Training reads through
    :func:`probe_n_frames` plus :func:`read_frames` so that it never holds a whole video.
    """
    return read_frames(record, source, range(probe_n_frames(record, source)))


__all__ = [
    "MediaReadError",
    "MediaSource",
    "probe_n_frames",
    "read_clip",
    "read_frames",
]
