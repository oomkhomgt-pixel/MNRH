import numpy as np

from corridor_engine.corridor import search_corridor
from corridor_engine.edt import bone_edt_mm
from corridor_engine.phantoms import plate_with_hole
from corridor_engine.volume import Volume

SPACING = (1.0, 1.0, 1.0)
SHAPE = (60, 60, 20)


def test_axis_avoids_hole_in_plate():
    mask = plate_with_hole(shape=SHAPE, hole_radius_mm=5.0)
    edt_vol = Volume(bone_edt_mm(mask, SPACING), SPACING)
    nz, ny, nx = SHAPE
    xx = np.arange(nx).reshape(1, 1, nx)
    xx = np.broadcast_to(xx, SHAPE)
    entry_mask = mask & (xx < 3)
    exit_mask = mask & (xx > nx - 3)
    entry_c = edt_vol.ijk_to_world((1, ny / 2.0, nz / 2.0))
    exit_c = edt_vol.ijk_to_world((nx - 1, ny / 2.0, nz / 2.0))

    results = search_corridor(
        entry_mask=entry_mask,
        exit_mask=exit_mask,
        entry_center_xyz=entry_c,
        entry_radius_mm=30.0,
        exit_center_xyz=exit_c,
        exit_radius_mm=30.0,
        edt_vol=edt_vol,
        margin_mm=2.0,
        length_range_mm=(nx * 0.5, nx * 1.5),
        top_k=1,
    )
    assert results
    best = results[0]
    # The hole is centered at (z=nz*0.5, y=ny*0.75); a safe axis should stay
    # far from that column. Check the midpoint in (z, y) is not near the hole.
    mid = (np.array(best.entry_xyz) + np.array(best.target_xyz)) / 2.0
    hole_yz = np.array([ny * 0.75, nz * 0.5])
    dist_to_hole_axis = np.linalg.norm(np.array([mid[1], mid[2]]) - hole_yz)
    assert dist_to_hole_axis > 5.0
    assert best.screw.fits
