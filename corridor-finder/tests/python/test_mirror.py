import numpy as np
import pytest

from corridor_engine import segmentation as seg
from corridor_engine.mirror import (
    MAX_MIRROR_TILT_DEG,
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
