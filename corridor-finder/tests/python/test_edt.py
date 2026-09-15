import numpy as np

from corridor_engine.edt import bone_edt_mm


def test_solid_sphere_edt_matches_radius():
    n = 60
    zz, yy, xx = np.mgrid[0:n, 0:n, 0:n]
    c = n / 2.0
    r = 20.0
    mask = np.sqrt((zz - c) ** 2 + (yy - c) ** 2 + (xx - c) ** 2) <= r
    edt = bone_edt_mm(mask, spacing=(1.0, 1.0, 1.0))
    assert abs(edt.max() - r) < 1.5


def test_edt_zero_outside_mask():
    mask = np.zeros((10, 10, 10), dtype=bool)
    mask[4:6, 4:6, 4:6] = True
    edt = bone_edt_mm(mask, spacing=(1.0, 1.0, 1.0))
    assert edt[0, 0, 0] == 0.0
    assert edt[4, 4, 4] > 0.0
