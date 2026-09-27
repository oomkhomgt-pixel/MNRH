import numpy as np
import pytest

from corridor_engine import segmentation as seg
from corridor_engine.mirror import (
    MAX_MIRROR_TILT_DEG,
    SACRUM_FRACTURE_PENALTY_MM,
    MirrorPlane,
    MirrorRefused,
    ReferenceNotConfirmed,
    confirm,
    fit_plane,
    fit_reference,
    preselect,
    reference_mask,
)
from corridor_engine.phantoms import fractured_pelvis
from corridor_engine.volume import Volume


@pytest.fixture(scope="module")
def turned_pelvis():
    """The intact phantom, turned 6 degrees about the scanner's long axis,
    so its mirror plane is not a plane of the voxel grid."""
    p = fractured_pelvis(yaw_deg=6.0)
    return Volume(p.labels, p.spacing, p.origin)


@pytest.fixture(scope="module")
def turned_reference(turned_pelvis):
    return fit_reference(turned_pelvis)


def test_the_plane_is_found_through_a_turned_patient(turned_reference):
    ref = turned_reference
    truth = np.array([np.cos(np.radians(6.0)), np.sin(np.radians(6.0)), 0.0])
    for name, plane in ref.fits.items():
        off = np.degrees(np.arccos(abs(float(plane.normal @ truth))))
        print(f"{name}: {off:.2f} degrees off the true plane, offset {plane.offset_mm:.2f} mm, "
              f"tilt {plane.tilt_deg:.2f}, self-symmetry p50/p90 {plane.self_symmetry_p50_mm:.2f}/"
              f"{plane.self_symmetry_p90_mm:.2f} mm")
        assert off < 1.0
        assert abs(plane.offset_mm) < 1.0  # the plane passes through the midline
        assert plane.tilt_deg < 1.0 and not plane.refused
    # A symmetric sacrum costs the fit nothing, so it is not pre-selected as
    # fractured, and the two references agree on where the mirror puts the
    # hemipelvis.
    assert not ref.sacrum_fractured_preselected
    assert ref.reference_preselected == "l5_and_central_sacrum"
    assert ref.disagreement_mm < 2.0


def test_l5_is_the_lowest_35_mm_of_the_lumbar_label(turned_pelvis):
    l5 = reference_mask(turned_pelvis, "l5")
    lumbar = turned_pelvis.array == seg.LUMBAR
    z = turned_pelvis.origin[2] + np.arange(lumbar.shape[0]) * turned_pelvis.spacing[2]
    assert z[l5.any(axis=(1, 2))].max() - z[lumbar.any(axis=(1, 2))].min() <= 35.0
    assert (lumbar & ~l5).any()  # L4 is left out


def test_nothing_is_used_until_the_sacrum_is_confirmed(turned_reference):
    """Unconfirmed means refuse, with the pre-selection in the reason, never
    a silent default (DECISIONS 2.1a)."""
    ref = turned_reference
    with pytest.raises(ReferenceNotConfirmed, match="sacrum pre-selected as intact"):
        confirm(ref, sacrum_fractured=None)


def test_every_confirmation_records_the_reference_and_whether_it_was_overridden(turned_reference):
    ref = turned_reference
    agreed = confirm(ref, sacrum_fractured=False)
    assert agreed.reference == "l5_and_central_sacrum" and agreed.choice == "pre-selection"
    overridden = confirm(ref, sacrum_fractured=True)
    assert overridden.reference == "l5" and overridden.choice == "override"
    assert "override" in overridden.sentence() and "l5 plane" in overridden.sentence()
    assert agreed.uncertainty_mm == pytest.approx(ref.disagreement_mm)


def _plane(reference, cost, tilt):
    refused = f"{reference} is {tilt:.0f} degrees off" if tilt > MAX_MIRROR_TILT_DEG else ""
    return MirrorPlane(reference, np.array([1.0, 0.0, 0.0]), 0.0, cost, 1.0, 2.0, tilt, 1000, refused)


