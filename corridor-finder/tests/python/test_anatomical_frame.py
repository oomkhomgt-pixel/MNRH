"""True axial, coronal and sagittal planes from intact anatomy first (the
surgeon, 2026-10-05): the mid-sagittal plane from the sacral midline, the
coronal tilted to the intact hemipelvis's anterior pelvic plane, then the
surgeon's own turn of the axes."""
import numpy as np
import pytest
from scipy import ndimage as ndi

from corridor_engine import segmentation as seg
from corridor_engine.anatomical_frame import (anatomical_landmarks, pelvic_frame, reslice, to_anatomical,
                                              from_anatomical, turned)
from corridor_engine.app_frame import Frame, build_app
from corridor_engine.landmarks import Landmark
from corridor_engine.si_joint import measure_joint_widths
from corridor_engine.volume import Volume


def _rotation(tilt, roll, yaw):
    """Rx(tilt) then Ry(roll) then Rz(yaw), degrees, in RAS."""
    t, r, y = np.radians([tilt, roll, yaw])
    rx = np.array([[1, 0, 0], [0, np.cos(t), -np.sin(t)], [0, np.sin(t), np.cos(t)]])
    ry = np.array([[np.cos(r), 0, np.sin(r)], [0, 1, 0], [-np.sin(r), 0, np.cos(r)]])
    rz = np.array([[np.cos(y), -np.sin(y), 0], [np.sin(y), np.cos(y), 0], [0, 0, 1]])
    return rz @ ry @ rx


# A pelvis in its own anatomical mm (right, anterior, cephalad).
MIDLINE = {"s1_body": (0.0, 10.0, 0.0), "s2_body": (0.0, 5.0, -25.0), "s3_body": (0.0, 0.0, -45.0),
           "s1_canal": (0.0, -25.0, 0.0), "s2_canal": (0.0, -22.0, -25.0)}
ASIS = {"right": (110.0, 60.0, 20.0), "left": (-110.0, 60.0, 20.0)}
PUBIS = {"right": (15.0, 60.0, -90.0), "left": (-15.0, 60.0, -90.0)}


def _angle(a, b):
    return float(np.degrees(np.arccos(np.clip(abs(float(np.dot(a, b))), -1.0, 1.0))))


def _on_the_table(rot, shift=(12.0, -30.0, 900.0)):
    def world(p):
        return rot @ np.asarray(p, dtype=float) + np.asarray(shift)
    return world


def test_the_planes_follow_the_patient_not_the_table():
    rot = _rotation(tilt=12.0, roll=8.0, yaw=6.0)
    world = _on_the_table(rot)
    mid = [world(p) for p in MIDLINE.values()]
    frame = pelvic_frame(mid, origin=world(MIDLINE["s1_body"]),
                         asis_pubis_pairs=[(world(ASIS[s]), world(PUBIS[s])) for s in ("right", "left")])
    assert _angle(frame.x_hat, rot @ np.array([-1.0, 0.0, 0.0])) < 0.5, "left-right"
    assert _angle(frame.y_hat, rot @ np.array([0.0, 1.0, 0.0])) < 0.5, "front-back"
    assert _angle(frame.z_hat, rot @ np.array([0.0, 0.0, 1.0])) < 0.5, "up-down"
    assert float(frame.x_hat @ (rot @ np.array([-1.0, 0.0, 0.0]))) > 0, "x toward the patient's left"


