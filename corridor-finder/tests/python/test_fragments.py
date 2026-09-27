"""The tests that decide whether the fragment finder is real (slice 1 plan):
the phantom's known transform recovered, printed in mm and degrees; the
null tests; the mirror's self-consistency; and the virtual reduction round
trip that Corridor Finder relies on. All on the phantom turned 6 degrees,
so the mirror plane is not a plane of the voxel grid and the two sides are
not voxel-identical: the untilted phantom is exactly symmetric, which makes
a null test too easy."""
import dataclasses

import numpy as np
import pytest
from scipy import ndimage as ndi

from corridor_engine import fragments as fragment_finder
from corridor_engine import mirror
from corridor_engine import segmentation as seg
from corridor_engine.fragments import (
    MIN_FRAGMENT_ACETABULAR_CM3,
    TO_REFERENCE_NOT_VALIDATED,
    Fragment,
    FragmentSet,
    articular_surface,
    find_fragments,
    reduce_labels,
)
from corridor_engine.mirror import ReferenceNotConfirmed, reflection_matrix
from corridor_engine.phantoms import fractured_pelvis
from corridor_engine.register import invert, rotation_deg, transform_points, travel_mm
from corridor_engine.volume import Volume

YAW_DEG = 6.0


def _case(**move):
    phantom = fractured_pelvis(yaw_deg=YAW_DEG, **move)
    vol = Volume(phantom.labels, phantom.spacing, phantom.origin)
    ref = mirror.fit_reference(vol)
    confirmed = mirror.confirm(ref, sacrum_fractured=ref.sacrum_fractured_preselected)
    found = find_fragments(vol, confirmed, "right", articular=articular_surface(vol, "right"))
    return phantom, vol, confirmed, found


@pytest.fixture(scope="module")
def undisplaced():
    return _case()


@pytest.fixture(scope="module")
def moved_10mm():
    """Fact 4's case: a true 10 mm / 8 degree fragment."""
    return _case(translate_mm=(4.0, 3.0, 8.5), rotate_deg=8.0, rotate_axis=(1.0, 0.3, 0.2))


@pytest.fixture(scope="module")
def moved_5mm():
    """Where clinical displacement starts: 5 mm, at which fact 4's
    residual split was at chance."""
    return _case(translate_mm=(2.0, 1.5, 4.3))


# Searched from the main body's transform alone, the fragment was found at
# 10 and 15 mm and missed at each of these, and the finder said "one body"
# with the fragment inside it, no warning and no rejected candidate.
@pytest.fixture(scope="module")
def moved_20mm():
    return _case(translate_mm=(0.0, 0.0, 20.0))


@pytest.fixture(scope="module")
def moved_30mm():
    return _case(translate_mm=(0.0, 0.0, 30.0))


@pytest.fixture(scope="module")
def moved_23mm_turned():
    """5, 5 and 18 mm and 10 degrees: 23.3 mm at its furthest voxel."""
    return _case(translate_mm=(5.0, 5.0, 18.0), rotate_deg=10.0)


def _the_fragment(phantom, found):
    """The found body that is the phantom's fragment; fails if none is."""
    assert len(found.fragments) == 2, found.sentence() + "".join(f"; {c.reasons}" for c in found.rejected)
    fragment = found.fragments[1]
    recall = (fragment.mask & phantom.fragment).sum() / phantom.fragment.sum()
    purity = (fragment.mask & phantom.fragment).sum() / fragment.mask.sum()
    print(f"fragment mask: {recall:.2f} of the true fragment, {purity:.2f} of it true")
    assert recall >= 0.9 and purity >= 0.9
    return fragment


def _errors(found_transform, truth, points):
    worst = np.linalg.norm(transform_points(found_transform, points) - transform_points(truth, points), axis=1)
    centre = points.mean(axis=0)[None, :]
    at_centre = float(np.linalg.norm(transform_points(found_transform, centre) - transform_points(truth, centre)))
    return at_centre, rotation_deg(found_transform @ invert(truth)), float(worst.max())


