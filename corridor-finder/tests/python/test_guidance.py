import numpy as np
import pytest

from corridor_engine.app_frame import Frame, scanner_frame
from corridor_engine.drr import load_views, project_point, render_view, view_rotation
from corridor_engine.guidance import describe_direction, down_the_barrel_view
from corridor_engine.volume import Volume

S = np.sqrt(0.5)


def _world(frame, local_xyz):
    """A direction given in frame coordinates (left, anterior, cephalad),
    expressed in RAS world coordinates."""
    lx, ly, lz = local_xyz
    return lx * frame.x_hat + ly * frame.y_hat + lz * frame.z_hat


def test_straight_cephalad_has_no_in_plane_direction():
    # Straight up the patient: the horizontal component is zero, which must
    # not produce a NaN or an arbitrary medial/lateral word.
    d = describe_direction((0.0, 0.0, 1.0), scanner_frame(), "right")
    assert d.elevation_deg == pytest.approx(90.0)
    assert d.elevation_word == "cephalad"
    assert not d.in_plane_defined
    assert d.in_plane_deg == 0.0
    assert d.in_plane_reference == ""
    assert d.sentence == "90 degrees cephalad, with no in-plane direction"

    down = describe_direction((0.0, 0.0, -1.0), scanner_frame(), "left")
    assert down.elevation_deg == pytest.approx(-90.0)
    assert down.elevation_word == "caudad"
    assert down.sentence == "90 degrees caudad, with no in-plane direction"


def test_medial_depends_on_the_screws_own_side():
    frame = scanner_frame()
    toward_patient_left = (-1.0, 0.0, 0.0)  # patient left is -x in RAS

    right = describe_direction(toward_patient_left, frame, "right")
    assert right.elevation_deg == pytest.approx(0.0)
    assert right.elevation_word == "in the axial plane"
    assert right.in_plane_deg == pytest.approx(0.0)
    assert right.in_plane_word == ""
    assert right.in_plane_reference == "medial"
    assert right.sentence == "in the axial plane, straight medial"

    # The same world direction is lateral for a screw on the left side...
    left = describe_direction(toward_patient_left, frame, "left")
    assert left.in_plane_reference == "lateral"
    assert left.sentence == "in the axial plane, straight lateral"

    # ...and a left-side screw is medial going the other way.
    left_medial = describe_direction((1.0, 0.0, 0.0), frame, "left")
    assert left_medial.in_plane_reference == "medial"
    assert left_medial.sentence == "in the axial plane, straight medial"


def test_cephalad_and_posterior_of_medial():
    frame = scanner_frame()
    # 45 degrees up, and in the axial plane 30 degrees posterior of straight
    # medial, for a right-side screw (medial = toward the patient's left).
    local = (
        np.cos(np.radians(45.0)) * np.cos(np.radians(30.0)),
        -np.cos(np.radians(45.0)) * np.sin(np.radians(30.0)),
        np.sin(np.radians(45.0)),
    )
    d = describe_direction(_world(frame, local), frame, "right")
    assert d.elevation_deg == pytest.approx(45.0)
    assert d.in_plane_deg == pytest.approx(-30.0)
    assert d.in_plane_word == "posterior"
    assert d.in_plane_reference == "medial"
    assert d.sentence == "45 degrees cephalad, and in the axial plane 30 degrees posterior of straight medial"

    # Straight posterior is a quarter turn from medial, and is said that way.
    straight_back = describe_direction((0.0, -S, S), frame, "right")
    assert straight_back.elevation_deg == pytest.approx(45.0)
    assert straight_back.in_plane_deg == pytest.approx(-90.0)
    assert straight_back.sentence == "45 degrees cephalad, and in the axial plane straight posterior"


def test_straight_anterior_in_the_axial_plane():
    d = describe_direction((0.0, 1.0, 0.0), scanner_frame(), "right")
    assert d.elevation_deg == pytest.approx(0.0)
    assert d.elevation_word == "in the axial plane"
    assert d.in_plane_deg == pytest.approx(90.0)
    assert d.in_plane_word == "anterior"
    assert d.sentence == "in the axial plane, straight anterior"


def test_midline_screw_is_described_left_right_not_medial_lateral():
    frame = scanner_frame()
    # A transsacral screw crossing the midline toward the patient's left,
    # 20 degrees anterior, level.
    local = (np.cos(np.radians(20.0)), np.sin(np.radians(20.0)), 0.0)
    d = describe_direction(_world(frame, local), frame, "midline")
    assert d.in_plane_deg == pytest.approx(20.0)
    assert d.in_plane_reference == "toward the patient's left"
    assert d.sentence == "in the axial plane, 20 degrees anterior of straight toward the patient's left"
    assert "medial" not in d.sentence and "lateral" not in d.sentence

    other_way = describe_direction((1.0, 0.0, 0.0), frame, "midline")
    assert other_way.in_plane_reference == "toward the patient's right"
    assert other_way.sentence == "in the axial plane, straight toward the patient's right"


def test_description_follows_the_frame_not_the_scanner_axes():
    # The same direction relative to the pelvis must read the same whether or
    # not the pelvis (and with it the APP frame) is tilted in the scanner.
    local = (0.6, -0.3, 0.74)
    upright = scanner_frame()
    theta = np.radians(20.0)
    c, s = np.cos(theta), np.sin(theta)
    rot = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    tilted = Frame(
        origin=np.zeros(3),
        x_hat=rot @ upright.x_hat,
        y_hat=rot @ upright.y_hat,
        z_hat=rot @ upright.z_hat,
    )

    a = describe_direction(_world(upright, local), upright, "left")
    b = describe_direction(_world(tilted, local), tilted, "left")
    assert a.sentence == b.sentence
    assert a.elevation_deg == pytest.approx(b.elevation_deg)
    assert a.in_plane_deg == pytest.approx(b.in_plane_deg)

    # ...and reading the tilted direction against the untilted frame must not
    # give the same answer, or the frame is being ignored.
    assert describe_direction(_world(tilted, local), upright, "left").sentence != a.sentence


