"""Unit tests for decoding every manifest media type.

Every fixture writes real media (a real encoded video, real PNG files) rather than a mock, so
the tests exercise the decoders the H100 runs will use.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pad_research.data.manifest import PAI, Label, ManifestRecord, MediaType, Split
from pad_research.data.media import (
    MediaReadError,
    probe_n_frames,
    read_clip,
    read_frames,
)


def _record(
    relative_path: str,
    media_type: MediaType,
    *,
    n_frames: int | None = None,
) -> ManifestRecord:
    return ManifestRecord(
        dataset_id="unit_ds",
        sample_id="sample_001",
        subject_id="subject_001",
        split=Split.train,
        label=Label.bona_fide,
        pai=PAI.none,
        relative_path=relative_path,
        media_type=media_type,
        n_frames=n_frames,
        width=8,
        height=8,
    )


def _ramp_frame(value: int, size: int = 8) -> np.ndarray:
    """A flat RGB frame whose grey level identifies the frame index."""
    return np.full((size, size, 3), value, dtype=np.uint8)


def _write_video(path: Path, values: list[int], size: int = 8) -> None:
    import av

    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264rgb", rate=10)
        stream.width = size
        stream.height = size
        stream.pix_fmt = "rgb24"
        # Lossless, so a decoded frame equals the frame that was written and the test can
        # assert on exact grey levels instead of a tolerance.
        stream.options = {"crf": "0", "preset": "ultrafast"}
        for value in values:
            frame = av.VideoFrame.from_ndarray(_ramp_frame(value, size), format="rgb24")
            container.mux(stream.encode(frame))
        container.mux(stream.encode(None))


def _write_frames_dir(directory: Path, values: list[int], names: list[str] | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    labels = names or [f"frame_{i}.png" for i in range(len(values))]
    for name, value in zip(labels, values, strict=True):
        Image.fromarray(_ramp_frame(value)).save(directory / name)


# --- npy_clip ---------------------------------------------------------------------------


def test_npy_clip_reads_requested_indices_in_order(tmp_path: Path) -> None:
    clip = np.stack([_ramp_frame(v) for v in (10, 20, 30, 40)], axis=0)
    (tmp_path / "unit_ds").mkdir()
    np.save(tmp_path / "unit_ds" / "clip.npy", clip)
    record = _record("unit_ds/clip.npy", MediaType.npy_clip)

    out = read_frames(record, tmp_path, [3, 0, 3])

    assert out.shape == (3, 3, 8, 8)
    assert out.dtype == np.float32
    greys = [round(float(out[i, 0, 0, 0]) * 255) for i in range(3)]
    assert greys == [40, 10, 40]


def test_npy_clip_index_past_the_end_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "unit_ds").mkdir()
    np.save(tmp_path / "unit_ds" / "clip.npy", np.stack([_ramp_frame(1)] * 2))
    record = _record("unit_ds/clip.npy", MediaType.npy_clip)

    with pytest.raises(MediaReadError, match="has 2 frames"):
        read_frames(record, tmp_path, [0, 5])


# --- video ------------------------------------------------------------------------------


def test_video_decodes_only_the_sampled_positions(tmp_path: Path) -> None:
    _write_video(tmp_path / "unit_ds" / "clip.mp4", [0, 60, 120, 180, 240])
    record = _record("unit_ds/clip.mp4", MediaType.video)

    out = read_frames(record, tmp_path, [0, 2, 4])

    assert out.shape == (3, 3, 8, 8)
    greys = [round(float(out[i, 0, 0, 0]) * 255) for i in range(3)]
    assert greys == [0, 120, 240]


def test_video_repeats_a_position_without_decoding_twice(tmp_path: Path) -> None:
    _write_video(tmp_path / "unit_ds" / "clip.mp4", [0, 60, 120])
    record = _record("unit_ds/clip.mp4", MediaType.video)

    out = read_frames(record, tmp_path, [2, 2, 2])

    greys = [round(float(out[i, 0, 0, 0]) * 255) for i in range(3)]
    assert greys == [120, 120, 120]


def test_video_frame_count_is_probed_from_the_container(tmp_path: Path) -> None:
    _write_video(tmp_path / "unit_ds" / "clip.mp4", [0, 30, 60, 90])
    record = _record("unit_ds/clip.mp4", MediaType.video)

    assert probe_n_frames(record, tmp_path) == 4


def test_manifest_n_frames_is_trusted_over_inspecting_the_file(tmp_path: Path) -> None:
    # Probing must not open the media when the adapter already recorded the count: on a real
    # dataset that would mean opening every video once per epoch.
    record = _record("unit_ds/missing.mp4", MediaType.video, n_frames=7)

    assert probe_n_frames(record, tmp_path) == 7


def test_video_shorter_than_the_manifest_claims_is_an_error(tmp_path: Path) -> None:
    _write_video(tmp_path / "unit_ds" / "clip.mp4", [0, 60])
    record = _record("unit_ds/clip.mp4", MediaType.video, n_frames=50)

    with pytest.raises(MediaReadError, match="ended before frame"):
        read_frames(record, tmp_path, [0, 40])


# --- frames_dir -------------------------------------------------------------------------


def test_frames_dir_orders_frames_numerically(tmp_path: Path) -> None:
    # Lexicographic order would read frame_10 before frame_2 and silently scramble time.
    _write_frames_dir(
        tmp_path / "unit_ds" / "clip",
        [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200],
    )
    record = _record("unit_ds/clip", MediaType.frames_dir)

    assert probe_n_frames(record, tmp_path) == 11
    out = read_frames(record, tmp_path, [1, 2, 10])
    greys = [round(float(out[i, 0, 0, 0]) * 255) for i in range(3)]
    assert greys == [20, 40, 200]


def test_frames_dir_without_images_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "unit_ds" / "clip").mkdir(parents=True)
    (tmp_path / "unit_ds" / "clip" / "notes.txt").write_text("x", encoding="utf-8")
    record = _record("unit_ds/clip", MediaType.frames_dir)

    with pytest.raises(MediaReadError, match="no images"):
        probe_n_frames(record, tmp_path)


# --- image ------------------------------------------------------------------------------


def test_image_record_is_one_frame_repeated(tmp_path: Path) -> None:
    # An image-only dataset (CelebA-Spoof) is read as a clip only when the protocol sets
    # allow_image_dataset_as_clip; the reader supplies the repeated frame it asks for.
    (tmp_path / "unit_ds").mkdir()
    Image.fromarray(_ramp_frame(77)).save(tmp_path / "unit_ds" / "still.png")
    record = _record("unit_ds/still.png", MediaType.image)

    assert probe_n_frames(record, tmp_path) == 1
    out = read_frames(record, tmp_path, [0, 0, 0, 0])
    assert out.shape == (4, 3, 8, 8)
    assert {round(float(out[i, 0, 0, 0]) * 255) for i in range(4)} == {77}


def test_image_record_rejects_a_nonzero_index(tmp_path: Path) -> None:
    (tmp_path / "unit_ds").mkdir()
    Image.fromarray(_ramp_frame(5)).save(tmp_path / "unit_ds" / "still.png")
    record = _record("unit_ds/still.png", MediaType.image)

    with pytest.raises(MediaReadError, match="has 1 frame"):
        read_frames(record, tmp_path, [0, 1])


# --- shared contract --------------------------------------------------------------------


@pytest.mark.parametrize("media_type", [MediaType.npy_clip, MediaType.video, MediaType.image])
def test_missing_media_names_the_sample_not_the_path(tmp_path: Path, media_type: MediaType) -> None:
    record = _record("unit_ds/missing.bin", media_type)

    with pytest.raises(FileNotFoundError) as excinfo:
        read_frames(record, tmp_path, [0])

    message = str(excinfo.value)
    assert "sample_id=sample_001" in message
    assert str(tmp_path) not in message  # contract section 34: no paths in messages


def test_read_clip_returns_every_frame(tmp_path: Path) -> None:
    _write_video(tmp_path / "unit_ds" / "clip.mp4", [0, 50, 100])
    record = _record("unit_ds/clip.mp4", MediaType.video)

    assert read_clip(record, tmp_path).shape == (3, 3, 8, 8)


def test_empty_index_list_is_rejected(tmp_path: Path) -> None:
    record = _record("unit_ds/clip.npy", MediaType.npy_clip)

    with pytest.raises(ValueError, match="no frame indices"):
        read_frames(record, tmp_path, [])