@pytest.mark.parametrize("case", ["moved_10mm", "moved_5mm", "moved_20mm", "moved_30mm", "moved_23mm_turned"])
def test_the_phantoms_known_transform_is_recovered(case, request):
    phantom, vol, _, found = request.getfixturevalue(case)
    fragment = _the_fragment(phantom, found)
    points = vol.mask_voxel_centers_world(phantom.fragment)
    true_travel = np.linalg.norm(transform_points(phantom.to_reference, points) - points, axis=1).max()
    # The phantom's main body did not move, so the truth is the same
    # transform both ways; to_parent is also free of the plane's own error.
    home = _errors(fragment.to_reference, phantom.to_reference, points)
    relative = _errors(fragment.to_parent, phantom.to_reference, points)
    print(f"\n{case}: true travel {true_travel:.1f} mm; to_reference off by {home[0]:.2f} mm at the fragment's "
          f"centroid, {home[1]:.2f} degrees, {home[2]:.2f} mm at its worst point; to_parent off by "
          f"{relative[0]:.2f} mm, {relative[1]:.2f} degrees, {relative[2]:.2f} mm (reported residual "
          f"{fragment.residual_mm:.2f} mm, plane uncertainty {fragment.plane_uncertainty_mm:.2f} mm; "
          f"for scale, Zeng et al. 2024 report 2.88 mm and 3.18 degrees on real cases)")
    for at_centre, degrees, worst in (home, relative):
        assert worst <= 2.0 * max(vol.spacing)  # two voxels at the phantom's 1.5 mm
        assert degrees <= 2.0


def test_null_an_undisplaced_pelvis_is_one_body(undisplaced):
    """Fact 4 is this failing: with no fragment present, a split into two
    bodies was reported travelling 7.8 and 4.1 mm."""
    _, _, confirmed, found = undisplaced
    main = found.fragments[0]
    print(f"\nundisplaced: {found.sentence()}; main body rotation {rotation_deg(main.to_reference):.2f} degrees, "
          f"from the plane itself ({confirmed.reference}); not promoted: {[c.reasons for c in found.rejected]}")
    assert len(found.fragments) == 1


def _own_mirror(undisplaced):
    """The right hip replaced by the left one mirrored across the confirmed
    plane, voxel for voxel."""
    phantom, vol, confirmed, _ = undisplaced
    labels = phantom.labels.copy()
    labels[labels == seg.HIP_R] = 0
    idx = np.argwhere(np.ones(labels.shape, dtype=bool))
    source = np.rint(vol.world_to_zyx_indices(confirmed.plane.reflect(vol.zyx_indices_to_world(idx)))).astype(int).T
    inside = np.all((source >= 0) & (source < np.array(labels.shape)), axis=1)
    hit = np.zeros(len(idx), dtype=bool)
    hit[inside] = phantom.labels[tuple(source[inside].T)] == seg.HIP_L
    right = np.zeros(labels.shape, dtype=bool)
    right[tuple(idx[hit].T)] = True
    labels[right & (labels == 0)] = seg.HIP_R
    return Volume(labels, vol.spacing, vol.origin), confirmed


def test_null_and_self_consistency_an_intact_hemipelvis_against_its_own_mirror(undisplaced):
    """One body, and about zero displacement: below the case's own floor,
    and still reported as a number with the flag (DECISIONS 1.4)."""
    vol, confirmed = _own_mirror(undisplaced)
    found = find_fragments(vol, confirmed, "right")
    main = found.fragments[0]
    print(f"\nown mirror: {found.sentence()}")
    assert len(found.fragments) == 1
    assert found.unexplained_cm3 == 0.0 and not found.unexplained.any()
    assert main.below_floor and main.travel_mm < found.residual_floor_mm
    assert main.travel_mm > 0.0  # a number, not zeroed
    assert rotation_deg(main.to_reference) < 0.5