def test_unknown_side_is_rejected():
    with pytest.raises(ValueError):
        describe_direction((0.0, 0.0, 1.0), scanner_frame(), "Left")


BARREL_DIRECTIONS = [
    (0.0, -1.0, 0.0),  # straight posterior: the plain AP beam
    (0.0, 0.0, 1.0),  # straight up the long axis
    (-S, -S, 0.0),  # toward the patient's left and posterior
    (0.5, -0.5, S),  # toward the patient's right, posterior and up
    (-0.6, 0.3, 0.74),
    (0.8, 0.0, -0.6),
]


def _dotted_line_volume(center, direction, half_len_mm=25.0, shape=(80, 80, 80)):
    """1 mm voxels, origin 0: a bright 3x3x3 block every mm along the segment
    ``center +- half_len_mm * direction`` (thick enough to survive trilinear
    resampling at any sub-voxel offset)."""
    hu = np.full(shape, -1000.0, dtype=np.float32)
    for t in np.arange(-half_len_mm, half_len_mm + 1.0):
        x, y, z = np.asarray(center, dtype=float) + t * np.asarray(direction, dtype=float)
        i, j, k = int(round(x)), int(round(y)), int(round(z))
        hu[k - 1:k + 2, j - 1:j + 2, i - 1:i + 2] = 1500.0
    return Volume(array=hu, spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0))


def test_barrel_view_collapses_the_trajectory_to_a_point():
    center = np.array([40.0, 40.0, 40.0])
    for direction in BARREL_DIRECTIONS:
        d = np.asarray(direction, dtype=float)
        d = d / np.linalg.norm(d)
        barrel = down_the_barrel_view(d)

        vol = _dotted_line_volume(center, d)
        view = render_view(vol, barrel.rotate_x_deg, barrel.rotate_z_deg, pixel_mm=1.0)

        col0, row0 = project_point(view, center - 40.0 * d)
        col1, row1 = project_point(view, center + 40.0 * d)
        assert np.hypot(col1 - col0, row1 - row0) < 1.0, direction

        # The rendered image must agree: an end-on 50 mm rod is a spot, and
        # nothing like the >= 50 px streak it makes in any other view.
        image = view.image
        assert (image > 0.5 * image.max()).sum() <= 40, direction


def test_barrel_angles_round_trip_through_view_rotation():
    for direction in BARREL_DIRECTIONS:
        d = np.asarray(direction, dtype=float)
        d = d / np.linalg.norm(d)
        barrel = down_the_barrel_view(d)
        beam = view_rotation(barrel.rotate_x_deg, barrel.rotate_z_deg)[2]
        assert np.allclose(beam, d, atol=1e-9), direction
        assert abs(barrel.rotate_x_deg) <= 90.0 + 1e-9, direction


def test_barrel_view_recovers_the_named_view_angles():
    # Every view in corridors.json is itself a down-the-barrel view of its own
    # beam, so the angles must come back unchanged.
    for name, (rx, rz) in load_views().items():
        beam = view_rotation(rx, rz)[2]
        barrel = down_the_barrel_view(beam)
        assert barrel.rotate_x_deg == pytest.approx(rx, abs=1e-9), name
        assert barrel.rotate_z_deg == pytest.approx(rz, abs=1e-9), name


def test_barrel_view_prefers_the_smaller_tilt():
    # A direction straight anterior is reachable either as no tilt with the
    # beam from behind, or as a 180 degree tilt; the flat one is the answer.
    barrel = down_the_barrel_view((0.0, 1.0, 0.0))
    assert barrel.rotate_x_deg == pytest.approx(0.0)
    assert abs(barrel.rotate_z_deg) == pytest.approx(180.0)
    assert np.allclose(view_rotation(barrel.rotate_x_deg, barrel.rotate_z_deg)[2], (0.0, 1.0, 0.0), atol=1e-9)


def test_barrel_reading_names_the_c_arm_position():
    assert down_the_barrel_view((0.0, -1.0, 0.0)).reading == "no cranio-caudal tilt, the beam straight from in front (AP)"
    assert down_the_barrel_view((0.0, -S, -S)).reading == "45 degrees of inlet (caudad) tilt, the beam straight from in front (AP)"
    assert down_the_barrel_view((0.0, -S, S)).reading == "45 degrees of outlet (cephalad) tilt, the beam straight from in front (AP)"

    # Beam toward the patient's left = C-arm tube on the patient's right.
    assert down_the_barrel_view((-1.0, 0.0, 0.0)).reading == (
        "no cranio-caudal tilt, a lateral, the beam entering from the patient's right"
    )
    assert down_the_barrel_view((S, -S, 0.0)).reading == (
        "no cranio-caudal tilt, 45 degrees oblique, the beam entering from the patient's left"
    )
    assert down_the_barrel_view((0.0, 0.0, 1.0)).reading == (
        "90 degrees of outlet (cephalad) tilt, the beam along the patient's long axis, from the feet"
    )


def test_barrel_view_is_exact_close_to_the_long_axis():
    """Half a degree off the long axis the roll still matters: the returned
    angles must aim the beam exactly along the screw even though the words
    fall back to "along the patient's long axis"."""
    d = np.array([np.sin(np.radians(0.5)), 0.0, np.cos(np.radians(0.5))])
    barrel = down_the_barrel_view(d)
    assert np.allclose(view_rotation(barrel.rotate_x_deg, barrel.rotate_z_deg)[2], d, atol=1e-9)
    assert "long axis" in barrel.reading
