import numpy as np

from corridor_engine.edt import bone_edt_mm
from corridor_engine.phantoms import solid_rod
from corridor_engine.validate import validate_screw
from corridor_engine.volume import Volume

SPACING = (1.0, 1.0, 1.0)
SHAPE = (60, 60, 120)


def _rod_volumes(radius_mm=8.0):
    mask = solid_rod(shape=SHAPE, radius_mm=radius_mm)
    edt = bone_edt_mm(mask, SPACING)
    edt_vol = Volume(edt, SPACING)
    labels = mask.astype(np.uint8)
    labels_vol = Volume(labels, SPACING)
    return edt_vol, labels_vol


def test_centered_axis_is_safe():
    edt_vol, labels_vol = _rod_volumes(radius_mm=8.0)
    entry = edt_vol.ijk_to_world((5, 30, 30))
    target = edt_vol.ijk_to_world((115, 30, 30))
    result = validate_screw(entry, target, diameter_mm=6.5, margin_mm=2.0, edt_volume=edt_vol, labels_volume=labels_vol)
    assert not result.breach
    assert result.min_clearance_mm > 0
    assert 1 in result.traversed_labels


def test_oversized_screw_breaches():
    edt_vol, labels_vol = _rod_volumes(radius_mm=8.0)
    entry = edt_vol.ijk_to_world((5, 30, 30))
    target = edt_vol.ijk_to_world((115, 30, 30))
    result = validate_screw(entry, target, diameter_mm=16.0, margin_mm=2.0, edt_volume=edt_vol, labels_volume=labels_vol)
    assert result.breach


def test_axis_outside_bone_breaches():
    edt_vol, labels_vol = _rod_volumes(radius_mm=8.0)
    # Off-axis line that misses the rod entirely (rod is centered at y=30,z=30)
    entry = edt_vol.ijk_to_world((5, 55, 55))
    target = edt_vol.ijk_to_world((115, 55, 55))
    result = validate_screw(entry, target, diameter_mm=3.5, margin_mm=2.0, edt_volume=edt_vol, labels_volume=labels_vol)
    assert result.breach
    assert result.traversed_labels == []
