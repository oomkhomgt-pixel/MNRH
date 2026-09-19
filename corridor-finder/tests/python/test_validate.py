import numpy as np
import pytest

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


# ---- DECISIONS.md section 1: entry on the cortex, exemption, tip rules ----

CATALOG_5MM = [float(v) for v in range(10, 105, 5)]


def _slab(slot_x=None):
    """A 1 mm grid with a box of bone, top face at z = 40.5 (voxel boundary)
    and bottom face at z = 9.5; optionally a full-depth slot 2 mm wide at
    x = slot_x..slot_x + 2 running along y (a side wall next to an entry)."""
    zz, yy, xx = np.mgrid[0:60, 0:60, 0:70]
    mask = (xx >= 5) & (xx <= 64) & (yy >= 5) & (yy <= 54) & (zz >= 10) & (zz <= 40)
    if slot_x is not None:
        mask &= ~((xx >= slot_x) & (xx <= slot_x + 2) & (zz >= 20))
    edt = Volume(bone_edt_mm(mask, SPACING), SPACING)
    return edt, Volume(mask.astype(np.uint8), SPACING)


def test_square_on_entry_into_a_flat_cortex_is_not_a_breach():
    edt, labels = _slab()
    v = validate_screw((30, 30, 45), (30, 30, 15), 6.5, 2.0, edt, labels, catalog_lengths_mm=CATALOG_5MM)
    assert not v.breach
    assert abs(v.start_xyz[2] - 40.5) <= 0.11  # the screw starts on the cortex
    assert v.entry_handle_offset_mm == pytest.approx(45 - v.start_xyz[2])
    assert v.length_mm == 25.0  # longest catalogue length before the target
    assert v.entry_angle_deg < 1.0
    assert v.warning_codes == ["handle_off_cortex"]  # handle 4.5 mm above the bone


def test_plain_field_alone_would_flag_every_entry():
    # Without the exemption the first samples sit on the surface: the
    # exemption is what lets a screw enter bone at all.
    edt, _ = _slab()
    assert edt.sample_trilinear(np.array([[30.0, 30.0, 40.4]]))[0] < 1.0


def test_handle_inside_the_bone_starts_the_screw_at_the_cortex_behind_it():
    edt, labels = _slab()
    v = validate_screw((30, 30, 35), (30, 30, 15), 6.5, 2.0, edt, labels, catalog_lengths_mm=CATALOG_5MM)
    assert abs(v.start_xyz[2] - 40.5) <= 0.11
    assert v.entry_handle_offset_mm == pytest.approx(35 - v.start_xyz[2])  # negative: inside
    assert "handle_off_cortex" in v.warning_codes
    assert v.length_mm == 25.0


def test_side_wall_next_to_the_entry_is_still_a_breach():
    edt, labels = _slab(slot_x=34)  # slot faces at x = 33.5 and 36.5
    near = validate_screw((30, 30, 45), (30, 30, 15), 4.5, 2.0, edt, labels, catalog_lengths_mm=CATALOG_5MM)
    far = validate_screw((20, 30, 45), (20, 30, 15), 4.5, 2.0, edt, labels, catalog_lengths_mm=CATALOG_5MM)
    assert near.breach  # envelope (2.25 + 2 mm) reaches the slot 3.5 mm away
    assert near.worst_point_xyz[2] > 40.5 - near.entry_zone_mm  # ...inside the entry zone
    assert not far.breach


def test_steep_entry_is_warned_about():
    edt, labels = _slab()
    d = np.array([np.sin(np.radians(65)), 0.0, -np.cos(np.radians(65))])
    v = validate_screw(np.array([20.0, 30.0, 42.0]), np.array([20.0, 30.0, 42.0]) + 40 * d, 4.5, 2.0, edt, labels)
    assert "entry_oblique" in v.warning_codes
    assert v.entry_angle_deg > 60


def test_inside_tip_keeps_its_full_margin():
    edt, labels = _slab()
    # Without a catalogue the tip is at the target, 1 mm above the far cortex.
    v = validate_screw((30, 30, 45), (30, 30, 10.5), 6.5, 2.0, edt, labels)
    assert v.breach and v.exit_xyz is None and v.protrusion_mm is None


