import numpy as np
import pytest

from corridor_engine import segmentation as seg
from corridor_engine.app_frame import build_app
from corridor_engine.landmarks import Landmark, detect_landmarks
from corridor_engine.views import angles_from_beam, beam_from_angles, patient_views
from corridor_engine.volume import Volume

TEXTBOOK = {
    "ap": {"rotate_x": 0, "rotate_z": 0},
    "inlet": {"rotate_x": -45, "rotate_z": 0},
    "outlet": {"rotate_x": 45, "rotate_z": 0},
    "iliac_oblique_right": {"rotate_x": 0, "rotate_z": -45},
    "obturator_oblique_right": {"rotate_x": 0, "rotate_z": 45},
}


def _tilted_pelvis(tilt_deg=0.0):
    """A pelvis of blocks, optionally tilted back about the left-right axis:
    two wings in their own plane, two pubic bodies, two ischial tuberosities
    and a sacrum. Tilting it must move every computed view by the same
    amount, which is the point of computing them."""
    nz, ny, nx = 170, 170, 280
    labels = np.zeros((nz, ny, nx), dtype=np.uint8)
    origin = (-140.0, -60.0, 0.0)

    def block(label, x_lo, x_hi, y_lo, y_hi, z_lo, z_hi):
        if x_lo > x_hi:  # the left side's bounds come out mirrored
            x_lo, x_hi = x_hi, x_lo
        zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
        x = origin[0] + xx
        y = origin[1] + yy
        z = origin[2] + zz
        if tilt_deg:  # rotate the body about the x axis, as a tilted pelvis is
            a = np.radians(tilt_deg)
            y, z = y * np.cos(a) + z * np.sin(a), -y * np.sin(a) + z * np.cos(a)
        inside = ((x >= x_lo) & (x <= x_hi) & (y >= y_lo) & (y <= y_hi) & (z >= z_lo) & (z <= z_hi))
        labels[inside & (labels == 0)] = label

    for label, sign in ((seg.HIP_R, 1), (seg.HIP_L, -1)):
        block(label, sign * 60, sign * 125, 20, 50, 60, 130)   # wing, in the coronal plane
        block(label, sign * 95, sign * 110, 50, 58, 100, 115)  # the ASIS
        block(label, sign * 8, sign * 38, 30, 55, 25, 45)      # pubic body
        block(label, sign * 38, sign * 62, 10, 30, 35, 70)     # anterior column
        block(label, sign * 45, sign * 75, -25, 0, 5, 25)      # ischial tuberosity
        block(label, sign * 16, sign * 60, -25, 10, 60, 105)   # the surface facing the sacrum
        # An obturator ring: bone around a thin oblique slab of space, which
        # is what makes the foramen a hole with a plane of its own.
        block(label, sign * 18, sign * 72, -22, 28, 8, 42)
        zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
        x, y, z = origin[0] + xx, origin[1] + yy, origin[2] + zz
        if tilt_deg:
            a_rad = np.radians(tilt_deg)
            y, z = y * np.cos(a_rad) + z * np.sin(a_rad), -y * np.sin(a_rad) + z * np.cos(a_rad)
        hole = ((np.abs(0.7 * (x - sign * 45) + sign * 0.7 * (y - 3)) < 7)
                & (np.abs(x - sign * 45) < 22) & (y > -18) & (y < 24) & (z > 12) & (z < 38))
        labels[hole] = 0
    # A sacrum with a slope: its front face leans back as it descends, which
    # is what gives a patient his own outlet angle.
    for z in range(45, 115, 5):
        front = 20 - 0.6 * (115 - z)
        block(seg.SACRUM, -14, 14, front - 45, front, z, z + 5)
    return Volume(labels, (1.0, 1.0, 1.0), origin)


def _views(tilt_deg=0.0):
    vol = _tilted_pelvis(tilt_deg)
    marks = detect_landmarks(vol)
    frame = build_app(marks["asis_right"].xyz, marks["asis_left"].xyz,
                      marks["pubic_tubercle_right"].xyz, marks["pubic_tubercle_left"].xyz)
    return patient_views(vol, marks, frame, textbook=TEXTBOOK), marks, frame