def test_virtual_reduction_puts_the_fragment_back(moved_10mm):
    """What Corridor Finder calls, held to DECISIONS 2.3's reading of the
    budget: the residual reported for the fragment plus the plane
    uncertainty its to_reference carries. This is NOT the plan's test 6
    (the residual alone): that is
    test_virtual_reduction_lands_the_fragment_within_its_reported_residual,
    and which budget applies awaits a ruling. Measured where the transform
    sends each voxel before rounding onto the grid, so an exact transform
    reads zero: distances between voxel surfaces read 1.5 mm at p90 even
    with the exact transform on this 1.5 mm grid, and cannot tell it from
    one about 1 mm off. The rounding reduce_labels does is tested on its
    own, with the exact transform, below."""
    phantom, vol, _, found = moved_10mm
    fragment = _the_fragment(phantom, found)
    error = _landing_error(fragment.to_reference, phantom.to_reference,
                           vol.mask_voxel_centers_world(fragment.mask & phantom.fragment))
    p90 = float(np.percentile(error, 90))
    budget = fragment.residual_mm + fragment.plane_uncertainty_mm
    print(f"\nlanding error of the reduced fragment: p50 {np.median(error):.2f} mm, p90 {p90:.2f} mm, worst "
          f"{error.max():.2f} mm; residual reported {fragment.residual_mm:.2f} mm, plus plane uncertainty "
          f"{budget:.2f} mm")
    assert p90 <= budget
    reduced = reduce_labels(vol, found, accept_unvalidated=True)
    # Everything but the injured hip is untouched.
    for label in (seg.HIP_L, seg.SACRUM, seg.LUMBAR, seg.FEMUR_R):
        assert np.array_equal(reduced.array == label, vol.array == label)


def test_a_bilateral_injury_is_refused_a_transform_home(undisplaced):
    _, vol, confirmed, _ = undisplaced
    found = find_fragments(vol, confirmed, "both")
    assert found.refused and "DECISIONS 2.4" in found.refused and not found.fragments
    with pytest.raises(ValueError, match="no virtual reduction"):
        reduce_labels(vol, found)


def test_an_unconfirmed_reference_is_refused(undisplaced):
    _, vol, _, _ = undisplaced
    with pytest.raises(ReferenceNotConfirmed):
        find_fragments(vol, mirror.fit_reference(vol), "right")


def test_the_articular_surface_is_where_the_hip_meets_the_femoral_head(undisplaced):
    phantom, vol, _, _ = undisplaced
    joint = articular_surface(vol, "right")
    assert joint is not None and joint.any()
    assert np.all(vol.array[joint] == seg.HIP_R)
    head = vol.array == seg.FEMUR_R
    near = ndi.distance_transform_edt(~head, sampling=vol.spacing[::-1])
    assert near[joint].max() <= 6.0
    # With no femur label and no CT there is nothing to find it from.
    no_femur = vol.array.copy()
    no_femur[np.isin(no_femur, (seg.FEMUR_R, seg.FEMUR_L))] = 0
    assert articular_surface(Volume(no_femur, vol.spacing, vol.origin), "right") is None


def test_the_unvalidated_ct_femur_is_used_only_when_asked_for(undisplaced):
    """A CT whose femur shows only as unlabelled bone: the HU heuristic
    would find it, but it has not been checked against a real femur
    segmentation, so it is ignored unless the caller opts in."""
    phantom, vol, _, _ = undisplaced
    ct = Volume(np.where(vol.array > 0, 1000.0, -100.0).astype(np.float32), vol.spacing, vol.origin)
    no_femur = vol.array.copy()
    no_femur[np.isin(no_femur, (seg.FEMUR_R, seg.FEMUR_L))] = 0
    labels = Volume(no_femur, vol.spacing, vol.origin)
    assert articular_surface(labels, "right", ct) is None
    found = articular_surface(labels, "right", ct, allow_unvalidated_ct_femur=True)
    assert found is not None and found.any()
    assert np.all(no_femur[found] == seg.HIP_R)


# --------------------------------------------------------------------------
# Added to make the deciding tests catch what they name. Each says which
# wrong implementation it would fail on.

