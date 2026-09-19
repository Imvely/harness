"""Tests for seeding helpers (torch imported lazily inside the helpers)."""

from __future__ import annotations

import random

import numpy as np

from pad_research.utils.seed import make_generator, seed_everything, worker_init_fn


def test_seed_everything_is_reproducible() -> None:
    import torch

    seed_everything(123)
    a = torch.randn(4)
    r1 = random.random()
    n1 = np.random.rand()
    seed_everything(123)
    b = torch.randn(4)
    r2 = random.random()
    n2 = np.random.rand()
    assert torch.equal(a, b)
    assert r1 == r2
    assert n1 == n2


def test_different_seeds_differ() -> None:
    import torch

    seed_everything(1)
    a = torch.randn(4)
    seed_everything(2)
    b = torch.randn(4)
    assert not torch.equal(a, b)


def test_make_generator() -> None:
    import torch

    g1, g2 = make_generator(7), make_generator(7)
    assert torch.equal(torch.randperm(10, generator=g1), torch.randperm(10, generator=g2))
    assert g1.device.type == "cpu"


def test_worker_init_fn_seeds_numpy_and_random() -> None:
    import torch

    torch.manual_seed(5)
    worker_init_fn(0)
    x1, y1 = np.random.rand(), random.random()
    torch.manual_seed(5)
    worker_init_fn(0)
    x2, y2 = np.random.rand(), random.random()
    assert x1 == x2 and y1 == y2
    torch.manual_seed(5)
    worker_init_fn(1)
    assert np.random.rand() != x1
