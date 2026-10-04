import numpy as np

from corridor_engine.sacral_canal import canal_and_foramina
from corridor_engine.volume import Volume

SACRUM, HIP_R = 3, 2


def _sacrum():
    """A block of sacrum with a canal tunnel (enclosed in every axial slice)
    and a foramen channel 9 mm across running front to back, and a hip bone
    beside it across a 3 mm joint."""
    labels = np.zeros((60, 80, 120), dtype=np.uint8)
    labels[5:55, 10:70, 20:80] = SACRUM
    labels[5:55, 15:30, 42:58] = 0          # canal: y 15..29, x 42..57, every slice
    zz, yy, xx = np.mgrid[0:60, 0:80, 0:120]
    foramen = ((zz - 30) ** 2 + (xx - 32) ** 2 <= 4.5 ** 2) & (yy >= 10) & (yy < 70)
    labels[foramen & (labels == SACRUM)] = 0
    labels[5:55, 10:70, 83:110] = HIP_R      # the hip, 3 mm from the sacrum's side
    return Volume(labels, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)), foramen


def test_the_canal_and_a_foramen_are_found():
    vol, foramen = _sacrum()
    found = canal_and_foramina(vol, SACRUM, (HIP_R,))
    assert found[10:50, 17:28, 44:56].all(), "the canal"
    inner = foramen.copy()
    inner[:, :12] = False
    inner[:, 68:] = False
    assert found[inner].mean() > 0.95, "the foramen, through the bone"


def test_the_sacroiliac_joint_is_not_a_foramen():
    vol, _ = _sacrum()
    found = canal_and_foramina(vol, SACRUM, (HIP_R,))
    assert not found[:, :, 80:83].any()


def test_dense_bone_is_never_taken():
    vol, _ = _sacrum()
    found = canal_and_foramina(vol, SACRUM, (HIP_R,))
    assert not (found & (vol.array != 0)).any()


def test_a_thin_fracture_gap_is_not_a_foramen():
    """A 3 mm fracture gap across the sacrum is a sheet, not a channel: it
    stays bridgeable when the surgeon marks it (DECISIONS 7.14)."""
    vol, _ = _sacrum()
    labels = vol.array.copy()
    labels[30:33, 10:70, 20:40] = 0  # a 3 mm gap through the ala, lateral to the foramen
    found = canal_and_foramina(Volume(labels, vol.spacing, vol.origin), SACRUM, (HIP_R,))
    sheet = np.zeros(labels.shape, dtype=bool)
    sheet[30:33, 12:68, 20:26] = True  # away from the foramen
    assert not found[sheet].any()