MOVE_10MM = dict(translate_mm=(4.0, 3.0, 8.5), rotate_deg=8.0, rotate_axis=(1.0, 0.3, 0.2))
TRUE_NORMAL = np.array([np.cos(np.radians(YAW_DEG)), np.sin(np.radians(YAW_DEG)), 0.0])


def _with_plane(confirmed, normal, offset_mm):
    """The same confirmation, mirrored across a plane of our choosing."""
    plane = dataclasses.replace(confirmed.plane, normal=np.asarray(normal, dtype=float), offset_mm=float(offset_mm))
    return dataclasses.replace(confirmed, plane=plane)


def _landing_error(transform, truth, points):
    """Where the transform sends each point against where it truly belongs,
    before any rounding onto the grid (reduce_labels rounds once, and that
    is tested on its own below)."""
    return np.linalg.norm(transform_points(transform, points) - transform_points(truth, points), axis=1)


def _surface_travel(vol, fragment):
    """The furthest any surface voxel of the fragment's own mask moves home."""
    surface = fragment.mask & ~ndi.binary_erosion(fragment.mask)
    return float(travel_mm(fragment.to_reference, vol.mask_voxel_centers_world(surface)).max())


@pytest.fixture(scope="module")
def true_plane_10mm(moved_10mm):
    """The 10 mm / 8 degree case measured against the exact mirror plane
    (the patient's midline, turned 6 degrees), so the plane adds no error."""
    phantom, vol, confirmed, _ = moved_10mm
    exact = _with_plane(confirmed, TRUE_NORMAL, 0.0)
    return phantom, vol, exact, find_fragments(vol, exact, "right", articular=articular_surface(vol, "right"))


@pytest.fixture(scope="module")
def moved_left():
    phantom = fractured_pelvis(yaw_deg=YAW_DEG, side="left", **MOVE_10MM)
    vol = Volume(phantom.labels, phantom.spacing, phantom.origin)
    ref = mirror.fit_reference(vol)
    confirmed = mirror.confirm(ref, sacrum_fractured=ref.sacrum_fractured_preselected)
    return phantom, vol, confirmed, find_fragments(vol, confirmed, "left", articular=articular_surface(vol, "left"))


def test_null_the_one_body_is_the_whole_hip_and_it_barely_moves(undisplaced):
    """Catches a finder that reports one body but leaves part of the hip out
    of it (a fragment silently dropped instead of promoted), and one whose
    single body is itself displaced. Tolerance as for recovery: two voxels
    and two degrees; what it reads is the plane's own error."""
    _, vol, _, found = undisplaced
    main = found.fragments[0]
    hip = vol.array == seg.HIP_R
    voxel_cm3 = float(np.prod(vol.spacing)) / 1000.0
    left_out = float((hip & ~main.mask).sum()) * voxel_cm3
    print(f"\nundisplaced main body: {main.volume_cm3:.1f} cm3, {left_out:.3f} cm3 of the hip outside it, "
          f"travel {main.travel_mm:.2f} mm, rotation {rotation_deg(main.to_reference):.2f} degrees")
    assert not (main.mask & ~hip).any()
    assert left_out < MIN_FRAGMENT_ACETABULAR_CM3  # only dust, under the smallest fragment there can be
    assert main.travel_mm <= 2.0 * max(vol.spacing)
    assert rotation_deg(main.to_reference) <= 2.0
    assert np.allclose(main.to_parent, np.eye(4)) and main.parent is None


def test_null_an_undisplaced_left_hemipelvis_is_one_body(undisplaced):
    """The left side takes the other branch of every side lookup."""
    _, vol, confirmed, _ = undisplaced
    found = find_fragments(vol, confirmed, "left", articular=articular_surface(vol, "left"))
    print(f"\nundisplaced, left: {found.sentence()}")
    assert found.side == "left" and len(found.fragments) == 1
    assert not (found.fragments[0].mask & (vol.array != seg.HIP_L)).any()


