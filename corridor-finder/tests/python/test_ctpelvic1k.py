import numpy as np
import pytest

from corridor_engine import segmentation as seg
from corridor_engine.ctpelvic1k import (
    METAL_HU,
    CaseRefused,
    MetalInScan,
    load_case,
    remap_labels,
)
from corridor_engine.volume import Volume

SPACING = (2.0, 2.0, 2.0)
ORIGIN = (-100.0, -60.0, 0.0)  # x runs -100..+98 mm, so the midline is near x = 0


def _ctpelvic1k(id_on_patient_right=3, hip_x_mm=70.0):
    """Four blocks laid out like a pelvis in CTPelvic1K's ids: the sacrum on
    the midline, the lumbar spine above it, and a hip either side, with the
    hip on the patient's right (+x) carrying ``id_on_patient_right``."""
    array = np.zeros((50, 60, 100), dtype=np.uint8)
    x = ORIGIN[0] + np.arange(100) * SPACING[0]
    z = ORIGIN[2] + np.arange(50) * SPACING[2]
    sacrum = np.abs(x) < 20
    array[np.ix_((z > 30) & (z < 60), np.arange(20, 40), np.flatnonzero(sacrum))] = 1
    array[np.ix_((z > 64) & (z < 90), np.arange(20, 40), np.flatnonzero(np.abs(x) < 15))] = 4
    left_id = 2 if id_on_patient_right == 3 else 3
    for hip_id, sign in ((id_on_patient_right, 1.0), (left_id, -1.0)):
        cols = np.flatnonzero(np.abs(x - sign * hip_x_mm) < 20)
        array[np.ix_((z > 10) & (z < 70), np.arange(10, 50), cols)] = hip_id
    return Volume(array, SPACING, ORIGIN)


@pytest.mark.parametrize("id_on_patient_right", [3, 2], ids=["CLINIC convention", "ABDOMEN convention"])
def test_sides_come_from_geometry_under_either_convention(id_on_patient_right):
    """CLINIC puts id 3 on the patient's right; ABDOMEN and most of CERVIX
    put id 2 there. Both must come out with HIP_R on the patient's right."""
    source = _ctpelvic1k(id_on_patient_right)
    labels, ids, note = remap_labels(source)

    x = ORIGIN[0] + np.arange(100) * SPACING[0]
    right_x = x[np.nonzero(labels.array == seg.HIP_R)[2]].mean()
    left_x = x[np.nonzero(labels.array == seg.HIP_L)[2]].mean()
    assert right_x > 40 and left_x < -40
    assert ids["right"] == id_on_patient_right
    assert f"right hip is id {id_on_patient_right}" in note


def test_sacrum_is_never_mapped_onto_the_engines_left_hip():
    """CTPelvic1K's sacrum is id 1, which is the engine's HIP_L. Read as-is,
    the sacrum would become the left hip."""
    source = _ctpelvic1k()
    labels, _, _ = remap_labels(source)
    assert np.array_equal(labels.array == seg.SACRUM, source.array == 1)
    assert not np.any((labels.array == seg.HIP_L) & (source.array == 1))
    # And the lumbar spine (id 4) is not the engine's left femur (also 4).
    assert np.array_equal(labels.array == seg.LUMBAR, source.array == 4)
    assert not np.any(labels.array == seg.FEMUR_L)


def test_lumbar_does_not_collide_with_any_engine_id():
    assert seg.LUMBAR not in (seg.HIP_L, seg.HIP_R, seg.SACRUM, seg.FEMUR_L, seg.FEMUR_R)


def test_hips_on_the_same_side_are_refused():
    source = _ctpelvic1k()
    array = source.array.copy()
    array[array == 2] = 0
    x = ORIGIN[0] + np.arange(100) * SPACING[0]
    array[np.ix_(np.arange(10, 30), np.arange(10, 50), np.flatnonzero(np.abs(x - 30) < 5))] = 2
    with pytest.raises(CaseRefused, match="not one on each side"):
        remap_labels(Volume(array, SPACING, ORIGIN))


def test_a_missing_hip_or_an_unknown_id_is_refused():
    source = _ctpelvic1k()
    no_hip = source.array.copy()
    no_hip[no_hip == 3] = 0
    with pytest.raises(CaseRefused, match="missing"):
        remap_labels(Volume(no_hip, SPACING, ORIGIN))
    extra = source.array.copy()
    extra[0, 0, 0] = 7
    with pytest.raises(CaseRefused, match="not CTPelvic1K's four"):
        remap_labels(Volume(extra, SPACING, ORIGIN))


nib = pytest.importorskip("nibabel", reason="nibabel is a development dependency (requirements-dev.txt)")


def _save(tmp_path, name, array_zyx, spacing=SPACING, origin=ORIGIN):
    affine = np.diag([spacing[0], spacing[1], spacing[2], 1.0])
    affine[:3, 3] = origin
    path = tmp_path / name
    nib.save(nib.Nifti1Image(np.ascontiguousarray(np.transpose(array_zyx, (2, 1, 0))), affine), str(path))
    return str(path)


def _ct_for(labels_zyx, metal_voxels=0):
    ct = np.full(labels_zyx.shape, -1000, dtype=np.int16)
    ct[:, 5:55, 5:95] = 40  # the body, symmetric about x = 0
    ct[labels_zyx > 0] = 700
    if metal_voxels:
        ct[20, 30, 50:50 + metal_voxels] = int(METAL_HU) + 500
    return ct


def test_load_case_reads_labels_and_ct_from_files(tmp_path):
    source = _ctpelvic1k(id_on_patient_right=2)
    case = load_case(_save(tmp_path, "mask.nii.gz", source.array),
                     _save(tmp_path, "data.nii.gz", _ct_for(source.array)))
    assert case.source_hip_ids == {"right": 2, "left": 3}
    assert case.ct is not None and case.ct.array.shape == case.labels.array.shape
    assert set(np.unique(case.labels.array)) == {0, seg.HIP_L, seg.HIP_R, seg.SACRUM, seg.LUMBAR}


def test_a_scan_with_metal_is_refused_with_its_volume_and_distance(tmp_path):
    source = _ctpelvic1k()
    labels = _save(tmp_path, "mask.nii.gz", source.array)
    with pytest.raises(MetalInScan, match=r"cm3 above 2500 HU, \d+ mm from the pelvic bones"):
        load_case(labels, _save(tmp_path, "metal.nii.gz", _ct_for(source.array, metal_voxels=20)))


def test_a_ct_off_the_label_grid_is_refused(tmp_path):
    source = _ctpelvic1k()
    with pytest.raises(CaseRefused, match="not on the label grid"):
        load_case(_save(tmp_path, "mask.nii.gz", source.array),
                  _save(tmp_path, "data.nii.gz", _ct_for(source.array)[:, :, :-2]))
