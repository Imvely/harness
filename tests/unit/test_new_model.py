"""Starting a new composition: what it refuses, what it writes, and what it admits is missing."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def load() -> ModuleType:
    """Import the script by path: `scripts/` is not a package, and it must not need to be."""
    spec = importlib.util.spec_from_file_location(
        "new_model", REPO_ROOT / "scripts" / "new_model.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


new_model = load()


def comp(**overrides: object):
    values: dict[str, object] = {
        "id": "x3d_m_mean",
        "backbone": "pytorchvideo:x3d_m",
        "temporal": "none",
        "head": "linear",
        "frames": 16,
    }
    values.update(overrides)
    return new_model.composition(**values)  # type: ignore[arg-type]


# -- the parts ------------------------------------------------------------------------


def test_a_backbone_must_say_where_it_comes_from() -> None:
    assert new_model.parse_backbone("timm:resnet18") == ("timm", "resnet18")
    for bad in ("resnet18", "timm:", ":resnet18", "nowhere:resnet18"):
        with pytest.raises(new_model.CompositionError):
            new_model.parse_backbone(bad)


def test_a_reference_a_loader_would_not_accept_is_refused() -> None:
    """The ref reaches a loader and a config file, so a space or a quote in it stops here."""
    for bad in ("timm:rm -rf /", 'timm:res"net', "timm:$(whoami)"):
        with pytest.raises(new_model.CompositionError, match="characters"):
            new_model.parse_backbone(bad)


def test_an_id_must_be_usable_as_a_file_name() -> None:
    for bad in ("X3D", "3d_model", "x3d-m", "x3d m", ""):
        with pytest.raises(new_model.CompositionError, match="--id"):
            comp(id=bad)
    assert comp(id="x3d_m2").id == "x3d_m2"


def test_frames_outside_the_supported_range_are_refused() -> None:
    for bad in (0, -1, 65):
        with pytest.raises(new_model.CompositionError, match="--frames"):
            comp(frames=bad)


# -- the composition checks, which match the UI's ------------------------------------


def test_a_frame_backbone_fed_several_frames_needs_a_temporal_step() -> None:
    """Otherwise it trains on frame one and silently discards the rest."""
    found = new_model.problems(comp(backbone="timm:resnet18", frames=8, temporal="none"))
    assert len(found) == 1
    assert "first frame" in found[0]
    assert new_model.problems(comp(backbone="timm:resnet18", frames=8, temporal="mean")) == []
    assert new_model.problems(comp(backbone="timm:resnet18", frames=1, temporal="none")) == []


def test_pooling_on_top_of_a_clip_backbone_is_refused() -> None:
    found = new_model.problems(comp(backbone="pytorchvideo:x3d_m", temporal="mean"))
    assert "flatten" in found[0]
    # Attention over its frame features is a real choice, not a redundancy.
    assert new_model.problems(comp(backbone="pytorchvideo:x3d_m", temporal="attention")) == []


def test_a_pixelwise_head_after_pooling_is_refused() -> None:
    found = new_model.problems(
        comp(backbone="timm:resnet18", frames=8, temporal="mean", head="pixelwise")
    )
    assert any("spatial map" in problem for problem in found)
    assert new_model.problems(comp(backbone="timm:resnet18", frames=1, head="pixelwise")) == []


# -- what it writes -------------------------------------------------------------------


def test_the_config_names_the_composition_and_carries_no_measurement() -> None:
    text = new_model.config_text(
        comp(backbone="timm:resnet18", frames=8, temporal="mean", head="mlp")
    )
    assert "family: composed" in text
    assert "backbone_source: timm" in text
    assert "backbone_ref: resnet18" in text
    assert "temporal: mean" in text
    assert "head: mlp" in text
    assert "frames: 8" in text
    assert new_model.COMPOSED_TARGET in text
    # It says what it is: a starting point, not a result.
    assert "not measurements" in text


def test_it_writes_nothing_without_being_asked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "configs" / "model").mkdir(parents=True)
    code = new_model.main(
        [
            "--id",
            "x3d_m_mean",
            "--backbone",
            "pytorchvideo:x3d_m",
            "--frames",
            "16",
            "--root",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert list((tmp_path / "configs" / "model").iterdir()) == []
    out = capsys.readouterr().out
    assert "not written" in out
    assert "still needed before a run can use it" in out


def test_writing_creates_the_config_and_refuses_to_replace_one(tmp_path: Path) -> None:
    args = [
        "--id",
        "x3d_m",
        "--backbone",
        "pytorchvideo:x3d_m",
        "--frames",
        "16",
        "--root",
        str(tmp_path),
        "--write",
    ]
    assert new_model.main(args) == 0
    path = tmp_path / "configs" / "model" / "x3d_m.yaml"
    assert "backbone_ref: x3d_m" in path.read_text(encoding="utf-8")
    assert new_model.main(args) == 4
    assert new_model.main([*args, "--force"]) == 0


def test_a_composition_that_cannot_train_exits_before_writing(tmp_path: Path) -> None:
    code = new_model.main(
        [
            "--id",
            "bad",
            "--backbone",
            "timm:resnet18",
            "--frames",
            "8",
            "--root",
            str(tmp_path),
            "--write",
        ]
    )
    assert code == 3
    assert not (tmp_path / "configs").exists()


def test_the_caller_can_say_whether_a_backbone_reads_time() -> None:
    """A hub source holds image and video models, so guessing from the source is not enough."""
    hub_video = comp(backbone="huggingface:MCG-NJU/videomae-base", frames=16, reads_clip="yes")
    assert hub_video.reads_clip is True
    assert new_model.problems(hub_video) == []
    # Told it reads a clip, pooling on top is refused just as for pytorchvideo.
    assert new_model.problems(
        comp(backbone="huggingface:MCG-NJU/videomae-base", temporal="mean", reads_clip="yes")
    )
    # Told it reads one frame, several frames now need a temporal step.
    assert new_model.problems(
        comp(backbone="huggingface:owner/img-model", frames=8, reads_clip="no")
    )
    with pytest.raises(new_model.CompositionError, match="--reads-clip"):
        comp(reads_clip="maybe")


def test_the_checklist_reports_what_this_repository_really_has() -> None:
    """It must not claim the model class exists while it does not."""
    items = new_model.checklist(comp(), REPO_ROOT)
    assert len(items) == 4
    composed = REPO_ROOT / "src" / "pad_research" / "models" / "composed.py"
    assert items[0][0] is composed.is_file()
    assert "composed.py" in items[0][1]
    # Every item names a file or a place, so it can be done without guessing.
    assert all(len(text) > 20 for _, text in items)
