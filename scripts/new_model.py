#!/usr/bin/env python3
"""Start a new model composition: write its config, and say what is still missing.

Trying an architecture published last week should not be a project. The parts of that are
already here — a config directory, a model registry, a shape contract — and what is missing is
the boring half: a config file naming the composition, and an honest list of what has to exist
before a run can use it. This writes the first and prints the second.

It does **not** generate a model implementation. A generated `nn.Module` nobody read is worse
than no model at all: it would import, train, and produce numbers whose meaning nobody checked.
So the output is a config plus a checklist, and the checklist is what `--write` cannot do for
you.

    # see what would be written
    python scripts/new_model.py --id x3d_m_mean --backbone pytorchvideo:x3d_m --frames 16

    # write configs/model/x3d_m_mean.yaml
    python scripts/new_model.py --id x3d_m_mean --backbone pytorchvideo:x3d_m --frames 16 --write

The composition rules are the same ones the setup UI checks, deliberately: a rule that holds in
one place and not the other is a rule that will be broken in the other.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Where a backbone can come from, and what `ref` means for each.
SOURCES: dict[str, str] = {
    "timm": "a timm model name, e.g. resnet18 or vit_base_patch16_224",
    "huggingface": "a hub id, e.g. MCG-NJU/videomae-base",
    "torchvision": "a torchvision factory, e.g. r2plus1d_18",
    "pytorchvideo": "a pytorchvideo hub entry, e.g. x3d_m",
    "local": "a dotted path to a class in this repository",
}
#: What happens to the time axis between backbone and head.
TEMPORAL_OPS = ("none", "mean", "max", "diff", "lstm", "attention")
#: What the head predicts.
HEADS = ("linear", "mlp", "pixelwise", "prototype")
#: Backbones that read a clip themselves, so a pooling step on top would flatten their output.
CLIP_SOURCES = frozenset({"pytorchvideo"})

ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]*$")
#: The class a composition config instantiates. It does not exist yet; that is item 1 of the
#: checklist, and naming it here is what makes the checklist checkable.
COMPOSED_TARGET = "pad_research.models.composed.ComposedModel"


class CompositionError(ValueError):
    """The composition cannot be written: a bad name, or a combination that cannot train."""


@dataclass(frozen=True)
class Composition:
    """One model: a backbone, what happens to time, and what the head predicts."""

    id: str
    source: str
    ref: str
    temporal: str
    head: str
    frames: int
    #: Whether the backbone consumes the time axis itself. ``None`` means "decide from the
    #: source", which is only a guess — a hub holds both image and video models, so the caller
    #: that knows (the setup UI does) says so explicitly.
    clip_backbone: bool | None = None

    @property
    def reads_clip(self) -> bool:
        """True when the backbone consumes the time axis itself."""
        if self.clip_backbone is not None:
            return self.clip_backbone
        return self.source in CLIP_SOURCES


def parse_backbone(value: str) -> tuple[str, str]:
    """Split ``source:ref``. A missing source is an error rather than a guess."""
    source, _, ref = value.partition(":")
    if not _ or not ref:
        raise CompositionError(
            f"--backbone must be source:ref, got {value!r} (sources: {sorted(SOURCES)})"
        )
    if source not in SOURCES:
        raise CompositionError(f"unknown backbone source {source!r}; one of {sorted(SOURCES)}")
    if not REF_RE.fullmatch(ref):
        raise CompositionError(
            f"the backbone reference {ref!r} has characters a loader would not accept; "
            "use a hub id, a factory name or a dotted path"
        )
    return source, ref


def composition(
    *,
    id: str,
    backbone: str,
    temporal: str,
    head: str,
    frames: int,
    reads_clip: str = "auto",
) -> Composition:
    """Validate the parts and return the composition, or raise with what is wrong."""
    if not ID_RE.fullmatch(id):
        raise CompositionError(f"--id {id!r} must match {ID_RE.pattern} (it becomes a file name)")
    if temporal not in TEMPORAL_OPS:
        raise CompositionError(f"--temporal must be one of {list(TEMPORAL_OPS)}")
    if head not in HEADS:
        raise CompositionError(f"--head must be one of {list(HEADS)}")
    if not 1 <= frames <= 64:
        raise CompositionError("--frames must be between 1 and 64")
    if reads_clip not in ("auto", "yes", "no"):
        raise CompositionError("--reads-clip must be auto, yes or no")
    source, ref = parse_backbone(backbone)
    return Composition(
        id=id,
        source=source,
        ref=ref,
        temporal=temporal,
        head=head,
        frames=frames,
        clip_backbone=None if reads_clip == "auto" else reads_clip == "yes",
    )


def problems(comp: Composition) -> list[str]:
    """Reasons this composition would not do what it looks like it does.

    The same three checks the setup UI runs, so a composition accepted there is accepted here.
    """
    found: list[str] = []
    if not comp.reads_clip and comp.frames > 1 and comp.temporal == "none":
        found.append(
            "a backbone that reads one frame is being given several with no temporal step: "
            "it would train on the first frame and discard the rest. Pick --temporal, or --frames 1."
        )
    if comp.reads_clip and comp.temporal in {"mean", "max", "diff", "lstm"}:
        found.append(
            f"{comp.ref} consumes the time axis itself, so --temporal {comp.temporal} would flatten "
            "what it computed. Use none, or attention over its frame features."
        )
    if comp.head == "pixelwise" and (comp.reads_clip or comp.temporal != "none"):
        found.append(
            "a pixel-wise head supervises a spatial map, and pooling has already removed the "
            "positions it would supervise."
        )
    return found


def config_text(comp: Composition) -> str:
    """The ``configs/model/<id>.yaml`` this composition stands for."""
    return f"""# {comp.id}: {comp.source}:{comp.ref} -> {comp.temporal} -> {comp.head}.