def test_a_displaced_hemipelvis_does_not_tilt_the_planes():
    """The right hemipelvis is displaced: its ASIS 15 mm up, its pubic
    tubercle 6 mm across. Built from the intact left side, the planes are
    where they belong; the old frame from both ASIS and both tubercles is
    turned by the injury."""
    rot = _rotation(tilt=10.0, roll=5.0, yaw=-4.0)
    world = _on_the_table(rot)
    asis_r = world(np.asarray(ASIS["right"]) + [0.0, 0.0, 15.0])
    pubis_r = world(np.asarray(PUBIS["right"]) + [6.0, 0.0, 0.0])
    mid = [world(p) for p in MIDLINE.values()]
    intact = pelvic_frame(mid, origin=world(MIDLINE["s1_body"]),
                          asis_pubis_pairs=[(world(ASIS["left"]), world(PUBIS["left"]))])
    for got, want in ((intact.x_hat, [-1, 0, 0]), (intact.y_hat, [0, 1, 0]), (intact.z_hat, [0, 0, 1])):
        assert _angle(got, rot @ np.asarray(want, float)) < 0.5
    both_asis = build_app(asis_r, world(ASIS["left"]), pubis_r, world(PUBIS["left"]))
    worst = max(_angle(both_asis.x_hat, rot @ np.array([-1.0, 0.0, 0.0])),
                _angle(both_asis.z_hat, rot @ np.array([0.0, 0.0, 1.0])))
    assert worst > 2.0, f"the both-ASIS frame is turned by the injury ({worst:.1f} degrees)"


def test_the_surgeon_can_turn_the_planes():
    world = _on_the_table(np.eye(3))
    mid = [world(p) for p in MIDLINE.values()]
    pairs = [(world(ASIS[s]), world(PUBIS[s])) for s in ("right", "left")]
    base = pelvic_frame(mid, origin=world(MIDLINE["s1_body"]), asis_pubis_pairs=pairs)
    tilted = pelvic_frame(mid, origin=world(MIDLINE["s1_body"]), asis_pubis_pairs=pairs, adjust_deg=(7.0, 0.0, 0.0))
    assert _angle(tilted.x_hat, base.x_hat) < 1e-6, "a tilt keeps the left-right axis"
    assert _angle(tilted.y_hat, base.y_hat) == pytest.approx(7.0, abs=1e-3)
    rolled = pelvic_frame(mid, origin=world(MIDLINE["s1_body"]), asis_pubis_pairs=pairs, adjust_deg=(0.0, 4.0, 0.0))
    assert _angle(rolled.y_hat, base.y_hat) < 1e-6 and _angle(rolled.x_hat, base.x_hat) == pytest.approx(4.0, abs=1e-3)
    # Turning the built planes is the same turn as building them turned.
    both = pelvic_frame(mid, origin=world(MIDLINE["s1_body"]), asis_pubis_pairs=pairs, adjust_deg=(5.0, -3.0, 2.0))
    later = turned(base, (5.0, -3.0, 2.0))
    for a_, b_ in ((both.x_hat, later.x_hat), (both.y_hat, later.y_hat), (both.z_hat, later.z_hat)):
        assert np.allclose(a_, b_, atol=1e-9)


def test_the_mid_sagittal_plane_comes_in_the_mirror_planes_form():
    """(normal, offset) like mirror.MirrorPlane, so the two midlines can be
    compared (displacement-finder 7f.6)."""
    from corridor_engine.anatomical_frame import mid_sagittal
    rot = _rotation(6.0, 4.0, -3.0)
    world = _on_the_table(rot)
    frame = pelvic_frame([world(p) for p in MIDLINE.values()], origin=world(MIDLINE["s1_body"]),
                         asis_pubis_pairs=[(world(ASIS["left"]), world(PUBIS["left"]))])
    normal, offset = mid_sagittal(frame)
    for p in MIDLINE.values():
        assert float(normal @ world(p) - offset) == pytest.approx(0.0, abs=1e-6), "the midline lies on it"
    assert float(normal @ world(ASIS["left"]) - offset) == pytest.approx(110.0, abs=1e-6), "normal toward the left"


def test_midline_points_on_one_line_are_refused():
    with pytest.raises(ValueError, match="one line"):
        pelvic_frame([(0, 0, 0), (0, 0, -25), (0, 0, -45)], origin=(0, 0, 0))


