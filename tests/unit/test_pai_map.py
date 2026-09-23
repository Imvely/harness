"""Each dataset's own attack names, translated to one vocabulary."""

from __future__ import annotations

import pytest

from pad_research.data.manifest import PAI, PAI_FLAT, PAI_ON_FACE, PAI_THREE_D, Label
from pad_research.data.pai_map import (
    ATTACK_CLASSES,
    BONA_FIDE_CLASSES,
    PaiMappingError,
    pai_for,
)

# The class names measured in the lab's stores on 2026-09-22, per domain.
MEASURED_ATTACK_CLASSES = {
    "casia_cefa": {"Screen"},
    "casia_surf": {"01_e_s", "02_e_b", "03_en_s", "04_en_b", "05_enm_s", "06_enm_b"},
    "siw_mv2": {
        "Replay",
        "Paper",
        "Mask_HalfMask",
        "Mask_TransparentMask",
        "Mask_PaperMask",
        "Silicone",
        "Mannequin",
        "Makeup_Impersonation",
        "Makeup_Obfuscation",
        "Makeup_Cosmetic",
        "Partial_Eye",
        "Partial_Mouth",
        "Partial_FunnyeyeGlasses",
        "Partial_PaperGlasses",
    },
    "aihub114": {
        "attack_01_print_none_flat",
        "attack_02_print_eye_nose_mouth_flat",
        "attack_03_replay_phone",
        "attack_04_replay_tablet",
        "attack_05_3d_mask",
    },
    "aihub115": {
        "attack_01_print_eye_flat",
        "attack_02_print_eye_curved",
        "attack_05_print_eye_nose_mouth_flat",
        "attack_06_print_eye_nose_mouth_curved",
    },
}


def test_every_attack_class_in_the_stores_has_a_pai() -> None:
    # The build stops rather than guessing, so a class missing here fails the whole dataset.
    for dataset_id, classes in MEASURED_ATTACK_CLASSES.items():
        for class_name in classes:
            label, pai = pai_for(dataset_id, class_name)
            assert label == Label.spoof
            assert pai != PAI.none


def test_bona_fide_classes_map_to_no_instrument() -> None:
    for dataset_id, classes in BONA_FIDE_CLASSES.items():
        for class_name in classes:
            assert pai_for(dataset_id, class_name) == (Label.bona_fide, PAI.none)


def test_an_unknown_class_names_what_it_knows_instead_of_guessing() -> None:
    with pytest.raises(PaiMappingError, match="attack_09_new"):
        pai_for("aihub115", "attack_09_new")
    with pytest.raises(PaiMappingError, match="no PAI table"):
        pai_for("oulu_npu", "print")


@pytest.mark.parametrize(
    ("device", "media", "expected"),
    [
        ("print", "photo", PAI.print),
        ("mobile", "photo", PAI.display),
        ("highdef", "photo", PAI.display),
        ("mobile", "video", PAI.replay_phone),
        ("highdef", "video", PAI.replay_display),
    ],
)
def test_replay_attack_reads_the_instrument_from_its_metadata(
    device: str, media: str, expected: PAI
) -> None:
    # Its class name is the support (hand/fixed), not the instrument.
    label, pai = pai_for("idiap_replayattack", "hand", {"device": device, "media_type": media})
    assert (label, pai) == (Label.spoof, expected)


def test_replay_attack_without_a_device_is_an_error_not_a_default() -> None:
    with pytest.raises(PaiMappingError, match="device"):
        pai_for("idiap_replayattack", "fixed", {"media_type": "video"})


def test_the_groups_cover_every_attack_instrument_exactly_once() -> None:
    """The switch a protocol flips is a group, so the groups have to partition the attacks."""
    groups = [PAI_FLAT, PAI_THREE_D, PAI_ON_FACE]
    union = set().union(*groups)
    assert union | {PAI.none, PAI.other} == set(PAI)
    for left, right in ((0, 1), (0, 2), (1, 2)):
        assert not groups[left] & groups[right]


def test_the_stores_flat_attacks_are_the_ones_this_project_targets_first() -> None:
    flat = {
        pai_for(dataset_id, class_name)[1]
        for dataset_id, classes in MEASURED_ATTACK_CLASSES.items()
        for class_name in classes
    } & PAI_FLAT
    assert flat == {PAI.print, PAI.replay, PAI.replay_phone, PAI.replay_tablet}
    # SiW-Mv2 is where the three-dimensional and on-face instruments come from.
    siw = {pai_for("siw_mv2", name)[1] for name in MEASURED_ATTACK_CLASSES["siw_mv2"]}
    assert siw & PAI_THREE_D == {
        PAI.mask_3d,
        PAI.mask_transparent,
        PAI.mask_paper,
        PAI.mask_silicone,
        PAI.mannequin,
    }
    assert siw & PAI_ON_FACE == {PAI.makeup, PAI.partial}


def test_every_mapped_class_keeps_a_distinct_name_per_dataset() -> None:
    # A typo that duplicates a key would silently drop one mapping.
    for dataset_id, table in ATTACK_CLASSES.items():
        assert len(table) == len(MEASURED_ATTACK_CLASSES[dataset_id])
