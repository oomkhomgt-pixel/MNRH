import numpy as np

from corridor_engine.app_frame import build_app, screw_angles, pelvic_tilt_deg, scanner_frame


def _known_points():
    # RAS world coordinates, the engine's convention (x = patient right+,
    # y = anterior+, z = superior+), so the RIGHT ASIS is at +x. A tidy,
    # roughly-anatomical arrangement: ASIS ~200mm apart, pubic tubercles
    # ~20mm apart, anterior/inferior to the ASIS.
    asis_r = np.array([100.0, 0.0, 300.0])
    asis_l = np.array([-100.0, 0.0, 300.0])
    pt_r = np.array([10.0, 20.0, 100.0])
    pt_l = np.array([-10.0, 20.0, 100.0])
    return asis_r, asis_l, pt_r, pt_l


def _rotate_about_x(points, deg):
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    R = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    return [R @ p for p in points]


def test_build_app_axes_orthonormal_and_oriented():
    asis_r, asis_l, pt_r, pt_l = _known_points()
    frame = build_app(asis_r, asis_l, pt_r, pt_l)

    assert abs(np.linalg.norm(frame.x_hat) - 1.0) < 1e-9
    assert abs(np.linalg.norm(frame.y_hat) - 1.0) < 1e-9
    assert abs(np.linalg.norm(frame.z_hat) - 1.0) < 1e-9
    assert abs(np.dot(frame.x_hat, frame.y_hat)) < 1e-9
    assert abs(np.dot(frame.y_hat, frame.z_hat)) < 1e-9
    assert abs(np.dot(frame.x_hat, frame.z_hat)) < 1e-9

    # Anatomical axes: x_hat toward the patient's left (-x in RAS), y_hat
    # anterior (+y), z_hat cephalad (+z).
    assert frame.x_hat[0] < -0.9
    assert frame.y_hat[1] > 0.5
    assert frame.z_hat[2] > 0.9


def test_app_frame_stays_anatomical_under_pelvic_tilt():
    # The APP normal must stay anterior and z_hat cephalad for a pelvis
    # tilted either way. (Before the anterior hint was added, the normal's
    # sign was only fixed indirectly and came out POSTERIOR for any RAS
    # input, flipping the sign of every reported anteversion.)
    for tilt_deg in (-25.0, 0.0, 25.0):
        frame = build_app(*_rotate_about_x(_known_points(), tilt_deg))
        assert frame.x_hat[0] < -0.9, tilt_deg
        assert frame.y_hat[1] > 0.8, tilt_deg
        assert frame.z_hat[2] > 0.8, tilt_deg


def test_angle_signs_are_anatomical():
    frame = build_app(*_known_points())
    toward_left_and_up = np.array([-0.5, 0.0, np.sqrt(0.75)])  # patient left is -x in RAS
    toward_front_and_up = np.array([0.0, 0.5, np.sqrt(0.75)])
    assert screw_angles(toward_left_and_up, frame)["inclination_deg"] > 0
    assert screw_angles(toward_front_and_up, frame)["anteversion_deg"] > 0
    assert screw_angles(toward_front_and_up * np.array([1, -1, 1]), frame)["anteversion_deg"] < 0


def test_scanner_frame_matches_app_for_untilted_pelvis():
    # With the APP exactly in the scanner's coronal plane the two frames have
    # the same anatomical axes, so the "APP" and "scanner" angle columns of
    # the report must agree.
    asis_r, asis_l = np.array([100.0, 0.0, 300.0]), np.array([-100.0, 0.0, 300.0])
    pt_r, pt_l = np.array([10.0, 0.0, 100.0]), np.array([-10.0, 0.0, 100.0])
    app = build_app(asis_r, asis_l, pt_r, pt_l)
    for direction in (np.array([0.3, -0.4, 0.866]), np.array([-0.6, 0.2, 0.77])):
        a, s = screw_angles(direction, app), screw_angles(direction, scanner_frame())
        for key in a:
            assert abs(a[key] - s[key]) < 1e-9, key


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
