import numpy as np

from corridor_engine.app_frame import build_app, screw_angles, pelvic_tilt_deg


def _known_points():
    # A tidy, roughly-anatomical arrangement: ASIS ~200mm apart, pubic
    # tubercles ~20mm apart, anterior/inferior to the ASIS.
    asis_r = np.array([-100.0, 0.0, 300.0])
    asis_l = np.array([100.0, 0.0, 300.0])
    pt_r = np.array([-10.0, 20.0, 100.0])
    pt_l = np.array([10.0, 20.0, 100.0])
    return asis_r, asis_l, pt_r, pt_l


def test_build_app_axes_orthonormal_and_oriented():
    asis_r, asis_l, pt_r, pt_l = _known_points()
    frame = build_app(asis_r, asis_l, pt_r, pt_l)

    assert abs(np.linalg.norm(frame.x_hat) - 1.0) < 1e-9
    assert abs(np.linalg.norm(frame.y_hat) - 1.0) < 1e-9
    assert abs(np.linalg.norm(frame.z_hat) - 1.0) < 1e-9
    assert abs(np.dot(frame.x_hat, frame.y_hat)) < 1e-9
    assert abs(np.dot(frame.y_hat, frame.z_hat)) < 1e-9

    # z_hat should point roughly toward +z (cephalad), y_hat toward +y (anterior)
    assert frame.z_hat[2] > 0.9
    assert frame.y_hat[1] > 0.5


def test_app_frame_invariant_under_rigid_rotation():
    asis_r, asis_l, pt_r, pt_l = _known_points()
    frame1 = build_app(asis_r, asis_l, pt_r, pt_l)
    angles1 = screw_angles(np.array([0.1, 0.2, 0.9]), frame1)

    # Rotate the whole configuration (and the test direction) by 15 degrees
    # about the world z axis; the reported angles relative to the (co-rotated)
    # APP frame must be unchanged.
    theta = np.radians(15.0)
    c, s = np.cos(theta), np.sin(theta)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])

    def rot(p):
        return R @ p

    frame2 = build_app(rot(asis_r), rot(asis_l), rot(pt_r), rot(pt_l))
    direction2 = rot(np.array([0.1, 0.2, 0.9]))
    angles2 = screw_angles(direction2, frame2)

    for key in angles1:
        assert abs(angles1[key] - angles2[key]) < 1e-6


def test_pelvic_tilt_zero_for_upright_pelvis():
    asis_r, asis_l, pt_r, pt_l = _known_points()
    frame = build_app(asis_r, asis_l, pt_r, pt_l)
    tilt = pelvic_tilt_deg(frame)
    assert tilt < 15.0