@pytest.mark.parametrize("case", ["undisplaced", "moved_10mm", "moved_5mm"])
def test_the_headline_travel_is_measured_over_the_fragment_it_reports(case, request):
    """DECISIONS 1.2's number is the furthest any point *of that fragment*
    travels home. Points the finder counted for a body but then gave to its
    neighbour (DECISIONS 3.2's small pieces) are not that fragment's, so the
    reported travel cannot exceed the travel of the fragment's own surface."""
    _, vol, _, found = request.getfixturevalue(case)
    for fragment in found.fragments:
        own = _surface_travel(vol, fragment)
        print(f"\n{case} body {fragment.index}: reported travel {fragment.travel_mm:.2f} mm, its own surface "
              f"travels at most {own:.2f} mm")
        assert fragment.travel_mm <= own + 1e-6


def test_below_the_floor_the_number_is_the_transforms_own_and_flagged(undisplaced):
    """DECISIONS 1.4: "1.1 mm, below this case's floor of 2.2 mm". The value
    is what the transform actually moves the body, not a stand-in (zero, or
    the floor), and the sentence says both numbers. The flag is exactly
    "under the floor", on every body."""
    vol, confirmed = _own_mirror(undisplaced)
    found = find_fragments(vol, confirmed, "right")
    main = found.fragments[0]
    assert main.below_floor
    assert main.travel_mm == pytest.approx(_surface_travel(vol, main), abs=0.05)
    assert main.travel_mm != pytest.approx(found.residual_floor_mm, abs=0.05)
    assert (f"travels {main.travel_mm:.1f} mm home (below this case's floor of "
            f"{found.residual_floor_mm:.1f} mm") in found.sentence()
    _, _, _, over = undisplaced
    for fs in (found, over):
        for f in fs.fragments:
            assert f.below_floor is (f.travel_mm < fs.residual_floor_mm)


def test_virtual_reduction_lands_within_its_residual_plus_the_planes_own_error(moved_10mm):
    """The plan's test 6, as the surgeon ruled on 2026-09-27. As first
    written it asserted that to_reference lands the fragment within its
    residual; it failed (p90 1.30 against 1.13 mm), and the residual is fit
    quality, not an error bound, so that claim is not made. Two true claims
    replace it:

    - with the exact plane the residual alone bounds every voxel
      (test_with_the_exact_plane_the_residual_alone_bounds_the_reduction);
    - with the fitted plane, here: the reduction adds nothing beyond the
      residual and the plane's own error at that point, measured against
      the phantom's true plane. The plane uncertainty is deliberately not
      used for it: on real cases it underestimates the plane's error.

    Pointwise, and measured before rounding onto the grid, so an exact
    transform reads zero."""
    phantom, vol, confirmed, found = moved_10mm
    fragment = _the_fragment(phantom, found)
    points = vol.mask_voxel_centers_world(fragment.mask & phantom.fragment)
    error = _landing_error(fragment.to_reference, phantom.to_reference, points)
    # How far the fitted plane's mirror moves the fragment's true home: the
    # two reflections compose to a rigid motion, zero for the exact plane.
    plane_motion = reflection_matrix(confirmed.plane.normal, confirmed.plane.offset_mm) @ reflection_matrix(TRUE_NORMAL, 0.0)
    home = transform_points(phantom.to_reference, points)
    plane_error = np.linalg.norm(transform_points(plane_motion, home) - home, axis=1)
    print(f"\nlanding error of the reduced fragment: p50 {np.median(error):.2f} mm, p90 "
          f"{np.percentile(error, 90):.2f} mm, worst {error.max():.2f} mm; residual {fragment.residual_mm:.2f} mm; "
          f"the fitted plane's own error there {plane_error.min():.2f}-{plane_error.max():.2f} mm; "
          f"plane uncertainty reported {fragment.plane_uncertainty_mm:.2f} mm (not a bound)")
    assert np.all(error <= fragment.residual_mm + plane_error)
    # The fitted plane is not the true one, so this is a real test of the
    # fitted-plane case and not the exact-plane test again.
    assert plane_error.max() > 0.0