def test_anatomical_coordinates_go_there_and_back():
    rot = _rotation(9.0, -6.0, 3.0)
    world = _on_the_table(rot)
    frame = pelvic_frame([world(p) for p in MIDLINE.values()], origin=world(MIDLINE["s1_body"]),
                         asis_pubis_pairs=[(world(ASIS["left"]), world(PUBIS["left"]))])
    p = world((40.0, -12.0, 30.0))
    assert to_anatomical(frame, p) == pytest.approx([40.0, -12.0 - 10.0, 30.0], abs=1e-6)
    assert from_anatomical(frame, to_anatomical(frame, p)) == pytest.approx(p, abs=1e-6)


def _si_phantom():
    """Sacrum between two hip bones across 3 mm joints, the joints widening
    upward (2 mm at the bottom to 5 mm at the top), as real
    joints do: a cut at a different height reads a different gap."""
    labels = np.zeros((70, 90, 160), dtype=np.uint8)
    zz, yy, xx = np.mgrid[0:70, 0:90, 0:160]
    gap = 2.0 + 3.0 * np.clip((zz - 10) / 50.0, 0, 1)
    labels[(xx >= 50) & (xx <= 110) & (yy >= 25) & (yy <= 65) & (zz >= 10) & (zz <= 60)] = seg.SACRUM
    labels[(xx >= 110 + gap) & (xx <= 145) & (yy >= 25) & (yy <= 65) & (zz >= 10) & (zz <= 60)] = seg.HIP_R
    labels[(xx >= 15) & (xx <= 50 - gap) & (yy >= 25) & (yy <= 65) & (zz >= 10) & (zz <= 60)] = seg.HIP_L
    landmarks = {"s1_body_center": Landmark(np.array([80.0, 45.0, 50.0])),
                 "s2_body_center": Landmark(np.array([80.0, 45.0, 25.0]))}
    return Volume(labels, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)), landmarks


def test_a_rolled_pelvis_reads_the_same_on_its_true_planes():
    """The same pelvis lying rolled 16 degrees on the table: on scanner
    slices its two identical joints are cut at different heights and read
    differently; on its true axial planes they read as they are."""
    vol, landmarks = _si_phantom()
    straight = measure_joint_widths(vol, landmarks)
    assert straight["right"].measured_mm == pytest.approx(straight["left"].measured_mm, abs=0.2)

    centre = np.array([80.0, 45.0, 35.0])
    rot = _rotation(tilt=0.0, roll=16.0, yaw=0.0)
    # Resample the phantom as it would be scanned rolled: world = rot @ (p - c) + c.
    inv = rot.T
    zyx_centre = centre[::-1]
    matrix = np.zeros((3, 3))
    perm = [2, 1, 0]
    for a in range(3):
        for b in range(3):
            matrix[a, b] = inv[perm[a], perm[b]]
    offset = zyx_centre - matrix @ zyx_centre
    rolled = Volume(ndi.affine_transform(vol.array, matrix, offset=offset, order=0, output_shape=vol.array.shape),
                    vol.spacing, vol.origin)
    moved = {k: Landmark(rot @ (np.asarray(v.xyz) - centre) + centre) for k, v in landmarks.items()}
    on_scanner = measure_joint_widths(rolled, moved)
    scanner_diff = abs(on_scanner["right"].measured_mm - on_scanner["left"].measured_mm)

    # The true planes: the pelvis's own axes, rolled with it.
    frame = Frame(origin=centre, x_hat=rot @ np.array([-1.0, 0.0, 0.0]), y_hat=rot @ np.array([0.0, 1.0, 0.0]),
                  z_hat=rot @ np.array([0.0, 0.0, 1.0]))
    # The scan's own voxels, grouped into the true planes' levels.
    on_planes = measure_joint_widths(rolled, anatomical_landmarks(frame, moved), frame=frame)
    planes_diff = abs(on_planes["right"].measured_mm - on_planes["left"].measured_mm)
    assert planes_diff <= 0.3, f"on true planes the identical joints read alike ({planes_diff:.2f} mm apart)"
    assert on_planes["right"].measured_mm == pytest.approx(straight["right"].measured_mm, abs=0.4)
    assert scanner_diff >= 0.5, f"on scanner slices the roll reads as asymmetry ({scanner_diff:.2f} mm)"


