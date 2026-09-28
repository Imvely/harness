"""Tests for canonical JSON serialization and hashing."""

from __future__ import annotations

import math

import pytest

from pad_research.utils.canonical_json import canonical_json, sha256_text


def test_keys_are_sorted_recursively_and_compact() -> None:
    obj = {"b": 1, "a": {"z": [1, 2, {"y": 0, "x": 1}], "k": "v"}}
    assert canonical_json(obj) == '{"a":{"k":"v","z":[1,2,{"x":1,"y":0}]},"b":1}'


def test_key_order_does_not_change_output() -> None:
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_non_ascii_is_escaped() -> None:
    assert canonical_json({"k": "한글"}) == '{"k":"\\ud55c\\uae00"}'


def test_nan_and_inf_are_rejected() -> None:
    with pytest.raises(ValueError):
        canonical_json({"x": math.nan})
    with pytest.raises(ValueError):
        canonical_json([math.inf])


def test_sha256_text_is_stable() -> None:
    assert sha256_text("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sha256_text(canonical_json({"a": 1})) == sha256_text('{"a":1}')