def test_with_the_exact_plane_the_residual_alone_bounds_the_reduction(true_plane_10mm):
    """Take the plane's error away and what is left is the registration's:
    then the residual alone must bound where every voxel lands, and the
    undisplaced main body reads under its floor."""
    phantom, vol, _, found = true_plane_10mm
    fragment = _the_fragment(phantom, found)
    error = _landing_error(fragment.to_reference, phantom.to_reference,
                           vol.mask_voxel_centers_world(fragment.mask & phantom.fragment))
    main = found.fragments[0]
    print(f"\nexact plane: {found.sentence()}; landing error p90 {np.percentile(error, 90):.2f} mm, worst "
          f"{error.max():.2f} mm, residual {fragment.residual_mm:.2f} mm")
    assert error.max() <= fragment.residual_mm
    assert rotation_deg(fragment.to_reference @ invert(phantom.to_reference)) <= 1.0
    assert main.travel_mm < found.residual_floor_mm and main.below_floor


def test_to_parent_is_immune_to_the_mirror_plane_and_to_reference_carries_it(moved_10mm):
    """The plan's key structural point. Mirror across a plane deliberately
    2 degrees and 2 mm off the true one: to_parent must still recover the
    fragment's displacement off its parent, and to_reference must move by
    exactly what the wrong plane moves the mirrored side. A to_reference
    that were secretly relative, or a to_parent that were secretly
    absolute, fails here and nowhere else, since the phantom's main body
    does not move."""
    phantom, vol, confirmed, _ = moved_10mm
    turn = np.radians(2.0)
    about_z = np.array([[np.cos(turn), -np.sin(turn), 0.0], [np.sin(turn), np.cos(turn), 0.0], [0.0, 0.0, 1.0]])
    wrong = _with_plane(confirmed, about_z @ TRUE_NORMAL, 2.0)
    found = find_fragments(vol, wrong, "right", articular=articular_surface(vol, "right"))
    fragment = _the_fragment(phantom, found)
    exact = _with_plane(confirmed, TRUE_NORMAL, 0.0)
    shift = wrong.plane.matrix() @ exact.plane.matrix()  # what the wrong plane does to the mirrored side
    points = vol.mask_voxel_centers_world(phantom.fragment)
    relative = _errors(fragment.to_parent, phantom.to_reference, points)
    carried = _errors(fragment.to_reference, shift @ phantom.to_reference, points)
    naive = _errors(fragment.to_reference, phantom.to_reference, points)
    print(f"\nplane 2 degrees / 2 mm off: to_parent off by {relative[2]:.2f} mm, {relative[1]:.2f} degrees; "
          f"to_reference against the shifted truth {carried[2]:.2f} mm, against the true home {naive[2]:.2f} mm")
    for _, degrees, worst in (relative, carried):
        assert worst <= 2.0 * max(vol.spacing) and degrees <= 2.0
    assert naive[2] > 2.0 * max(vol.spacing)


def test_a_left_fragment_is_found_and_reduced_on_the_left(moved_left):
    """The whole left-side path: which hip is injured, which is mirrored,
    and which id the virtual reduction paints."""
    phantom, vol, _, found = moved_left
    fragment = _the_fragment(phantom, found)
    points = vol.mask_voxel_centers_world(phantom.fragment)
    home = _errors(fragment.to_reference, phantom.to_reference, points)
    relative = _errors(fragment.to_parent, phantom.to_reference, points)
    print(f"\nleft: to_reference off by {home[2]:.2f} mm, {home[1]:.2f} degrees; to_parent {relative[2]:.2f} mm, "
          f"{relative[1]:.2f} degrees")
    for _, degrees, worst in (home, relative):
        assert worst <= 2.0 * max(vol.spacing) and degrees <= 2.0
    assert np.all(vol.array[fragment.mask] == seg.HIP_L)
    reduced = reduce_labels(vol, found, accept_unvalidated=True)
    for label in (seg.HIP_R, seg.SACRUM, seg.LUMBAR, seg.FEMUR_L, seg.FEMUR_R):
        assert np.array_equal(reduced.array == label, vol.array == label)
    # The left hip now covers where the fragment was before it moved.
    back = (reduced.array == seg.HIP_L) & phantom.fragment_before
    assert back.sum() >= 0.9 * phantom.fragment_before.sum()