def test_reslice_puts_things_where_the_frame_says():
    """A small block at a known place, scanned with the pelvis turned:
    resliced onto the true planes, it is where to_anatomical says."""
    labels = np.zeros((60, 60, 60), dtype=np.uint8)
    labels[35:40, 20:25, 40:45] = 1
    vol = Volume(labels, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0))
    rot = _rotation(10.0, -7.0, 5.0)
    frame = Frame(origin=np.array([30.0, 30.0, 30.0]), x_hat=rot @ np.array([-1.0, 0.0, 0.0]),
                  y_hat=rot @ np.array([0.0, 1.0, 0.0]), z_hat=rot @ np.array([0.0, 0.0, 1.0]))
    true = reslice(vol, frame, (-30.0, -30.0, -30.0), (30.0, 30.0, 30.0), spacing_mm=1.0, order=0)
    found = true.mask_voxel_centers_world(true.array == 1).mean(axis=0)
    expected = to_anatomical(frame, np.array([42.0, 22.0, 37.0]))
    assert found == pytest.approx(expected, abs=0.6)


def test_the_canal_centre_is_the_canal_not_a_foramen_beside_it():
    """CLINIC_0023: the nearest hole to the S1 body was an S1 foramen 23 mm
    to the side, and taking it for the canal turned the planes by 40
    degrees. The canal is the hole behind the body, near the midline."""
    from corridor_engine.anatomical_frame import canal_centres
    from corridor_engine.sacral_canal import canal_mask

    labels = np.zeros((30, 80, 100), dtype=np.uint8)  # 1 mm voxels; x 0-99, y 0-79, z 0-29
    labels[:, 10:70, 20:80] = seg.SACRUM
    labels[:, 15:25, 45:56] = 0  # the canal: behind the body, on the midline (x 50)
    labels[:, 22:40, 68:75] = 0  # a larger foramen 21 mm to the side, nearer the body
    vol = Volume(labels, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0))
    holes = canal_mask(vol, seg.SACRUM)
    assert holes[15, 20, 50] and holes[15, 30, 71], "both holes are found"
    body = {"s1_body_center": Landmark(np.array([50.0, 55.0, 15.0]))}
    centre = canal_centres(vol, body, holes)["s1_canal_center"]
    assert centre[0] == pytest.approx(50.0, abs=1.0) and centre[1] == pytest.approx(19.5, abs=1.0)


def test_planes_turned_more_than_a_patient_lies_are_not_trusted():
    """The Panoramix sample: pubic tubercles found 99 mm apart tilted the
    planes 52 degrees. Planes as built must be ones a patient can lie in."""
    from corridor_engine.anatomical_frame import implausible_turn, turn_from_scanner

    def frame(tilt, roll, yaw):
        rot = _rotation(tilt, roll, yaw)
        return Frame(origin=np.zeros(3), x_hat=rot @ np.array([-1.0, 0.0, 0.0]), y_hat=rot @ np.array([0.0, 1.0, 0.0]),
                     z_hat=rot @ np.array([0.0, 0.0, 1.0]))

    assert turn_from_scanner(frame(12.0, 0.0, 0.0))[0] == pytest.approx(12.0, abs=1e-6)
    assert implausible_turn(frame(10.6, 8.0, -6.0)) is None
    why = implausible_turn(frame(-52.0, 0.0, 0.0))
    assert why is not None and "52" in why and "pubic tubercle" in why
    assert implausible_turn(frame(0.0, 0.0, 30.0)) is not None
