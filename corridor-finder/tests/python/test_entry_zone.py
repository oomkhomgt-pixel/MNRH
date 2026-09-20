import numpy as np

from corridor_engine.edt import bone_edt_mm
from corridor_engine.entry_zone import safe_entry_area
from corridor_engine.validate import validate_screw
from corridor_engine.volume import Volume

SPACING = (1.0, 1.0, 1.0)


def _rod(radius_mm=12.0, shape=(50, 50, 70)):
    """A cylinder of bone along x, centred in y and z."""
    nz, ny, nx = shape
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    mask = np.sqrt((zz - nz / 2.0) ** 2 + (yy - ny / 2.0) ** 2) <= radius_mm
    return Volume(bone_edt_mm(mask, SPACING), SPACING), Volume(mask.astype(np.uint8), SPACING)


def _slab_with_slot(slot_x=34):
    """A block of bone with a full-depth slot, as in test_validate."""
    zz, yy, xx = np.mgrid[0:60, 0:60, 0:70]
    mask = (xx >= 5) & (xx <= 64) & (yy >= 5) & (yy <= 54) & (zz >= 10) & (zz <= 40)
    mask &= ~((xx >= slot_x) & (xx <= slot_x + 2) & (zz >= 20))
    return Volume(bone_edt_mm(mask, SPACING), SPACING), Volume(mask.astype(np.uint8), SPACING)


def test_room_in_a_rod_is_the_rod_minus_the_screws_envelope():
    edt, labels = _rod(radius_mm=12.0)
    entry = edt.ijk_to_world((2, 25, 25))
    target = edt.ijk_to_world((60, 25, 25))
    area = safe_entry_area(entry, target, 6.5, 2.0, edt, labels, step_mm=1.0, half_extent_mm=8.0)

    # A 6.5 mm screw with a 2 mm margin needs 5.25 mm of bone around its
    # axis, so in a 12 mm rod its entry can move about 6.75 mm any way.
    assert area.planned_is_safe
    assert 4.5 <= area.room_mm <= 7.0
    assert set(area.extents_mm) == {"toward the head", "toward the feet", "anterior", "posterior"}
    reach = list(area.extents_mm.values())
    assert min(reach) >= 5.0 and max(reach) - min(reach) <= 2.0  # round, as the rod is
    assert area.sentence().startswith(f"a safe circle of {area.room_mm:.1f} mm around it")
    assert "sliding the screw parallel" in area.sentence()


def test_every_offset_called_safe_passes_the_plan_s_own_check():
    edt, labels = _rod(radius_mm=10.0)
    entry = edt.ijk_to_world((2, 25, 25))
    target = edt.ijk_to_world((60, 25, 25))
    area = safe_entry_area(entry, target, 4.5, 2.0, edt, labels, step_mm=2.0, half_extent_mm=8.0)

    coords = np.arange(-(area.safe.shape[0] // 2), area.safe.shape[0] // 2 + 1) * area.step_mm
    axis_1, axis_2 = np.array(area.axis_1), np.array(area.axis_2)
    n_safe = 0
    for i2, c2 in enumerate(coords):
        for i1, c1 in enumerate(coords):
            shift = c1 * axis_1 + c2 * axis_2
            v = validate_screw(np.array(entry) + shift, np.array(target) + shift, 4.5, 2.0, edt, labels)
            if area.safe[i2, i1]:
                n_safe += 1
                assert not v.breach, (c1, c2)
            elif np.hypot(c1, c2) < area.room_mm:
                raise AssertionError(f"offset {(c1, c2)} is inside the reported room but not safe")
    assert n_safe > 4
    assert area.entry_points_xyz.shape == (n_safe, 3)


def test_a_slot_beside_the_entry_shortens_the_room_on_that_side():
    edt, labels = _slab_with_slot(slot_x=34)  # slot faces at x = 33.5 and 36.5
    entry, target = (28.0, 30.0, 45.0), (28.0, 30.0, 15.0)
    area = safe_entry_area(entry, target, 4.5, 2.0, edt, labels, step_mm=1.0, half_extent_mm=8.0)

    toward_slot = area.extents_mm["toward the patient's right"]  # +x, where the slot is
    away = area.extents_mm["toward the patient's left"]
    assert toward_slot < away
    assert toward_slot <= 2.0  # the envelope reaches the slot within ~2 mm
    assert area.room_mm <= 2.0


def test_an_entry_that_does_not_pass_is_reported_as_such():
    edt, labels = _rod(radius_mm=4.0)  # too narrow for this screw
    entry = edt.ijk_to_world((2, 25, 25))
    target = edt.ijk_to_world((60, 25, 25))
    area = safe_entry_area(entry, target, 7.3, 2.0, edt, labels, step_mm=2.0, half_extent_mm=6.0)
    assert not area.planned_is_safe
    assert not area.safe.any()
    assert area.room_mm == 0.0
    assert area.sentence() == "the planned entry itself does not pass the check"