def test_the_transform_home_is_refused_until_the_caller_accepts_it_unvalidated(moved_10mm):
    """DECISIONS 2.3 and 7a.2. Nothing in a result bounds to_reference's
    error (the residual misses the plane's error; the plane uncertainty read
    0.0-32.4 mm on normal pelvises whose main body "travelled" 5.8-45.9 mm),
    so the call Corridor Finder makes refuses by default, with the reason
    and this case's numbers, and so does a hand-built FragmentSet. Fails if
    reduce_labels moves a hemipelvis on a result that says nothing."""
    _, vol, _, found = moved_10mm
    main = found.fragments[0]
    assert found.to_reference_unvalidated.startswith(TO_REFERENCE_NOT_VALIDATED)
    assert f"travels {main.travel_mm:.1f} mm home" in found.to_reference_unvalidated
    assert f"uncertainty of {found.plane_uncertainty_mm:.1f} mm" in found.to_reference_unvalidated
    assert "not validated" in found.sentence()
    with pytest.raises(ValueError, match="no virtual reduction: the transform home has no validated error bound"):
        reduce_labels(vol, found)
    hand_built = FragmentSet("right", "l5", "pre-selection", [_body(0, vol.array == seg.HIP_R, np.eye(4))], 0.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="no validated error bound"):
        reduce_labels(vol, hand_built)
    accepted = reduce_labels(vol, found, accept_unvalidated=True).array
    assert np.array_equal(accepted == seg.SACRUM, vol.array == seg.SACRUM)


def _body(index, mask, to_reference):
    return Fragment(index=index, parent=None if index == 0 else 0, mask=mask, volume_cm3=0.0,
                    to_reference=to_reference, to_parent=to_reference, residual_mm=0.0, travel_mm=0.0,
                    relative_travel_mm=0.0, plane_uncertainty_mm=0.0, below_floor=False, articular=False, n_points=0)


def test_reduce_labels_with_the_exact_transform_restores_the_pre_injury_hip():
    """reduce_labels on its own, with the phantom's exact transform home:
    every intact voxel is within one voxel of the reduced hip, and every
    reduced voxel within two voxels per axis of the intact hip (the shape
    is rounded onto the grid twice, once when the phantom moved it and once
    when reduce_labels moves it back: the worst voxel lies 3.4 mm out, two
    voxels on one axis). The fragment's displaced position is emptied and
    no other bone changes. Fails if it applies the inverse (the reduced
    fragment then lies up to 23 mm out), leaves the fragment where it was,
    or moves anything else."""
    phantom = fractured_pelvis(yaw_deg=YAW_DEG, **MOVE_10MM)
    vol = Volume(phantom.labels, phantom.spacing, phantom.origin)
    rest = (vol.array == seg.HIP_R) & ~phantom.fragment
    fragments = FragmentSet("right", "l5", "pre-selection",
                            [_body(0, rest, np.eye(4)), _body(1, phantom.fragment, phantom.to_reference)], 0.0, 0.0, 0.0)
    reduced = reduce_labels(vol, fragments, accept_unvalidated=True).array
    within_a_voxel, within_two = np.ones((3, 3, 3), dtype=bool), np.ones((5, 5, 5), dtype=bool)
    after, intact = reduced == seg.HIP_R, phantom.intact_labels == seg.HIP_R
    assert np.all(ndi.binary_dilation(intact, within_two)[after])
    assert np.all(ndi.binary_dilation(after, within_a_voxel)[intact])
    assert not after[phantom.fragment & ~ndi.binary_dilation(intact, within_two)].any()
    for label in (seg.HIP_L, seg.SACRUM, seg.LUMBAR, seg.FEMUR_L, seg.FEMUR_R):
        assert np.array_equal(reduced == label, vol.array == label)


