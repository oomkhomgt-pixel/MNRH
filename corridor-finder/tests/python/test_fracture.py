import numpy as np
import pytest

from corridor_engine.fracture import fit_plane, fracture_gap, marks_near, off_square_deg, past_fracture_mm

# A crescent-like fracture: the plane x = 10, marked at four points.
MARKS = [(10.0, 0.0, 0.0), (10.0, 20.0, 0.0), (10.0, 0.0, 20.0), (10.2, 15.0, 15.0)]


def test_the_plane_goes_through_the_marks():
    plane = fit_plane(MARKS)
    assert abs(abs(plane.normal[0]) - 1.0) < 1e-2
    assert plane.rms_mm < 0.2


def test_too_few_marks_or_marks_on_one_line_give_no_plane():
    assert fit_plane(MARKS[:2]) is None
    assert fit_plane([(10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (10.0, 20.0, 0.5)]) is None


def test_the_surgeon_is_told_why_marks_give_no_plane():
    from corridor_engine.fracture import why_no_plane
    assert why_no_plane(MARKS) is None
    assert "mark 3 or more" in why_no_plane(MARKS[:2])
    assert "one line" in why_no_plane([(10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (10.0, 20.0, 0.5)])


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


def test_only_the_marks_near_the_screw_count():
    ramus = [(60.0, 0.0, 0.0), (60.0, 10.0, 0.0), (60.0, 0.0, 10.0)]
    near = marks_near(MARKS + ramus, (-30.0, 5.0, 5.0), (30.0, 5.0, 5.0), 25.0)
    assert len(near) == len(MARKS)


def test_square_to_the_fracture_is_zero_and_along_it_ninety():
    plane = fit_plane(MARKS)
    assert off_square_deg(plane, (1.0, 0.0, 0.0)) == pytest.approx(0.0, abs=1.0)
    assert off_square_deg(plane, (-1.0, 0.0, 0.0)) == pytest.approx(0.0, abs=1.0)
    assert off_square_deg(plane, (0.0, 1.0, 0.0)) == pytest.approx(90.0, abs=1.0)
    assert off_square_deg(plane, (1.0, 1.0, 0.0)) == pytest.approx(45.0, abs=1.0)


def test_a_fracture_gap_near_the_marks_counts_as_bone_and_nothing_else_does():
    """The surgeon: crossing a fracture is not a breach. A bar of bone
    broken across x = 30 with a 6 mm gap: the gap between the fragments is
    filled; the air beside the bar, and a gap far from the marks, are not."""
    labels = np.zeros((40, 40, 100), dtype=np.uint8)
    labels[10:30, 10:30, 5:95] = 2
    labels[10:30, 10:30, 27:33] = 0  # the fracture gap, 6 mm, at x 27..32
    labels[10:30, 10:30, 80:84] = 0  # another gap, far from the marks
    marks = [(30.0, 12.0, 12.0), (30.0, 27.0, 12.0), (30.0, 12.0, 27.0), (30.0, 25.0, 25.0)]
    gap = fracture_gap(labels, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0), 2, marks)
    assert gap[10:30, 10:30, 27:33].all(), "the whole gap between the fragments"
    assert not gap[:, :, 80:84].any(), "not a gap away from the marks"
    assert not gap[0:10].any() and not gap[30:].any() and not gap[:, 0:10].any(), "not the air beside the bar"
    assert fracture_gap(labels, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0), 2, marks[:2]) is None
