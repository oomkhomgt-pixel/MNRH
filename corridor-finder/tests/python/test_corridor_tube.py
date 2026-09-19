import numpy as np

from corridor_engine.corridor import search_corridor
from corridor_engine.edt import bone_edt_mm
from corridor_engine.phantoms import solid_rod
from corridor_engine.volume import Volume

SPACING = (1.0, 1.0, 1.0)
SHAPE = (60, 60, 120)


def _rod_setup(radius_mm: float):
    mask = solid_rod(shape=SHAPE, radius_mm=radius_mm)
    edt = bone_edt_mm(mask, SPACING)
    edt_vol = Volume(edt, SPACING)
    nz, ny, nx = SHAPE
    xx = np.arange(nx).reshape(1, 1, nx)
    xx = np.broadcast_to(xx, SHAPE)
    entry_mask = mask & (xx < 12)
    exit_mask = mask & (xx > nx - 12)
    entry_center = edt_vol.ijk_to_world((5, ny / 2.0, nz / 2.0))
    exit_center = edt_vol.ijk_to_world((nx - 5, ny / 2.0, nz / 2.0))
    return mask, edt_vol, entry_mask, exit_mask, entry_center, exit_center


def test_wide_rod_yields_expected_radius_and_direction():
    mask, edt_vol, entry_mask, exit_mask, entry_c, exit_c = _rod_setup(radius_mm=8.0)
    results = search_corridor(
        entry_mask=entry_mask,
        exit_mask=exit_mask,
        entry_center_xyz=entry_c,
        entry_radius_mm=15.0,
        exit_center_xyz=exit_c,
        exit_radius_mm=15.0,
        edt_vol=edt_vol,
        margin_mm=2.0,
        screw_diameters_mm=[3.5, 4.5, 6.5, 7.0, 7.3],
        length_range_mm=(60.0, 130.0),
        textbook_direction=(1, 0, 0),
        top_k=1,
    )
    assert results, "expected at least one corridor result"
    best = results[0]
    # radius 8mm rod, 2mm margin -> r_safe ~= 6mm; 7.3mm screw (radius 3.65) fits, 8.0 would not (no such size)
    assert 5.0 <= best.r_safe_mm <= 8.0
    assert best.screw.fits
    assert best.screw.diameter_mm == 7.3
    direction = np.asarray(best.direction)
    axis = np.array([1.0, 0.0, 0.0])
    cos_angle = abs(np.dot(direction, axis))
    angle_deg = np.degrees(np.arccos(np.clip(cos_angle, -1, 1)))
    assert angle_deg < 5.0


def test_narrow_rod_yields_no_screw_fit():
    mask, edt_vol, entry_mask, exit_mask, entry_c, exit_c = _rod_setup(radius_mm=3.0)
    results = search_corridor(
        entry_mask=entry_mask,
        exit_mask=exit_mask,
        entry_center_xyz=entry_c,
        entry_radius_mm=15.0,
        exit_center_xyz=exit_c,
        exit_radius_mm=15.0,
        edt_vol=edt_vol,
        margin_mm=2.0,
        screw_diameters_mm=[3.5, 4.5, 6.5, 7.0, 7.3],
        length_range_mm=(60.0, 130.0),
        top_k=1,
    )
    assert results
    assert results[0].screw.fits is False
    assert results[0].r_safe_mm < 1.75


def test_corridor_shorter_than_length_range_does_not_fit():
    # The rod is wide enough for the largest screw but only ~110 mm long, so
    # no screw from a 150-220 mm range fits. A diameter alone is not a fit:
    # the plan must never fall back to the raw, non-catalog axis length.
    mask, edt_vol, entry_mask, exit_mask, entry_c, exit_c = _rod_setup(radius_mm=8.0)
    results = search_corridor(
        entry_mask=entry_mask,
        exit_mask=exit_mask,
        entry_center_xyz=entry_c,
        entry_radius_mm=15.0,
        exit_center_xyz=exit_c,
        exit_radius_mm=15.0,
        edt_vol=edt_vol,
        margin_mm=2.0,
        screw_diameters_mm=[3.5, 4.5, 6.5, 7.0, 7.3],
        length_range_mm=(150.0, 220.0),
        top_k=1,
    )
    assert results
    best = results[0]
    assert best.length_mm < 150.0
    assert best.screw.length_mm is None
    assert best.screw.fits is False
