import numpy as np
import pytest

from corridor_engine import segmentation as seg
from corridor_engine.landmarks import Landmark
from corridor_engine.si_joint import (
    MAX_BRIDGE_MM,
    bridging_widths,
    looks_disrupted,
    measure_joint_widths,
)
from corridor_engine.volume import Volume

SPACING = (1.0, 1.0, 1.0)


def _pelvis(right_gap=3.0, left_gap=6.0, wide_behind=True, right_back=0.0, right_up=0.0):
    """Sacrum between two hip bones, with a chosen gap on each side. The
    posterior part of the right joint is left much wider, standing in for
    the interosseous ligament's space, which is not the joint. The right
    hemipelvis can also be slid back (``right_back``) and up
    (``right_up``), which is a step and not a gap."""
    labels = np.zeros((60, 80, 120), dtype=np.uint8)
    zz, yy, xx = np.mgrid[0:60, 0:80, 0:120]
    sacrum = (xx >= 50) & (xx <= 70) & (yy >= 20) & (yy <= 60) & (zz >= 10) & (zz <= 50)
    labels[sacrum] = seg.SACRUM
    right = ((xx >= 70 + right_gap) & (xx <= 100)
             & (yy >= 20 - right_back) & (yy <= 60 - right_back)
             & (zz >= 10 + right_up) & (zz <= 50 + right_up))
    if wide_behind:
        right &= ~((yy < 30 - right_back) & (xx < 82))  # the posterior third, 12 mm across
    labels[right] = seg.HIP_R
    left = (xx >= 20) & (xx <= 50 - left_gap) & (yy >= 20) & (yy <= 60) & (zz >= 10) & (zz <= 50)
    labels[left] = seg.HIP_L
    landmarks = {
        "s1_body_center": Landmark(np.array([60.0, 40.0, 40.0])),
        "s2_body_center": Landmark(np.array([60.0, 40.0, 25.0])),
    }
    return Volume(labels, SPACING), landmarks


def test_each_joint_is_measured_at_the_s1_s2_level():
    volume, landmarks = _pelvis(right_gap=3.0, left_gap=6.0)
    widths = measure_joint_widths(volume, landmarks)

    assert widths["right"].measured_mm == pytest.approx(3.0, abs=0.6)
    assert widths["left"].measured_mm == pytest.approx(6.0, abs=0.6)
    # One measurement per level through the band, not one per voxel.
    assert widths["right"].n_samples > 20 and widths["left"].n_samples > 20
    assert widths["right"].band_z_mm == (20.0, 45.0)
    # Neither hemipelvis is displaced along the joint here.
    assert widths["right"].step_mm == pytest.approx(0.0, abs=0.6)
    assert widths["left"].step_mm == pytest.approx(0.0, abs=0.6)
    # Over the cap, so the panel says so before anything is bridged.
    assert "capped" in widths["left"].warning and not widths["right"].warning
    # This phantom's joint runs perfectly straight up and down, so a shift
    # along it would leave no trace, and the sentence says so rather than
    # reporting a shift of zero.
    assert widths["right"].sentence() == (
        "right SI joint: anterior gap 3.0 mm, step 0.0 mm "
        "(no step across the joint; up or down cannot be told from it)")
    assert not widths["right"].cephalad_known
    # What a bridge covers is what a narrower one costs: the measured width
    # covers its 90% by construction, and 2 mm of a 3 mm joint covers almost
    # none of it.
    assert widths["right"].covers(widths["right"].measured_mm) >= 0.9
    assert widths["right"].covers(2.0) < 0.1
    assert widths["left"].sentence(4.0).endswith("covers 0% of it (measured 6.0 mm, capped at 4.0 mm)")


def test_a_hemipelvis_displaced_along_the_joint_is_measured_as_a_step():
    """The gap can be normal while the hemipelvis has slid: 8 mm back and
    5 mm up here, which is what the anterior margins are compared for."""
    volume, landmarks = _pelvis(right_gap=3.0, right_back=8.0, right_up=5.0)
    right = measure_joint_widths(volume, landmarks)["right"]

    assert right.measured_mm == pytest.approx(3.0, abs=0.8), "sliding along the joint is not a wider joint"
    assert right.step_mm == pytest.approx(8.0, abs=1.5)
    assert right.step_anterior_mm == pytest.approx(-8.0, abs=1.5), "the ilium sits behind the sacrum"
    assert "behind" in right.step_sentence()
    assert "step 8" in right.sentence() or "step 7" in right.sentence()


def test_a_step_counts_as_much_as_a_gap_when_offering_a_disrupted_side():
    volume, landmarks = _pelvis(right_gap=3.0, left_gap=3.0, right_back=8.0)
    assert looks_disrupted(measure_joint_widths(volume, landmarks)) == "right"


def test_the_ligament_space_behind_the_joint_is_not_the_joint():
    with_gap, landmarks = _pelvis(right_gap=3.0, wide_behind=True)
    without, _ = _pelvis(right_gap=3.0, wide_behind=False)
    wide = measure_joint_widths(with_gap, landmarks)["right"]
    plain = measure_joint_widths(without, landmarks)["right"]
    assert wide.measured_mm == pytest.approx(plain.measured_mm, abs=0.3)


