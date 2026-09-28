"""Synthetic PAD datasets for smoke tests and harness validation.

Two domains (``synthetic_a`` / ``synthetic_b``) share the same class structure but differ in
capture characteristics (brightness, gain, noise, colour cast, blur), giving a controllable
domain gap. Clips are tiny uint8 arrays ``[T, H, W, 3]`` generated from a per-sample seed,
so a rebuild is byte-identical. Results on these datasets never support research claims
(``pii_policy == "synthetic"`` marks them as non research grade).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from pad_research.data.adapters.base import DatasetAdapter
from pad_research.data.manifest import PAI, Label, ManifestRecord, MediaType, Split


@dataclass(frozen=True)
class SyntheticDomain:
    """Capture-domain transform applied to every clip of a synthetic dataset."""

    brightness: float
    gain: float
    noise_std: float
    color_cast: tuple[float, float, float]
    blur: int


SYN_DOMAINS: dict[str, SyntheticDomain] = {
    "synthetic_a": SyntheticDomain(0.0, 1.0, 0.02, (0.0, 0.0, 0.0), 0),
    "synthetic_b": SyntheticDomain(-0.15, 1.3, 0.05, (0.05, -0.03, 0.02), 1),
}

#: Subject offsets keep subject_ids disjoint across the synthetic domains.
SYN_SUBJECT_OFFSETS: dict[str, int] = {"synthetic_a": 0, "synthetic_b": 1000}

#: PAI of clip index c within a subject (cycled when clips_per_subject != 8).
_PAI_PATTERN: tuple[PAI, ...] = (
    PAI.none,
    PAI.none,
    PAI.none,
    PAI.none,
    PAI.print,
    PAI.print,
    PAI.replay_phone,
    PAI.replay_tablet,
)


def _seed_from_sample_id(sample_id: str) -> int:
    return int.from_bytes(hashlib.sha256(sample_id.encode("utf-8")).digest()[:8], "little")


def _box_blur(frames: npt.NDArray[np.float64], radius: int) -> npt.NDArray[np.float64]:
    """Separable box blur with edge replication over the spatial axes of ``[T,H,W,C]``."""
    if radius <= 0:
        return frames
    k = 2 * radius + 1
    padded = np.pad(frames, ((0, 0), (radius, radius), (radius, radius), (0, 0)), mode="edge")
    out = np.zeros_like(frames)
    for dy in range(k):
        for dx in range(k):
            out += padded[:, dy : dy + frames.shape[1], dx : dx + frames.shape[2], :]
    return out / float(k * k)


def generate_clip(
    sample_id: str,
    pai: PAI | str,
    domain: SyntheticDomain,
    T: int,  # noqa: N803 - T/H/W follow the interface contract
    H: int,  # noqa: N803
    W: int,  # noqa: N803
) -> npt.NDArray[np.uint8]:
    """Generate a deterministic uint8 clip ``[T, H, W, 3]`` for ``sample_id``.

    Cues: bona fide = smooth low-frequency blob with slow motion; print = static with a
    high-frequency halftone grid; replay_phone / replay_tablet = distinct flicker frequency
    plus horizontal / vertical stripes. The domain transform (gain, brightness, colour cast,
    blur, noise) is applied with the same RNG so the output is reproducible byte for byte.
    """
    pai = PAI(pai)
    rng = np.random.default_rng(_seed_from_sample_id(sample_id))
    t = np.arange(T, dtype=np.float64)[:, None, None, None]
    yy = np.linspace(-1.0, 1.0, H, dtype=np.float64)[None, :, None, None]
    xx = np.linspace(-1.0, 1.0, W, dtype=np.float64)[None, None, :, None]

    # Background gradient and a face-like blob with a skin-ish colour.
    bg = 0.35 + 0.15 * (0.5 * yy + 0.5 * xx) + np.zeros((1, 1, 1, 3))
    cx, cy = rng.uniform(-0.25, 0.25, size=2)
    sigma = rng.uniform(0.35, 0.55)
    skin = np.array([0.85, 0.65, 0.55]) + rng.normal(0.0, 0.04, size=3)

    if pai == PAI.none:
        drift = 0.08 * np.sin(2.0 * np.pi * t / max(T, 1) + rng.uniform(0.0, 2.0 * np.pi))
        cxt, cyt = cx + drift, cy + 0.5 * drift
        illum = 1.0 + 0.03 * np.sin(2.0 * np.pi * t / max(T, 1))
    else:
        cxt, cyt = cx + 0.0 * t, cy + 0.0 * t
        illum = np.ones_like(t)

    blob = np.exp(-(((xx - cxt) ** 2) + ((yy - cyt) ** 2)) / (2.0 * sigma**2))
    img = bg * (1.0 - blob) + blob * skin[None, None, None, :]
    img = img * illum

    if pai == PAI.print:
        checker = ((np.arange(H)[:, None] + np.arange(W)[None, :]) % 2).astype(np.float64)
        img = img + 0.06 * (checker[None, :, :, None] - 0.5)
        img = img + rng.normal(0.0, 0.01, size=(1, H, W, 1))  # static paper texture
    elif pai in (PAI.replay_phone, PAI.replay, PAI.replay_display, PAI.display):
        flicker = 1.0 + 0.10 * np.sin(2.0 * np.pi * 0.25 * t)
        stripes = 0.05 * np.sin(2.0 * np.pi * np.arange(H) / 3.0)[None, :, None, None]
        img = img * flicker + stripes
    elif pai == PAI.replay_tablet:
        flicker = 1.0 + 0.08 * np.sin(2.0 * np.pi * 0.125 * t)
        stripes = 0.05 * np.sin(2.0 * np.pi * np.arange(W) / 5.0)[None, None, :, None]
        img = img * flicker + stripes
    else:  # mask_3d / other: rigid, slightly desaturated blob
        gray = img.mean(axis=-1, keepdims=True)
        img = 0.5 * img + 0.5 * gray

    # Domain transform.
    img = img * domain.gain + domain.brightness + np.asarray(domain.color_cast)[None, None, None, :]
    img = _box_blur(img, domain.blur)
    img = img + rng.normal(0.0, domain.noise_std, size=img.shape)
    return np.clip(np.round(img * 255.0), 0, 255).astype(np.uint8)


class SyntheticAdapter(DatasetAdapter):
    """Generates a subject-disjoint synthetic dataset and writes its clips under ``root``."""

    adapter_name = "synthetic"
    version = "1.0"
    license = "synthetic-cc0"
    pii_policy = "synthetic"
    temporal_valid = True

    def __init__(
        self,
        dataset_id: str,
        n_subjects: int = 20,
        clips_per_subject: int = 8,
        num_frames: int = 16,
        size: tuple[int, int] = (32, 32),
        fps: float = 30.0,
        split_ratio: tuple[float, float, float] = (0.6, 0.2, 0.2),
        subject_offset: int | None = None,
        domain: SyntheticDomain | None = None,
    ) -> None:
        self.dataset_id = dataset_id.lower()
        if domain is None:
            if self.dataset_id not in SYN_DOMAINS:
                raise ValueError(
                    f"no synthetic domain defined for {self.dataset_id!r}; "
                    f"known: {sorted(SYN_DOMAINS)} (or pass domain=...)"
                )
            domain = SYN_DOMAINS[self.dataset_id]
        self.domain = domain
        if n_subjects < 3:
            raise ValueError("n_subjects must be >= 3 so every split has a subject")
        if clips_per_subject < 1:
            raise ValueError("clips_per_subject must be >= 1")
        if abs(sum(split_ratio) - 1.0) > 1e-9:
            raise ValueError(f"split_ratio must sum to 1, got {split_ratio}")
        self.n_subjects = n_subjects
        self.clips_per_subject = clips_per_subject
        self.num_frames = num_frames
        self.size = (int(size[0]), int(size[1]))
        self.fps = fps
        self.split_ratio = split_ratio
        self.subject_offset = (
            SYN_SUBJECT_OFFSETS.get(self.dataset_id, 0)
            if subject_offset is None
            else subject_offset
        )

    def split_of_index(self, index: int) -> Split:
        """Subject-disjoint split: first 60% train, next 20% dev, rest test (by index)."""
        n_train = int(self.n_subjects * self.split_ratio[0] + 1e-9)
        n_dev = int(self.n_subjects * self.split_ratio[1] + 1e-9)
        n_train = max(1, n_train)
        n_dev = max(1, n_dev)
        if n_train + n_dev >= self.n_subjects:
            n_train, n_dev = self.n_subjects - 2, 1
        if index < n_train:
            return Split.train
        if index < n_train + n_dev:
            return Split.dev
        return Split.test

    @staticmethod
    def pai_of_clip(clip: int) -> PAI:
        return _PAI_PATTERN[clip % len(_PAI_PATTERN)]

    def sample_id(self, subject: int, clip: int, pai: PAI) -> str:
        return f"{self.dataset_id}_s{subject:03d}_c{clip:02d}_{pai.value}"

    def _write_clip(self, path: Path, clip: npt.NDArray[np.uint8]) -> None:
        """Save ``clip`` with ``np.save`` only when the file is missing or differs."""
        if path.is_file():
            try:
                existing = np.load(path)
                if (
                    existing.shape == clip.shape
                    and existing.dtype == clip.dtype
                    and np.array_equal(existing, clip)
                ):
                    return
            except (OSError, ValueError):
                pass
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".npy.tmp")
        with tmp.open("wb") as fh:
            np.save(fh, clip)
        tmp.replace(path)

    def build(self, root: Path) -> list[ManifestRecord]:
        n_frames = self.num_frames
        height, width = self.size
        device = f"synthetic_cam_{self.dataset_id.removeprefix('synthetic_')}"
        records: list[ManifestRecord] = []
        for index in range(self.n_subjects):
            subject = self.subject_offset + index
            split = self.split_of_index(index)
            subject_id = f"subj{subject:04d}"
            for clip_index in range(self.clips_per_subject):
                pai = self.pai_of_clip(clip_index)
                sample_id = self.sample_id(subject, clip_index, pai)
                relative_path = f"{self.dataset_id}/{sample_id}.npy"
                clip = generate_clip(sample_id, pai, self.domain, n_frames, height, width)
                self._write_clip(Path(root) / relative_path, clip)
                records.append(
                    ManifestRecord(
                        dataset_id=self.dataset_id,
                        sample_id=sample_id,
                        subject_id=subject_id,
                        split=split,
                        label=Label.bona_fide if pai == PAI.none else Label.spoof,
                        pai=pai,
                        pai_detail=None,
                        relative_path=relative_path,
                        media_type=MediaType.npy_clip,
                        fps=self.fps,
                        n_frames=n_frames,
                        width=width,
                        height=height,
                        capture_device=device,
                        session="s01",
                        environment="synthetic",
                        official_protocol=None,
                        extra={"clip_index": clip_index, "subject_index": index},
                    )
                )
        return records