def test_when_the_gate_refuses_the_rules_plane_the_other_is_preselected_with_a_warning():
    """3 of 278 L5-alone fits came out 71-77 degrees off. The penalty here
    says fractured (so L5 alone), but L5 alone was refused."""
    ref = preselect({"l5": _plane("l5", 1.3, 74.0), "l5_and_central_sacrum": _plane("l5_and_central_sacrum", 2.2, 3.0)},
                    disagreement_mm=1.5)
    assert ref.sacrum_fractured_preselected
    assert ref.reference_preselected == "l5_and_central_sacrum"
    assert any("pre-selected instead" in w for w in ref.warnings)
    # The rule's plane cannot be used even when confirmed; the other can,
    # and choosing it is what was pre-selected.
    with pytest.raises(MirrorRefused, match="can be chosen explicitly"):
        confirm(ref, sacrum_fractured=True)
    used = confirm(ref, sacrum_fractured=True, reference="l5_and_central_sacrum")
    assert used.choice == "pre-selection"
    # With no second plane to compare, the uncertainty falls back to the
    # plane's own asymmetry, and says so.
    assert used.uncertainty_mm == pytest.approx(2.0)
    assert any("self-symmetry" in w for w in used.warnings)


def test_a_plane_far_off_the_hip_axis_is_refused():
    """A lumbar body whose only symmetry planes are at least 45 degrees off
    the line between the hips: the gate must refuse whatever is fitted."""
    labels = np.zeros((60, 80, 120), dtype=np.uint8)
    zz, yy, xx = np.mgrid[0:60, 0:80, 0:120].astype(float)
    labels[(np.abs(xx - 25) < 12) & (np.abs(yy - 40) < 15) & (zz < 30)] = seg.HIP_L
    labels[(np.abs(xx - 95) < 12) & (np.abs(yy - 40) < 15) & (zz < 30)] = seg.HIP_R
    axis = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    rel = np.stack([xx - 60, yy - 40, zz - 45])
    along = np.einsum("i,i...->...", axis, rel)
    across = np.linalg.norm(rel - along * axis[:, None, None, None], axis=0)
    labels[(along > -12) & (along < 12) & (across < 0.5 * (12 - along))] = seg.LUMBAR  # a cone
    plane = fit_plane(Volume(labels, (1.0, 1.0, 1.0)), "l5")
    assert plane.tilt_deg > 40.0
    assert plane.refused and "gate" in plane.refused


def test_no_lumbar_spine_means_no_reference():
    p = fractured_pelvis(spacing_mm=3.0)
    labels = p.labels.copy()
    labels[labels == seg.LUMBAR] = 0
    with pytest.raises(MirrorRefused, match="no lumbar spine"):
        fit_reference(Volume(labels, p.spacing, p.origin))


def _hips_around_a_symmetric_l5(hip_axis_deg):
    """An L5 whose only mirror plane is x = 0 (tapered front to back and
    taller in front, so no other plane fits it), with the two hip bones
    placed on a line ``hip_axis_deg`` off the x axis. Whatever plane is
    fitted is x = 0, so its tilt off the hips is ``hip_axis_deg``."""
    labels = np.zeros((60, 90, 160), dtype=np.uint8)
    zz, yy, xx = np.mgrid[0:60, 0:90, 0:160].astype(float)
    x, y, z = xx - 80.0, yy - 45.0, zz
    labels[(np.abs(x) <= 14.0 - 0.2 * y) & (np.abs(y) < 15.0) & (z > 30.0) & (z < 50.0 + 0.3 * y)] = seg.LUMBAR
    a = np.radians(hip_axis_deg)
    for label, sign in ((seg.HIP_R, 1.0), (seg.HIP_L, -1.0)):
        cx, cy = sign * 55.0 * np.cos(a), sign * 55.0 * np.sin(a)
        labels[(np.abs(x - cx) < 10.0) & (np.abs(y - cy) < 10.0) & (z < 25.0)] = label
    return Volume(labels, (1.0, 1.0, 1.0))


