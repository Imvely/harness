"""Unit tests for Hydra-composed experiment specs and science/spec hashes."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pad_research.config.compose import compose_spec
from pad_research.config.schema import ExperimentSpec, SmokeLimits, science_hash, spec_hash

ROOT = Path(__file__).resolve().parents[2]
EXP_DIR = ROOT / "configs" / "exp"


def _compose(exp_name: str, *overrides: str) -> ExperimentSpec:
    _, spec = compose_spec([f"+exp={exp_name}", *overrides])
    return spec


def _spec_data(spec: ExperimentSpec) -> dict[str, Any]:
    return copy.deepcopy(spec.model_dump(mode="json"))


@pytest.mark.parametrize("path", sorted(EXP_DIR.glob("*.yaml")), ids=lambda p: p.stem)
def test_compose_each_exp_file_validates(path: Path) -> None:
    spec = _compose(path.stem)
    assert spec.experiment.id.startswith("exp_")
    assert spec.protocol.protocol_id
    assert spec.tracking.mlflow_experiment


def test_smoke_and_full_share_science_hash() -> None:
    smoke = _compose("syn_e02_video_source_only")
    full_data = _spec_data(smoke)
    full_data["execution"]["mode"] = "full"
    full_data["execution"]["allow_full_gpu_run"] = True
    full = ExperimentSpec.model_validate(full_data)
    assert science_hash(smoke) == science_hash(full)
    assert spec_hash(smoke) != spec_hash(full)


def test_science_hash_ignores_source_run_id_device_and_text_fields() -> None:
    spec = _compose("syn_e03_video_full_ft_bf_only")
    changed_data = _spec_data(spec)
    changed_data["experiment"]["title"] = "changed title"
    changed_data["experiment"]["hypothesis"] = "changed hypothesis"
    changed_data["experiment"]["parent_experiment_id"] = "exp_other"
    changed_data["adaptation"]["source_run_id"] = "mlflow-run-123"
    changed_data["adaptation"]["source_checkpoint"] = "checkpoints/source.pt"
    changed_data["training"]["device"] = "cuda"
    changed_data["training"]["num_workers"] = 8
    changed_data["evaluation"]["baseline_experiment_id"] = "exp_baseline"
    changed_data["evaluation"]["measure_latency"] = False
    changed = ExperimentSpec.model_validate(changed_data)
    assert science_hash(spec) == science_hash(changed)
    assert spec_hash(spec) != spec_hash(changed)


def test_spec_hash_machine_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAD_DATA_ROOT", "/tmp/pad_data_a")
    first = _compose("syn_e01_frame_source_only")
    monkeypatch.setenv("PAD_DATA_ROOT", "/tmp/pad_data_b")
    second = _compose("syn_e01_frame_source_only")
    assert science_hash(first) == science_hash(second)
    assert spec_hash(first) == spec_hash(second)


def test_adaptation_without_protocol_budget_rejected() -> None:
    spec = _compose("syn_e03_video_full_ft_bf_only")
    data = _spec_data(spec)
    data["protocol"]["target_adaptation"] = {
        "enabled": False,
        "supervision": "none",
        "shots_per_subject": None,
        "total_samples": None,
        "source_split": "train",
        "selection_seed": 0,
        "subject_disjoint_from_test": True,
    }
    with pytest.raises(ValidationError, match="ADAPTATION_WITHOUT_PROTOCOL_BUDGET"):
        ExperimentSpec.model_validate(data)


def test_draft_protocol_forces_smoke() -> None:
    spec = _compose("syn_e01_frame_source_only")
    data = _spec_data(spec)
    data["protocol"]["status"] = "draft"
    data["execution"]["mode"] = "full"
    data["execution"]["allow_full_gpu_run"] = True
    with pytest.raises(ValidationError, match="DRAFT_PROTOCOL_SMOKE_ONLY"):
        ExperimentSpec.model_validate(data)


def test_not_implemented_method_rejected() -> None:
    with pytest.raises(ValidationError, match="NOT_IMPLEMENTED_IN_PHASE0"):
        _compose("syn_e03_video_full_ft_bf_only", "adaptation=prototype")


def test_video_needs_frames() -> None:
    with pytest.raises(ValidationError, match="VIDEO_NEEDS_FRAMES"):
        _compose("syn_e02_video_source_only", "model.input.frames=1")


def test_smoke_limits_bounded() -> None:
    with pytest.raises(ValidationError):
        SmokeLimits(max_batches=21)
    with pytest.raises(ValidationError):
        SmokeLimits(max_epochs=2)
    with pytest.raises(ValidationError):
        SmokeLimits(max_eval_batches=21)


def test_section16_derived_fixture_validates() -> None:
    spec = _compose("syn_e01_frame_source_only")
    data = _spec_data(spec)
    data["data"]["source"] = ["synthetic_a"]
    data["data"]["target"] = ["synthetic_b"]
    derived = ExperimentSpec.model_validate(data)
    assert derived.data.source == ["synthetic_a"]
    assert derived.data.target == ["synthetic_b"]
