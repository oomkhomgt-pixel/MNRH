import numpy as np
import pytest

from corridor_engine.fracture import fit_plane, past_fracture_mm

# A crescent-like fracture: the plane x = 10, marked at four points.
MARKS = [(10.0, 0.0, 0.0), (10.0, 20.0, 0.0), (10.0, 0.0, 20.0), (10.2, 15.0, 15.0)]


def test_the_plane_goes_through_the_marks():
    plane = fit_plane(MARKS)
    assert abs(abs(plane.normal[0]) - 1.0) < 1e-2
    assert plane.rms_mm < 0.2


def test_too_few_marks_or_marks_on_one_line_give_no_plane():
    assert fit_plane(MARKS[:2]) is None
    assert fit_plane([(10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (10.0, 20.0, 0.5)]) is None


def test_the_part_of_the_screw_past_the_fracture_is_measured_from_the_crossing():
    plane = fit_plane(MARKS)
    assert past_fracture_mm(plane, (-30.0, 5.0, 5.0), (50.0, 5.0, 5.0)) == pytest.approx(40.0, abs=0.3)
    # Oblique screw: along the screw, not along the normal.
    tip = np.array([10.0, 5.0, 5.0]) + 32.0 * np.array([np.cos(0.5), np.sin(0.5), 0.0])
    assert past_fracture_mm(plane, (-20.0, 5.0 - 30.0 * np.tan(0.5), 5.0), tip) == pytest.approx(32.0, abs=0.3)


def test_a_screw_that_stops_short_of_the_fracture_does_not_cross_it():
    plane = fit_plane(MARKS)
    assert past_fracture_mm(plane, (-30.0, 5.0, 5.0), (5.0, 5.0, 5.0)) is None


def test_crossing_the_plane_far_from_the_marked_fracture_does_not_count():
    plane = fit_plane(MARKS)
    assert past_fracture_mm(plane, (-30.0, 80.0, 80.0), (50.0, 80.0, 80.0)) is None