# Written by scripts/new_model.py. Review it before a run uses it: the numbers below are
# starting points, not measurements.
family: composed
checkpoint: null
input:
  modality: rgb
  frames: {comp.frames}
  frame_sampling: uniform
  image_size: [224, 224]
net:
  _target_: {COMPOSED_TARGET}
  backbone_source: {comp.source}
  backbone_ref: {comp.ref}
  pretrained: true
  temporal: {comp.temporal}
  head: {comp.head}
  dropout: 0.0
"""


def checklist(comp: Composition, root: Path) -> list[tuple[bool, str]]:
    """What exists and what does not, in the order it has to be done."""
    composed_module = root / "src" / "pad_research" / "models" / "composed.py"
    test_file = root / "tests" / "unit" / "test_models_composed.py"
    registry = root / "src" / "pad_research" / "models" / "registry.py"
    registry_text = registry.read_text(encoding="utf-8") if registry.is_file() else ""
    return [
        (
            composed_module.is_file(),
            f"{composed_module.relative_to(root).as_posix()} — the PADModel that builds a "
            "composition (clip in, ModelOutput out; encoder and head parameter groups apart)",
        ),
        (
            "composed" in registry_text,
            "models/registry.py — register the 'composed' family so build_model can reach it",
        ),
        (
            f"{comp.source}" in composed_module.read_text(encoding="utf-8")
            if composed_module.is_file()
            else False,
            f"a loader for {comp.source} backbones ({SOURCES[comp.source]}), imported lazily so "
            "the package still imports without that library",
        ),
        (
            test_file.is_file(),
            f"{test_file.relative_to(root).as_posix()} — a shape test: (B, T, 3, H, W) in, "
            "logits (B,) and clip_embedding (B, D) out",
        ),
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--id", required=True, help="config name; becomes configs/model/<id>.yaml")
    parser.add_argument("--backbone", required=True, help="source:ref, e.g. timm:resnet18")
    parser.add_argument("--temporal", default="none", choices=list(TEMPORAL_OPS))
    parser.add_argument("--head", default="linear", choices=list(HEADS))
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument(
        "--reads-clip",
        default="auto",
        choices=["auto", "yes", "no"],
        help="whether the backbone consumes the time axis itself; auto guesses from the source",
    )
    parser.add_argument("--write", action="store_true", help="write the config file")
    parser.add_argument("--force", action="store_true", help="overwrite an existing config")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        comp = composition(
            id=args.id,
            backbone=args.backbone,
            temporal=args.temporal,
            head=args.head,
            frames=args.frames,
            reads_clip=args.reads_clip,
        )
    except CompositionError as error:
        print(f"{error}", file=sys.stderr)
        return 2

    found = problems(comp)
    if found:
        print("this composition would not do what it looks like:", file=sys.stderr)
        for problem in found:
            print(f"  - {problem}", file=sys.stderr)
        return 3

    text = config_text(comp)
    path = args.root / "configs" / "model" / f"{comp.id}.yaml"
    print(text)
    if args.write:
        if path.exists() and not args.force:
            print(f"{path} already exists; pass --force to replace it", file=sys.stderr)
            return 4
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(args.root).as_posix()}")
    else:
        print(
            f"# not written. Re-run with --write to create {path.relative_to(args.root).as_posix()}"
        )

    print("\nstill needed before a run can use it:")
    for done, item in checklist(comp, args.root):
        print(f"  [{'x' if done else ' '}] {item}")
    print(
        "\nThen: uv run --no-sync python scripts/validate_spec.py --exp <your exp> --for-launch\n"
        "A model with an unchecked implementation produces numbers nobody can defend, so the "
        "boxes above are the work, not the paperwork."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
