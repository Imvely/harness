"""Unit tests for PAD loss and score conventions (spoof = 1, score = sigmoid)."""

from __future__ import annotations

import torch
import torch.nn.functional as F  # noqa: N812

from pad_research.conventions import LABEL_BONA_FIDE, LABEL_SPOOF
from pad_research.losses.pad_loss import attack_score, bce_pad_loss

torch.set_num_threads(1)


def test_bce_pad_loss_convention() -> None:
    logits = torch.tensor([-2.0, 0.0, 2.0])
    spoof = torch.full((3,), float(LABEL_SPOOF))
    bona = torch.full((3,), float(LABEL_BONA_FIDE))
    spoof_losses = [bce_pad_loss(logits[i : i + 1], spoof[i : i + 1]).item() for i in range(3)]
    bona_losses = [bce_pad_loss(logits[i : i + 1], bona[i : i + 1]).item() for i in range(3)]
    assert spoof_losses[0] > spoof_losses[1] > spoof_losses[2]
    assert bona_losses[0] < bona_losses[1] < bona_losses[2]


def test_bce_pad_loss_matches_torch_and_accepts_int_labels() -> None:
    torch.manual_seed(0)
    logits = torch.randn(6)
    labels = torch.tensor([0, 1, 1, 0, 1, 0])
    expected = F.binary_cross_entropy_with_logits(logits, labels.float())
    torch.testing.assert_close(bce_pad_loss(logits, labels), expected)
    assert bce_pad_loss(logits, labels).ndim == 0


def test_attack_score_sigmoid() -> None:
    logits = torch.tensor([-3.0, 0.0, 3.0])
    score = attack_score(logits)
    torch.testing.assert_close(score, torch.sigmoid(logits))
    assert score[1].item() == 0.5
    assert torch.all((score >= 0) & (score <= 1))
    assert torch.all(score[1:] > score[:-1])  # monotone: higher logit = more spoof-like
