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


# DECISIONS 7.16: a Denis zone II fracture runs through the foramina.

from corridor_engine.sacral_canal import protected_spaces  # noqa: E402

MIDLINE = ((60.0, 0.0, 0.0), (1.0, 0.0, 0.0))  # the plane x = 60, normal to the patient's right


def _symmetric_sacrum(gap_on_right=True, gap_on_left=False, gap_mm=6):
    """A sacrum block symmetric about x = 60: a canal in the middle, one
    foramen each side at x = 60 -/+ 22 (9 mm across, front to back), and a
    zone II fracture gap gap_mm wide, full height and depth, through the
    foramen of the side(s) asked for."""
    labels = np.zeros((60, 80, 120), dtype=np.uint8)
    labels[5:55, 10:70, 25:96] = SACRUM
    labels[5:55, 15:30, 53:68] = 0  # canal
    zz, yy, xx = np.mgrid[0:60, 0:80, 0:120]
    foramina = np.zeros(labels.shape, dtype=bool)
    gaps = np.zeros(labels.shape, dtype=bool)
    for cx, broken in ((82.0, gap_on_right), (38.0, gap_on_left)):
        f = ((zz - 30) ** 2 + (xx - cx) ** 2 <= 4.5 ** 2) & (yy >= 10) & (yy < 70)
        foramina |= f
        if broken:
            gaps |= (np.abs(xx - cx) <= gap_mm / 2.0) & (zz >= 5) & (zz < 55) & (yy >= 10) & (yy < 70)
    labels[(foramina | gaps) & (labels == SACRUM)] = 0
    return Volume(labels, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)), foramina, gaps


def test_without_a_marked_fracture_the_gap_is_taken_for_foramen():
    """What the surgeon saw: the gap and the foramen are one hole."""
    vol, foramina, gaps = _symmetric_sacrum()
    found = canal_and_foramina(vol, SACRUM)
    away = gaps & ~foramina
    away[:, :, :] &= (np.abs(np.mgrid[0:60, 0:80, 0:120][0] - 30) > 12)
    assert found[away].mean() > 0.5


def test_a_marked_zone_two_fracture_keeps_the_foramen_and_frees_the_gap():
    vol, foramina, gaps = _symmetric_sacrum()
    found, notes = protected_spaces(vol, SACRUM, midline=MIDLINE, fractured_sides=["right"])
    zz = np.mgrid[0:60, 0:80, 0:120][0]
    right_foramen = foramina & (np.mgrid[0:60, 0:80, 0:120][2] > 60)
    inner = right_foramen.copy()
    inner[:, :12] = False
    inner[:, 68:] = False
    assert found[inner].mean() > 0.95, "the foramen in the fracture stays protected (mirrored from the left)"
    far_gap = gaps & (np.abs(zz - 30) > 4.5 + 2.0 + 2.0)
    assert not found[far_gap].any(), "the gap above and below it may be crossed"
    left_foramen = foramina & (np.mgrid[0:60, 0:80, 0:120][2] < 60)
    inner_left = left_foramen.copy()
    inner_left[:, :12] = False
    inner_left[:, 68:] = False
    assert found[inner_left].mean() > 0.95, "the intact side as found"
    assert found[10:50, 17:28, 55:66].all(), "the canal"
    assert notes and "mirrored" in notes[0]


def test_both_sides_fractured_keeps_everything_protected_and_says_so():
    vol, foramina, gaps = _symmetric_sacrum(gap_on_right=True, gap_on_left=True)
    found, notes = protected_spaces(vol, SACRUM, midline=MIDLINE, fractured_sides=["right", "left"])
    assert (found >= canal_and_foramina(vol, SACRUM)).all()
    assert notes and "Both sides" in notes[0]


def test_a_hole_enclosed_between_fragments_away_from_the_midline_is_not_the_canal():
    vol, _, _ = _symmetric_sacrum(gap_on_right=False)
    labels = vol.array.copy()
    labels[10:50, 40:50, 90:93] = 0  # a thin enclosed slot, 30 mm off the midline
    found, _ = protected_spaces(Volume(labels, vol.spacing, vol.origin), SACRUM, midline=MIDLINE)
    assert not found[10:50, 40:50, 90:93].any(), "a thin slot off the midline is neither canal nor foramen"


def test_nothing_is_mirrored_from_a_side_with_no_foramina_found():
    """If the side called intact shows no foramina (a segmentation problem),
    the fractured side keeps everything the shape found."""
    vol, foramina, gaps = _symmetric_sacrum()
    labels = vol.array.copy()
    labels[foramina & (np.mgrid[0:60, 0:80, 0:120][2] < 60)] = SACRUM  # the left foramen painted over
    v2 = Volume(labels, vol.spacing, vol.origin)
    found, notes = protected_spaces(v2, SACRUM, midline=MIDLINE, fractured_sides=["right"])
    assert (found >= canal_and_foramina(v2, SACRUM)).all()
    assert notes and "almost no foramina" in notes[0]


def test_a_painted_foramen_frees_the_fracture_gap_on_its_side_only():
    """DECISIONS 7.17: both sides fractured; the surgeon paints the right
    foramen on one coronal slice. It becomes a channel front to back; the
    right fracture gap outside it may be crossed; the unpainted left side
    stays fully protected."""
    vol, foramina, gaps = _symmetric_sacrum(gap_on_right=True, gap_on_left=True)
    zz, yy, xx = np.mgrid[0:60, 0:80, 0:120]
    painted = ((zz - 30) ** 2 + (xx - 82) ** 2 <= 4.5 ** 2) & (yy == 40)
    found, notes = protected_spaces(vol, SACRUM, midline=MIDLINE, fractured_sides=["right", "left"],
                                    user_foramina=painted, fracture_gap=gaps, ap_axis=(0.0, 1.0, 0.0))
    channel = foramina & (xx > 60) & (yy >= 12) & (yy < 68)
    assert found[channel].mean() > 0.95, "the painted foramen, front to back"
    right_gap_far = gaps & (xx > 60) & (np.abs(zz - 30) > 4.5 + 1.0)
    assert not found[right_gap_far].any(), "the right fracture gap outside it may be crossed"
    left_gap_far = gaps & (xx < 60) & (np.abs(zz - 30) > 4.5 + 1.0)
    assert found[left_gap_far].mean() > 0.5, "the left side, not painted, stays protected"
    assert any("painted" in n for n in notes)