def test_a_disrupted_joint_takes_the_intact_sides_width():
    volume, landmarks = _pelvis(right_gap=3.0, left_gap=6.0)
    widths = measure_joint_widths(volume, landmarks)

    # The left one measures 6 mm, which on a pre-reduction CT is the injury,
    # not an anatomical width: it takes the right side's 3 mm.
    assert bridging_widths(widths, "left")["left"] == pytest.approx(3.0, abs=0.6)
    assert bridging_widths(widths, "left")["right"] == pytest.approx(3.0, abs=0.6)
    # Undisrupted, each joint keeps its own, capped.
    each = bridging_widths(widths, "none")
    assert each["right"] == pytest.approx(3.0, abs=0.6) and each["left"] == MAX_BRIDGE_MM
    # Both disrupted: nothing to measure from, so the cap.
    assert bridging_widths(widths, "both") == {"right": MAX_BRIDGE_MM, "left": MAX_BRIDGE_MM}
    with pytest.raises(ValueError):
        bridging_widths(widths, "right side")


def test_a_clearly_wider_joint_is_offered_as_the_disrupted_one():
    volume, landmarks = _pelvis(right_gap=3.0, left_gap=6.0)
    assert looks_disrupted(measure_joint_widths(volume, landmarks)) == "left"

    even, landmarks_even = _pelvis(right_gap=3.0, left_gap=4.0)
    assert looks_disrupted(measure_joint_widths(even, landmarks_even)) is None


def test_missing_sacral_landmarks_are_reported_not_guessed():
    volume, _ = _pelvis()
    widths = measure_joint_widths(volume, {})
    assert all(not np.isfinite(w.measured_mm) and w.n_samples == 0 for w in widths.values())
    assert "S1 and S2" in widths["right"].warning
    # With nothing measured, both sides fall back to the cap rather than to
    # a number nobody checked.
    assert bridging_widths(widths, "none") == {"right": MAX_BRIDGE_MM, "left": MAX_BRIDGE_MM}


def _profiled(up=0.0):
    """Sacrum and right hip whose anterior margins have relief along z: the
    front of each bone waves by 4 mm, in step, so a hemipelvis moved up
    carries its wave up with it. That is the only kind of joint on which an
    up-or-down shift can be measured at all."""
    labels = np.zeros((70, 80, 120), dtype=np.uint8)
    zz, yy, xx = np.mgrid[0:70, 0:80, 0:120]
    front_sacrum = 55 + 4.0 * np.sin(zz / 4.0)
    labels[(xx >= 50) & (xx <= 70) & (yy >= 20) & (yy <= front_sacrum) & (zz >= 10) & (zz <= 60)] = seg.SACRUM
    front_hip = 55 + 4.0 * np.sin((zz - up) / 4.0)
    labels[(xx >= 73) & (xx <= 100) & (yy >= 20) & (yy <= front_hip) & (zz >= 10 + up) & (zz <= 60 + up)] = seg.HIP_R
    labels[(xx >= 20) & (xx <= 47) & (yy >= 20) & (yy <= front_sacrum) & (zz >= 10) & (zz <= 60)] = seg.HIP_L
    landmarks = {"s1_body_center": Landmark(np.array([60.0, 40.0, 50.0])),
                 "s2_body_center": Landmark(np.array([60.0, 40.0, 25.0]))}
    return Volume(labels, SPACING), landmarks


def test_an_undisplaced_joint_is_not_read_as_shifted_down():
    """On eight joints the surgeon reads as intact, the old matching always
    answered "below", by a whole number of slices: it costed shifts on the
    ends of the trace, where interpolation holds the end value flat."""
    volume, landmarks = _profiled(up=0.0)
    right = measure_joint_widths(volume, landmarks)["right"]
    assert right.cephalad_known
    assert right.step_cephalad_mm == pytest.approx(0.0, abs=0.6)


def test_a_hemipelvis_moved_up_is_read_as_up():
    volume, landmarks = _profiled(up=5.0)
    right = measure_joint_widths(volume, landmarks)["right"]
    assert right.cephalad_known
    # The direction is right; the size reads short. On this phantom a true
    # 3, 5 or 8 mm shift comes back as about 2, 3.8 and 6.8 mm, the same
    # either way up, because each bone's anterior margin is read within a
    # few millimetres of the joint's front end, which blunts the profile
    # being matched. Recorded here so a change that makes it worse, or
    # better, is seen.
    assert 3.0 <= right.step_cephalad_mm <= 5.5
    assert "above" in right.step_sentence()
    down = measure_joint_widths(*_profiled(up=-5.0))["right"]
    assert -5.5 <= down.step_cephalad_mm <= -3.0 and "below" in down.step_sentence()




def test_a_step_both_joints_share_is_anatomy_and_does_not_hide_a_gap():
    """The surgeon, 2026-10-05: a symmetric step is this patient's anatomy;
    only a difference between the sides counts, by gap or by step."""
    from corridor_engine.si_joint import JointWidth, shared_step_sentence

    def joint(side, gap, step):
        return JointWidth(side=side, measured_mm=gap, n_samples=10, band_z_mm=(0.0, 10.0), step_mm=step)

    same = {"right": joint("right", 3.0, 4.0), "left": joint("left", 3.0, 4.0)}
    assert looks_disrupted(same) is None
    assert "anatomy" in shared_step_sentence(same)
    # A shared 4 mm step must not hide a 3 mm difference in the gap.
    wider = {"right": joint("right", 6.0, 4.0), "left": joint("left", 3.0, 4.0)}
    assert looks_disrupted(wider) == "right"
    # A step on one side only is a difference.
    slid = {"right": joint("right", 3.0, 1.0), "left": joint("left", 3.0, 4.5)}
    assert looks_disrupted(slid) == "left"
    assert shared_step_sentence(slid) is None