def test_angles_and_beams_are_inverses():
    for rotate_x, rotate_z in ((0, 0), (-45, 0), (45, 0), (0, 45), (-25, 10), (30, -60)):
        back = angles_from_beam(beam_from_angles(rotate_x, rotate_z))
        assert back == pytest.approx((rotate_x, rotate_z), abs=1e-6)


def test_each_view_runs_the_way_that_view_is_taken():
    views, marks, frame = _views()
    assert {"ap", "inlet", "outlet", "lateral", "lateral_sacral"} <= set(views)

    assert np.dot(views["ap"].beam, frame.y_hat) < -0.9, "AP runs front to back"
    assert views["inlet"].beam[2] < -0.2, "the inlet is tilted caudally"
    assert views["outlet"].beam[2] > 0.2, "the outlet is tilted cranially"
    # The two are far apart and both run in the patient's midline plane.
    # They are NOT a right angle apart: the inlet comes from the brim and
    # the outlet from the front of the sacrum, and in a real pelvis those
    # two are not perpendicular.
    between = np.degrees(np.arccos(np.clip(float(np.dot(views["inlet"].beam, views["outlet"].beam)), -1.0, 1.0)))
    assert between > 45.0
    for name in ("inlet", "outlet"):
        assert float(np.dot(views[name].beam, frame.x_hat)) == pytest.approx(0.0, abs=0.1)
    assert abs(float(np.dot(views["lateral"].beam, frame.x_hat))) > 0.9, "the lateral runs across"

    # An oblique of one side is entered from the other.
    assert views["iliac_oblique_right"].beam[0] > 0.2
    assert views["iliac_oblique_left"].beam[0] < -0.2
    assert views["obturator_oblique_right"].beam[0] < -0.2
    assert views["obturator_oblique_left"].beam[0] > 0.2


def test_the_views_follow_the_patient_rather_than_the_table():
    """A pelvis tilted back 20 degrees needs every view moved by 20 degrees.
    Fixed angles would not move at all, which is what this is here to
    prevent."""
    upright, _, _ = _views(0.0)
    tilted, _, _ = _views(20.0)
    for name in ("ap", "inlet", "outlet"):
        moved = np.degrees(np.arccos(np.clip(float(np.dot(upright[name].beam, tilted[name].beam)), -1.0, 1.0)))
        # The tolerance is wide because the landmarks themselves shift a
        # little when this blocky phantom is rotated on its voxel grid; what
        # matters is that the views move with the patient at all.
        assert moved == pytest.approx(20.0, abs=10.0), f"{name} moved {moved:.0f} degrees"
    # And the tool says how far from the textbook angles each one is. This
    # phantom stands upright, so its own inlet is about 25 degrees of tilt
    # and the textbook 45 is wrong for it by about 20; tilt the pelvis back
    # by 20 and the textbook angle becomes right for it.
    assert upright["inlet"].off_textbook_deg == pytest.approx(20.0, abs=8.0)
    assert tilted["inlet"].off_textbook_deg == pytest.approx(0.0, abs=8.0)


def test_a_view_says_what_it_is():
    views, _, _ = _views()
    sentence = views["inlet"].sentence()
    assert "pelvic brim" in sentence and "S1" in sentence
    assert "tilt" in sentence and "textbook" in sentence


def test_missing_anatomy_leaves_the_view_out_rather_than_guessing():
    vol = _tilted_pelvis()
    marks = detect_landmarks(vol)
    frame = build_app(marks["asis_right"].xyz, marks["asis_left"].xyz,
                      marks["pubic_tubercle_right"].xyz, marks["pubic_tubercle_left"].xyz)
    without = {k: v for k, v in marks.items() if k not in ("si_joint_center_right", "si_joint_center_left")}
    views = patient_views(vol, without, frame, textbook=TEXTBOOK)
    assert "lateral_sacral" not in views
    assert "ap" in views
