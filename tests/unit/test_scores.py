"""ScoreTable construction, validation and CSV round trip."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from pad_research.evaluation.scores import ScoreTable


def _table() -> ScoreTable:
    return ScoreTable.from_arrays(
        "test",
        "target",
        ["a", "b", "c"],
        ["s1", "s1", "s2"],
        np.array([0.1, 1 / 3, 0.9]),
        np.array([0, 1, 1]),
        ["none", "print", "replay_phone"],
    )


def test_from_arrays_and_to_numpy() -> None:
    t = _table()
    assert t.n == 3
    assert t.role == "test" and t.domain == "target"
    score, y, pai = t.to_numpy()
    assert score.dtype == np.float64 and y.dtype == np.bool_
    assert score.tolist() == pytest.approx([0.1, 1 / 3, 0.9])
    assert y.tolist() == [False, True, True]
    assert pai == ["none", "print", "replay_phone"]
    assert t.y_attack == [False, True, True]


def test_length_validation() -> None:
    with pytest.raises(ValidationError):
        ScoreTable(
            role="dev",
            domain="source",
            sample_id=["a", "b"],
            subject_id=["s", "s"],
            score=[0.1],
            y_attack=[False, True],
            pai=["none", "print"],
        )
    with pytest.raises(ValidationError):
        ScoreTable.from_arrays("dev", "source", ["a"], ["s"], [0.1, 0.2], [False], ["none"])
    with pytest.raises(ValueError):
        ScoreTable.from_arrays("dev", "source", ["a"], ["s"], [0.1], [2], ["none"])
    with pytest.raises(ValidationError):
        ScoreTable.from_arrays("train", "source", ["a"], ["s"], [0.1], [False], ["none"])  # type: ignore[arg-type]


def test_csv_roundtrip(tmp_path: Path) -> None:
    t = _table()
    out = t.to_csv(tmp_path / "nested" / "scores.csv")
    assert out.exists()
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header == "role,domain,sample_id,subject_id,score,y_attack,pai"
    back = ScoreTable.from_csv(out)
    assert back == t  # exact: scores are written with repr()


def test_empty_table_allowed() -> None:
    t = ScoreTable(
        role="dev", domain="source", sample_id=[], subject_id=[], score=[], y_attack=[], pai=[]
    )
    assert t.n == 0
    score, y, pai = t.to_numpy()
    assert score.shape == (0,) and y.shape == (0,) and pai == []
