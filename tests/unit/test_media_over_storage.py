"""Decoding the same media out of an LMDB store rather than out of files.

``tests/unit/test_media.py`` covers every media type against a directory tree. This file asks
the question that matters once a dataset is packed: does the decoder produce the *same pixels*
when the bytes arrive from a key/value store instead of a path? A backend is only allowed to
change where bytes come from, never what they decode to — that is the premise
``science_hash`` relies on when it ignores the storage block entirely.

Each case builds the file tree first, reads it, packs the identical bytes into an LMDB, reads
that, and compares. A difference would mean the two backends are not interchangeable.
"""

from __future__ import annotations

from pathlib import Path

import lmdb
import numpy as np
import pytest
from PIL import Image

from pad_research.data.manifest import PAI, Label, ManifestRecord, MediaType, Split
from pad_research.data.media import MediaReadError, probe_n_frames, read_frames
from pad_research.data.storage.lmdb_store import LmdbStorage


def _record(relative_path: str, media_type: MediaType) -> ManifestRecord:
    return ManifestRecord(
        dataset_id="unit_ds",
        sample_id="sample_001",
        subject_id="subject_001",
        split=Split.train,
        label=Label.bona_fide,
        pai=PAI.none,
        relative_path=relative_path,
        media_type=media_type,
    )


def _frame(value: int, size: int = 8) -> np.ndarray:
    return np.full((size, size, 3), value, dtype=np.uint8)


def _pack(path: Path, entries: dict[str, bytes]) -> LmdbStorage:
    env = lmdb.open(str(path), subdir=True, map_size=1 << 24)
    with env.begin(write=True) as txn:
        for key, value in entries.items():
            txn.put(key.encode("utf-8"), value)
    env.close()
    return LmdbStorage(path)


def _write_video(path: Path, values: list[int], size: int = 8) -> None:
    import av

    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264rgb", rate=10)
        stream.width, stream.height, stream.pix_fmt = size, size, "rgb24"
        # Lossless, so decoded grey levels can be compared exactly across backends.
        stream.options = {"crf": "0", "preset": "ultrafast"}
        for value in values:
            container.mux(stream.encode(av.VideoFrame.from_ndarray(_frame(value, size), "rgb24")))
        container.mux(stream.encode(None))


def test_a_video_decodes_identically_from_a_key_as_from_a_file(tmp_path: Path) -> None:
    """The case the user's datasets are actually in: whole encoded videos packed into LMDB.

    PyAV needs a *seekable* stream and raises NotImplementedError on one that is not, which is
    why media.py wraps fetched bytes in BytesIO rather than any other file-like object.
    """
    source = tmp_path / "tree" / "unit_ds" / "clip.mp4"
    _write_video(source, [0, 40, 80, 120, 160])
    record = _record("unit_ds/clip.mp4", MediaType.video)

    from_files = read_frames(record, tmp_path / "tree", [0, 2, 4])
    store = _pack(tmp_path / "s.lmdb", {"unit_ds/clip.mp4": source.read_bytes()})

    assert probe_n_frames(record, store) == 5
    np.testing.assert_array_equal(read_frames(record, store, [0, 2, 4]), from_files)
    store.close()


def test_frames_stored_as_a_key_range_decode_like_a_directory(tmp_path: Path) -> None:
    # In LMDB a frames_dir is a key prefix. The frame names here carry no extension, which is
    # how stores are commonly built and which the directory-tree filter would otherwise drop.
    tree = tmp_path / "tree" / "unit_ds" / "clip"
    tree.mkdir(parents=True)
    values = [10, 20, 30]
    for index, value in enumerate(values, start=1):
        Image.fromarray(_frame(value)).save(tree / f"{index}.png")
    record = _record("unit_ds/clip", MediaType.frames_dir)

    from_files = read_frames(record, tmp_path / "tree", [0, 1, 2])
    store = _pack(
        tmp_path / "s.lmdb",
        {f"unit_ds/clip/{i}": (tree / f"{i}.png").read_bytes() for i in (1, 2, 3)},
    )

    assert probe_n_frames(record, store) == 3
    np.testing.assert_array_equal(read_frames(record, store, [0, 1, 2]), from_files)
    store.close()


def test_an_npy_clip_reads_the_same_frames_from_a_key(tmp_path: Path) -> None:
    # np.load memory-maps a real file and reads a BytesIO in full; both must yield the same
    # frames in the same order.
    import io

    clip = np.stack([_frame(v) for v in (10, 20, 30, 40)], axis=0)
    tree = tmp_path / "tree" / "unit_ds"
    tree.mkdir(parents=True)
    np.save(tree / "clip.npy", clip)
    record = _record("unit_ds/clip.npy", MediaType.npy_clip)

    buffer = io.BytesIO()
    np.save(buffer, clip)
    store = _pack(tmp_path / "s.lmdb", {"unit_ds/clip.npy": buffer.getvalue()})

    from_files = read_frames(record, tmp_path / "tree", [3, 0, 3])
    np.testing.assert_array_equal(read_frames(record, store, [3, 0, 3]), from_files)
    store.close()


def test_a_missing_key_names_the_sample_and_not_the_key(tmp_path: Path) -> None:
    # Errors reach logs and reports, so they identify a sample by id and never by location
    # (contract section 34).
    store = _pack(tmp_path / "s.lmdb", {"unit_ds/other.mp4": b"x"})
    record = _record("unit_ds/clip.mp4", MediaType.video)
    with pytest.raises(MediaReadError) as excinfo:
        probe_n_frames(record, store)
    message = str(excinfo.value)
    assert "sample_id=sample_001" in message
    assert str(tmp_path) not in message
    store.close()
