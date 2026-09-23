"""What each dataset calls an attack, and which PAI that is.

Every dataset names its attacks its own way: CASIA-SURF numbers its print cut-outs
(``01_e_s``), SiW-Mv2 spells them out (``Mask_TransparentMask``), Replay-Attack keeps the
instrument in a metadata field rather than in the class name. Per-PAI APCER is only comparable
across datasets once those names land on one vocabulary, and that translation is a research
judgement, so it lives here in one readable table rather than inside an adapter.

Two rules hold throughout:

* **Nothing is guessed.** A class name that is not in a table raises, so a dataset that grows a
  new attack type stops the build instead of quietly becoming ``other`` (contract section 27.2).
* **The original name survives.** Every record keeps its dataset's own label in ``pai_detail``,
  so a mapping decision can be re-read, and re-made, without rebuilding anything.
"""

from __future__ import annotations

from pad_research.data.manifest import PAI, Label

#: The raw class name a dataset uses for a bona fide clip, per dataset.
BONA_FIDE_CLASSES: dict[str, frozenset[str]] = {
    "casia_cefa": frozenset({"Real"}),
    "casia_surf": frozenset({"real"}),
    "idiap_replayattack": frozenset({"real"}),
    "siw_mv2": frozenset({"Live"}),
    "aihub114": frozenset({"real_01_phone"}),
    "aihub115": frozenset({"real_01"}),
}

#: Attack class name -> PAI. Idiap is absent: its class is the support (hand/fixed), and the
#: instrument is in the metadata, so it is resolved by :func:`idiap_pai` instead.
ATTACK_CLASSES: dict[str, dict[str, PAI]] = {
    # Protocol 2.2 ships one attack type, a video replayed on a screen.
    "casia_cefa": {"Screen": PAI.replay},
    # Printed faces with cut-outs (eyes / eyes+nose / eyes+nose+mouth), flat or curved. The
    # distinction is the cut-out, not the instrument: all six are paper.
    "casia_surf": {
        "01_e_s": PAI.print,
        "02_e_b": PAI.print,
        "03_en_s": PAI.print,
        "04_en_b": PAI.print,
        "05_enm_s": PAI.print,
        "06_enm_b": PAI.print,
    },
    "siw_mv2": {
        "Replay": PAI.replay,
        "Paper": PAI.print,
        "Mask_HalfMask": PAI.mask_3d,
        "Mask_TransparentMask": PAI.mask_transparent,
        "Mask_PaperMask": PAI.mask_paper,
        "Silicone": PAI.mask_silicone,
        "Mannequin": PAI.mannequin,
        "Makeup_Impersonation": PAI.makeup,
        "Makeup_Obfuscation": PAI.makeup,
        "Makeup_Cosmetic": PAI.makeup,
        "Partial_Eye": PAI.partial,
        "Partial_Mouth": PAI.partial,
        "Partial_FunnyeyeGlasses": PAI.partial,
        "Partial_PaperGlasses": PAI.partial,
    },
    "aihub114": {
        "attack_01_print_none_flat": PAI.print,
        "attack_02_print_eye_nose_mouth_flat": PAI.print,
        "attack_03_replay_phone": PAI.replay_phone,
        "attack_04_replay_tablet": PAI.replay_tablet,
        "attack_05_3d_mask": PAI.mask_3d,
    },
    # Six print cut-outs in the source tree. The lab's store holds four of them: its build
    # skipped attack_03 and attack_04, which our own build includes (ADR-016).
    "aihub115": {
        "attack_01_print_eye_flat": PAI.print,
        "attack_02_print_eye_curved": PAI.print,
        "attack_03_print_eye_nose_flat": PAI.print,
        "attack_04_print_eye_nose_curved": PAI.print,
        "attack_05_print_eye_nose_mouth_flat": PAI.print,
        "attack_06_print_eye_nose_mouth_curved": PAI.print,
    },
}


class PaiMappingError(KeyError):
    """A dataset used a class name the table does not cover."""


def idiap_pai(device: str, media: str | None) -> PAI:
    """Replay-Attack: the class is the support, so the instrument comes from the metadata.

    ``device`` is how the face was presented (``print``, ``mobile``, ``highdef``) and ``media``
    whether it was a still or a video. A still shown on a screen is not a replay — nothing
    moves — so it maps to ``display``; only a played video is a replay.
    """
    if device == "print":
        return PAI.print
    if media == "photo":
        return PAI.display
    if device == "mobile":
        return PAI.replay_phone
    if device == "highdef":
        return PAI.replay_display
    raise PaiMappingError(f"idiap_replayattack: unmapped device {device!r} / media {media!r}")


def pai_for(
    dataset_id: str, class_name: str, extra: dict[str, object] | None = None
) -> tuple[Label, PAI]:
    """Return ``(label, pai)`` for one clip, or raise when the class name is unknown."""
    extra = extra or {}
    bona_fide = BONA_FIDE_CLASSES.get(dataset_id)
    if bona_fide is None:
        raise PaiMappingError(f"no PAI table for dataset {dataset_id!r}")
    if class_name in bona_fide:
        return Label.bona_fide, PAI.none
    if dataset_id == "idiap_replayattack":
        device = extra.get("device")
        media = extra.get("media_type")
        if not isinstance(device, str):
            raise PaiMappingError("idiap_replayattack: a clip carries no device in extra_meta")
        return Label.spoof, idiap_pai(device, media if isinstance(media, str) else None)
    try:
        return Label.spoof, ATTACK_CLASSES[dataset_id][class_name]
    except KeyError as exc:
        known = sorted(ATTACK_CLASSES.get(dataset_id, {}))
        raise PaiMappingError(
            f"{dataset_id}: no PAI for class {class_name!r}; known attack classes: {known}"
        ) from exc


__all__ = [
    "ATTACK_CLASSES",
    "BONA_FIDE_CLASSES",
    "PaiMappingError",
    "idiap_pai",
    "pai_for",
]