@pytest.mark.parametrize("side", ["right", "left"])
def test_reduce_labels_never_paints_over_another_bone(side):
    """A wrong transform home that drives the whole hip 25 mm toward the
    midline, into the sacrum and the other hip: every other bone is kept
    voxel for voxel, and the moved hip fills only what was empty."""
    phantom = fractured_pelvis(spacing_mm=3.0)
    vol = Volume(phantom.labels, phantom.spacing, phantom.origin)
    hip_id = seg.HIP_R if side == "right" else seg.HIP_L
    hip = vol.array == hip_id
    medial = np.eye(4)
    medial[0, 3] = -25.0 if side == "right" else 25.0
    landing = np.rint(vol.world_to_zyx_indices(transform_points(medial, vol.mask_voxel_centers_world(hip)))).astype(int)
    struck = vol.array[tuple(landing)]
    assert np.isin(struck, (seg.SACRUM, seg.HIP_L if side == "right" else seg.HIP_R)).sum() > 100  # it does collide
    reduced = reduce_labels(vol, FragmentSet(side, "l5", "pre-selection", [_body(0, hip, medial)], 0.0, 0.0, 0.0),
                            accept_unvalidated=True).array
    for label in set(int(v) for v in np.unique(vol.array)) - {0, hip_id}:
        assert np.array_equal(reduced == label, vol.array == label), label
    x = vol.origin[0] + np.arange(vol.array.shape[2]) * vol.spacing[0]
    moved_by = x[np.nonzero(reduced == hip_id)[2]].mean() - x[np.nonzero(hip)[2]].mean()
    assert moved_by == pytest.approx(medial[0, 3], abs=5.0)


@pytest.mark.parametrize("case", ["undisplaced", "moved_5mm", "moved_10mm", "moved_20mm", "moved_30mm",
                                  "moved_23mm_turned"])
def test_nothing_is_left_unexplained_once_every_fragment_is_found(case, request):
    """With no fragment, or with the one fragment found, every hip voxel is
    carried home by its own body: no piece is reported as unexplained, and
    the sentence does not say there is one. Fails on a check that fires on
    every case, which would make its warning worthless."""
    _, _, _, found = request.getfixturevalue(case)
    print(f"\n{case}: {found.unexplained_points} surface points ({100 * found.unexplained_share:.1f}%) explained "
          f"by no body; {found.unexplained_cm3:.2f} cm3 in pieces of fragment size carried home by none")
    assert found.unexplained_cm3 == 0.0 and found.unexplained_pieces == 0 and not found.unexplained.any()
    assert "no body carries home" not in found.sentence()


def test_a_fragment_the_search_misses_is_reported_and_never_folded_into_one_body(monkeypatch):
    """The search as it was before it started from the unexplained bone:
    the 25 mm fragment is missed. It must not come back as a healthy "one
    body": the bone no body carries home is returned as a region that is the
    fragment, with its size in the warnings and the sentence, and the
    virtual reduction refuses, even with the plane's error accepted, rather
    than move the fragment with the main body and leave it 25 mm out."""
    monkeypatch.setattr(fragment_finder, "_shifted_starts", lambda *args, **kwargs: iter(()))
    phantom, vol, _, found = _case(translate_mm=(0.0, 0.0, 25.0))
    stray = found.unexplained
    inside = (stray & phantom.fragment).sum() / max(stray.sum(), 1)
    covers = (stray & phantom.fragment).sum() / phantom.fragment.sum()
    print(f"\nmissed at 25 mm: {found.sentence()}; the unexplained region is {inside:.2f} true fragment and "
          f"covers {covers:.2f} of it")
    assert len(found.fragments) == 1
    assert found.unexplained_pieces == 1 and inside >= 0.9 and covers >= 0.9
    assert found.unexplained_cm3 == pytest.approx(stray.sum() * np.prod(vol.spacing) / 1000.0)
    assert found.unexplained_points > 0 and found.unexplained_share > 0.0
    assert any(f"{found.unexplained_cm3:.1f} cm3 of the right hip" in w for w in found.warnings)
    assert "one body found" in found.sentence() and f"{found.unexplained_cm3:.1f} cm3" in found.sentence()
    with pytest.raises(ValueError, match="carried home by no body"):
        reduce_labels(vol, found, accept_unvalidated=True)