def test_through_tip_rounds_up_and_reports_the_protrusion():
    edt, labels = _slab()
    v = validate_screw((30, 30, 45), (30, 30, 12), 6.5, 2.0, edt, labels, tip_rule="through", catalog_lengths_mm=CATALOG_5MM)
    assert abs(v.exit_xyz[2] - 9.5) <= 0.11
    assert v.length_mm == 35.0  # 31 mm cortex to cortex, rounded up
    assert 0 < v.protrusion_mm <= 5.0
    assert v.tip_xyz[2] < 9.5
    assert not v.breach


def test_through_tip_is_exempted_at_most_one_catalogue_step_past_the_cortex():
    edt, labels = _slab()
    ok = validate_screw((30, 30, 45), (30, 30, 12), 6.5, 2.0, edt, labels, tip_rule="through", catalog_lengths_mm=[10.0, 35.0])
    long = validate_screw((30, 30, 45), (30, 30, 12), 6.5, 2.0, edt, labels, tip_rule="through", catalog_lengths_mm=[10.0, 45.0])
    assert not ok.breach
    assert long.protrusion_mm > 5.0 and long.breach


def test_missing_catalogue_length_is_reported():
    edt, labels = _slab()
    v = validate_screw((30, 30, 45), (30, 30, 35), 6.5, 2.0, edt, labels, catalog_lengths_mm=[40.0, 45.0])
    assert "no_catalog_length" in v.warning_codes
    assert v.length_mm == pytest.approx(v.start_xyz[2] - 35)


def test_coincident_handles_are_rejected():
    edt, labels = _slab()
    with pytest.raises(ValueError):
        validate_screw((30, 30, 45), (30, 30, 45), 6.5, 2.0, edt, labels)


def _slab_with_cavity():
    """The slab with a closed cavity inside it (like the sacral canal or a
    foramen): x 40-47, y 25-35, z 20-30 is not bone."""
    zz, yy, xx = np.mgrid[0:60, 0:60, 0:70]
    mask = (xx >= 5) & (xx <= 64) & (yy >= 5) & (yy <= 54) & (zz >= 10) & (zz <= 40)
    mask &= ~((xx >= 40) & (xx <= 47) & (yy >= 25) & (yy <= 35) & (zz >= 20) & (zz <= 30))
    return Volume(bone_edt_mm(mask, SPACING), SPACING), Volume(mask.astype(np.uint8), SPACING)


def test_a_gap_inside_the_bone_is_not_a_far_cortex():
    # A "through" target placed in the cavity: its wall is not the bone's
    # far surface, so the tip is not exempted there and the screw breaches.
    edt, labels = _slab_with_cavity()
    v = validate_screw((43, 30, 45), (43, 30, 25), 4.5, 2.0, edt, labels, tip_rule="through", catalog_lengths_mm=CATALOG_5MM)
    assert "exit_not_outer" in v.warning_codes
    assert v.exit_xyz is None and v.protrusion_mm is None
    assert v.breach
    # The same screw away from the cavity reaches the real far cortex.
    ok = validate_screw((20, 30, 45), (20, 30, 12), 4.5, 2.0, edt, labels, tip_rule="through", catalog_lengths_mm=CATALOG_5MM)
    assert ok.warning_codes == ["handle_off_cortex"] and ok.exit_xyz is not None and not ok.breach


def test_a_gap_inside_the_bone_is_not_an_entry_cortex():
    # Entry handle just past the cavity: the crossing behind it is the
    # cavity's wall, not the outer cortex. The screw cannot be checked from
    # its real entry, so it is never reported safe.
    edt, labels = _slab_with_cavity()
    v = validate_screw((43, 30, 18), (43, 30, 11), 4.5, 0.0, edt, labels)
    assert v.warning_codes == ["entry_not_outer"]
    assert v.breach
    # Away from the cavity the same handle is 22 mm below the top cortex.
    far = validate_screw((20, 30, 18), (20, 30, 11), 4.5, 0.0, edt, labels)
    assert far.warning_codes == ["entry_cortex_not_found"]


def test_entry_handle_deep_in_bone_is_never_safe():
    edt, labels = _slab()
    # Along y from inside the slab: 30 mm of bone behind the handle.
    v = validate_screw((30, 35, 25), (30, 50, 25), 3.5, 0.0, edt, labels)
    assert v.warning_codes == ["entry_cortex_not_found"]
    assert v.breach and v.min_clearance_mm > 0  # a breach although the axis itself is clear