@pytest.mark.parametrize("hip_axis_deg, refused", [(12.0, False), (18.0, True)])
def test_the_tilt_gate_sits_at_15_degrees(hip_axis_deg, refused):
    """The same good plane, judged against hips 12 and 18 degrees off it:
    under the 15 degree gate it is used, over it it is refused. The cone
    test above only shows a 45 degree plane is refused, which a gate at 30
    or 40 degrees would also do."""
    assert MAX_MIRROR_TILT_DEG == 15.0
    vol = _hips_around_a_symmetric_l5(hip_axis_deg)
    plane = fit_plane(vol, "l5")
    off_x = np.degrees(np.arccos(abs(float(plane.normal[0]))))
    # The hips' own axis, as voxelised (the blocks round onto the grid).
    right = np.argwhere(vol.array == seg.HIP_R).mean(axis=0)
    left = np.argwhere(vol.array == seg.HIP_L).mean(axis=0)
    axis_deg = np.degrees(np.arctan2(right[1] - left[1], right[2] - left[2]))
    print(f"\nhips {hip_axis_deg:.0f} degrees off: plane {off_x:.2f} degrees off x, tilt {plane.tilt_deg:.2f}, "
          f"refused: {plane.refused or 'no'}")
    assert off_x < 0.5  # the fit itself is right; only the gate decides
    assert abs(axis_deg - hip_axis_deg) < 1.0
    assert plane.tilt_deg == pytest.approx(axis_deg, abs=0.5)
    assert bool(plane.refused) is refused
    if refused:
        assert f"{plane.tilt_deg:.1f} degrees off" in plane.refused and "15 degree gate" in plane.refused


def test_when_the_gate_refuses_the_intact_sacrum_plane_l5_alone_is_preselected():
    """The other direction of the fallback: the penalty says intact (so L5
    + central sacrum), that plane was refused, and L5 alone is offered."""
    ref = preselect({"l5": _plane("l5", 1.3, 4.0), "l5_and_central_sacrum": _plane("l5_and_central_sacrum", 1.5, 40.0)},
                    disagreement_mm=1.5)
    assert not ref.sacrum_fractured_preselected
    assert ref.reference_preselected == "l5"
    assert any("l5 pre-selected instead" in w for w in ref.warnings)
    with pytest.raises(MirrorRefused, match="l5 passed the gate and can be chosen explicitly"):
        confirm(ref, sacrum_fractured=False)
    used = confirm(ref, sacrum_fractured=False, reference="l5")
    assert used.reference == "l5" and used.choice == "pre-selection" and not used.sacrum_fractured


def test_when_the_gate_refuses_both_planes_nothing_is_preselected_or_usable():
    ref = preselect({"l5": _plane("l5", 1.3, 74.0), "l5_and_central_sacrum": _plane("l5_and_central_sacrum", 1.5, 40.0)},
                    disagreement_mm=1.5)
    assert ref.reference_preselected is None
    assert "none, the gate refused both" in ref.preselection_sentence()
    for fractured, reference in ((True, None), (False, None), (True, "l5_and_central_sacrum"), (False, "l5")):
        with pytest.raises(MirrorRefused) as refused:
            confirm(ref, sacrum_fractured=fractured, reference=reference)
        assert "degrees off" in str(refused.value) and "can be chosen explicitly" not in str(refused.value)


@pytest.mark.parametrize("reference", [None, "l5", "l5_and_central_sacrum"])
def test_naming_a_reference_does_not_stand_in_for_confirming_the_sacrum(reference):
    """Choosing a plane explicitly is not the surgeon's answer on the
    sacrum; unconfirmed still refuses, whatever else is given."""
    ref = preselect({"l5": _plane("l5", 1.3, 3.0), "l5_and_central_sacrum": _plane("l5_and_central_sacrum", 2.2, 3.0)},
                    disagreement_mm=1.5)
    with pytest.raises(ReferenceNotConfirmed, match="has not been confirmed"):
        confirm(ref, sacrum_fractured=None, reference=reference)


@pytest.mark.parametrize("penalty_mm, fractured", [(0.69, False), (0.70, True), (0.71, True)])
def test_sacrum_fractured_is_preselected_from_a_penalty_of_0_70_mm(penalty_mm, fractured):
    """DECISIONS 2.1a: 0.70 mm pre-selects all four surgeon-read fractures
    (0.73-0.99) and 14% of normals. At the threshold it pre-selects."""
    assert SACRUM_FRACTURE_PENALTY_MM == 0.70
    ref = preselect({"l5": _plane("l5", 1.0, 3.0), "l5_and_central_sacrum": _plane("l5_and_central_sacrum", 1.0 + penalty_mm, 3.0)},
                    disagreement_mm=1.5)
    assert ref.penalty_mm == pytest.approx(penalty_mm)
    assert ref.sacrum_fractured_preselected is fractured
    assert ref.reference_preselected == ("l5" if fractured else "l5_and_central_sacrum")
