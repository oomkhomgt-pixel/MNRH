"""The reduction fit by congruence (displacement-finder slice 1b, plan tests
1-6). All on the synthetic pelvis of phantoms.py at 1.5 mm voxels, where
the reduction that puts each piece back is known exactly (DECISIONS 6.2).

Every landing error is measured before rounding onto the grid, as each side
of a region relative to its other side, which is what a region's error
means (congruence's docstring), and each point's true reduction is taken
from the phantom, not from the units the fit built.

Most fits here are given the phantom's own normal joint widths as targets,
measured the way 7c.2 and 7c.7 measure them: its 6 mm symphysis reads
7.5 mm centre to centre, wider than 255 of the 258 normal pelvises the
4.93 mm target comes from, and its SI joints read 4.7-4.9 mm against the
4 mm cap. That measures the fit; what the targets of 7c do to this phantom
is printed and checked separately."""
import contextlib
import dataclasses
import json

import numpy as np
import pytest
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from corridor_engine import congruence as cg
from corridor_engine import fracture_surface as fsm
from corridor_engine import segmentation as seg
from corridor_engine import mirror, si_joint
from corridor_engine.fracture import fit_plane
from corridor_engine.fragments import Fragment, FragmentSet
from corridor_engine.landmarks import detect_landmarks
from corridor_engine.phantoms import (_rotation, bilateral_sacral_fractured_pelvis, fractured_pelvis,
                                      impacted_sacral_pelvis, pelvis_ct, sacral_fractured_pelvis)
from corridor_engine.reduction import REGION_RADIUS_MM, Reduction, apply_moves, reduction_warnings, warning_text
from corridor_engine.register import invert, rotation_deg, transform_points
from corridor_engine.volume import Volume

VOXEL_MM = 1.5
# A deliberately wrong mirror start (plan test 1): 5 mm and 3 degrees.
WRONG_SHIFT_MM = (3.0, 4.0, 0.0)
WRONG_TURN_DEG = 3.0
SACRAL_MOVES = {"right": (0.0, 1.5, 0.0), "left": (0.0, -1.0, 1.0)}  # each unit's slide, with a 3 degree hinge
# How far an undisplaced hip may be moved (plan test 3), and how far a fit
# started exactly may walk away: the fracture bound these tests were written
# against, kept when the wider family raised the phantom bound to 6.5 mm so
# neither check loosened with it. The review measured walks of 5.61 and
# 9.41 mm from the exact start.
STAY_MM = 3.5
# What plan tests 1 and 2 held a hip's pose error to before the bound was
# measured per displacement: max(PHANTOM_BOUND_MM.values()), 6.5 mm. The
# replacement holds it to the table's bound at the fit's displacement as
# well, which at 5.18 mm is 6.72 mm, looser; plan test 7 asks for a
# replacement as strict, so both hold.
SLICE_1B_BOUND_MM = 6.5


def _vol(labels, phantom):
    return Volume(labels, phantom.spacing, phantom.origin)


def _body(index, parent, mask, home):
    return Fragment(index, parent, mask, float(mask.sum()) * VOXEL_MM ** 3 / 1000.0, home,
                    home if parent is not None else np.eye(4), 0.5, 0.0, 0.0, 0.5, False, False, int(mask.sum()))


def _fragment_set(side, bodies):
    """slice 1's result, built from the phantom's own pieces and starts, so
    the fit is tested apart from how well slice 1 finds them."""
    return FragmentSet(side, "l5", "pre-selection", bodies, 0.5, 1.5, 0.5)


def _wrong(points):
    """A mirror start 5 mm and 3 degrees off, about the unit's centroid."""
    centre = points.mean(axis=0)
    out = np.eye(4)
    out[:3, :3] = _rotation((0.3, 1.0, 0.2), WRONG_TURN_DEG)
    out[:3, 3] = centre - out[:3, :3] @ centre + np.asarray(WRONG_SHIFT_MM)
    return out


def _truth(vol, moving):
    """Each scanned point's true reduction, from the phantom's own moving
    masks [(mask, transform)]; everything else stays."""
    def of(points):
        idx = tuple(np.rint(vol.world_to_zyx_indices(points)).astype(int))
        out = np.repeat(np.eye(4)[None], len(points), axis=0)
        for mask, transform in moving:
            out[mask[idx]] = transform
        return out
    return of


def _landing(fit, truth_of):
    """Per region, the worst distance between where the fit puts a point of
    one side and where it belongs, once the other side is put where it
    belongs."""
    fitted = [u.transform for u in fit.units]
    out = {}
    for name, region in fit.regions.items():
        worst = 0.0
        for a, b in ((0, 1), (1, 0)):
            pa, pb = region.sides[a], region.sides[b]
            if not len(pa) or not len(pb):
                continue
            fa = np.stack([fitted[k] if k >= 0 else np.eye(4) for k in region.side_units[a]])
            fb = np.stack([fitted[k] if k >= 0 else np.eye(4) for k in region.side_units[b]])
            ta, tb = truth_of(pa), truth_of(pb)
            # The other side's own error, from its commonest pairing of fitted and true transform.
            keys = np.round(np.concatenate([fb[:, :3].reshape(len(fb), -1), tb[:, :3].reshape(len(tb), -1)], axis=1), 6)
            _, first, counts = np.unique(keys, axis=0, return_index=True, return_counts=True)
            k = first[np.argmax(counts)]
            error = tb[k] @ invert(fb[k])
            got = transform_points(error, np.einsum("nij,nj->ni", fa[:, :3, :3], pa) + fa[:, :3, 3])
            want = np.einsum("nij,nj->ni", ta[:, :3, :3], pa) + ta[:, :3, 3]
            worst = max(worst, float(np.linalg.norm(got - want, axis=1).max()))
        out[name] = worst
    return out


def _pose_error(fitted, truth, points):
    """Worst distance over the points, and the rotation, between two poses."""
    return (float(np.linalg.norm(transform_points(fitted, points) - transform_points(truth, points), axis=1).max()),
            rotation_deg(fitted @ invert(truth)))


def _report(label, fit, landing):
    print(f"{label}:")
    for name, region in fit.regions.items():
        print(f"  {region.sentence()}; lands {landing[name]:.2f} mm")


def _check_lands_within(fit, landing):
    for name, region in fit.regions.items():
        assert landing[name] <= region.residual_mm, (
            f"{name} lands {landing[name]:.2f} mm off, but reports {region.residual_mm:.2f} mm")


# --------------------------------------------------------------------------
# Fixtures. The phantom's own targets, and each phantom once per module.


@pytest.fixture(scope="module")
def own_targets():
    phantom = fractured_pelvis()
    vol = _vol(phantom.intact_labels, phantom)
    widths = si_joint.measure_joint_widths(vol, detect_landmarks(vol))
    symphysis = cg.symphysis_gap(vol)[0]
    # 7c.2 takes the intact side's width; the phantom is symmetric, so each
    # side's target is the other side's measurement, uncapped.
    return {"si_target_mm": {"right": widths["left"].measured_mm, "left": widths["right"].measured_mm},
            "symphysis_target_mm": symphysis}


@pytest.fixture(scope="module")
def sacral():
    """A unilateral sacral fracture on each side, hinged 3 degrees open and
    slid, as found: surfaces and split."""
    cases = {}
    for side, move in SACRAL_MOVES.items():
        phantom = sacral_fractured_pelvis(side=side, hinge_deg=3.0, translate_mm=move)
        vol = _vol(phantom.labels, phantom)
        found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
        cases[side] = (phantom, vol, found, fsm.split_sacrum(vol, found))
    return cases


def _sacral_fit_args(sacral, side, start):
    """fit_reduction's positional arguments for a unilateral sacral case."""
    phantom, vol, found, splits = sacral[side]
    truth = np.linalg.inv(phantom.moved_by)
    hip = phantom.labels == (seg.HIP_R if side == "right" else seg.HIP_L)
    begin = truth if start == "exact" else _wrong(vol.mask_voxel_centers_world(hip)) @ truth
    return (vol, side, found, _fragment_set(side, [_body(0, None, hip, begin)]), splits), truth, begin


def _sacral_fit(sacral, own_targets, side, start, targets="own"):
    phantom, vol, found, splits = sacral[side]
    args, truth, begin = _sacral_fit_args(sacral, side, start)
    fit = cg.fit_reduction(*args, **(own_targets if targets == "own" else {}))
    hip = phantom.labels == (seg.HIP_R if side == "right" else seg.HIP_L)
    femur = phantom.labels == (seg.FEMUR_R if side == "right" else seg.FEMUR_L)
    truth_of = _truth(vol, [(hip | phantom.lateral_fragment | femur, truth)])
    return phantom, vol, fit, truth, begin, truth_of


@pytest.fixture(scope="module", params=[("right", "exact"), ("right", "wrong"), ("left", "wrong")],
                ids=lambda p: f"{p[0]}-{p[1]}")
def unilateral(request, sacral, own_targets):
    side, start = request.param
    return (side, start) + _sacral_fit(sacral, own_targets, side, start)


@pytest.fixture(scope="module")
def bilateral(own_targets):
    phantom = bilateral_sacral_fractured_pelvis(hinge_deg=(3.0, 2.0), translate_mm=(SACRAL_MOVES["right"],
                                                                                    SACRAL_MOVES["left"]))
    vol = _vol(phantom.labels, phantom)
    found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
    splits = fsm.split_sacrum(vol, found)
    fit = cg.fit_reduction(vol, "both", found, None, splits, **own_targets)
    moving = []
    for side, hip_id, femur_id in (("right", seg.HIP_R, seg.FEMUR_R), ("left", seg.HIP_L, seg.FEMUR_L)):
        mask = (phantom.labels == hip_id) | phantom.lateral_fragments[side] | (phantom.labels == femur_id)
        moving.append((mask, np.linalg.inv(phantom.moved_by[side])))
    return phantom, vol, fit, _truth(vol, moving)


# --------------------------------------------------------------------------
# Plan test 1: unilateral recovery, from the exact plane and a wrong mirror.


def test_unilateral_recovery(unilateral):
    side, start, phantom, vol, fit, truth, begin, truth_of = unilateral
    unit = fit.units[0]
    surface = vol.mask_voxel_centers_world(unit.mask & ~ndi.binary_erosion(unit.mask))
    before, after = _pose_error(begin, truth, surface), _pose_error(unit.transform, truth, surface)
    landing = _landing(fit, truth_of)
    _report(f"unilateral {side} sacral fracture from the {start} start: start off {before[0]:.2f} mm, "
            f"{before[1]:.2f} deg; fitted off {after[0]:.2f} mm, {after[1]:.2f} deg (worst surface point)", fit, landing)
    assert unit.name == f"hip_{side}" and any("lateral sacral fragment" in p for p in unit.parts)
    assert after[0] <= min(SLICE_1B_BOUND_MM, _largest_bound(fit))
    if start == "wrong":
        assert after[0] < before[0], "congruence did not correct the mirror at all"
    _check_lands_within(fit, landing)
    sacral_region = [r for r in fit.regions.values() if r.name.startswith("fracture_sacrum")]
    assert sacral_region and all(np.isfinite(r.residual_mm) for r in sacral_region)


def test_departing_from_the_mirror_is_flagged_only_past_its_floor(sacral, own_targets):
    _, _, exact, *_ = _sacral_fit(sacral, own_targets, "right", "exact")
    _, _, wrong, *_ = _sacral_fit(sacral, own_targets, "right", "wrong")
    assert not any("departs from the mirror start" in n for n in exact.notes)
    flags = [n for n in wrong.notes if "departs from the mirror start" in n]
    print(flags)
    assert flags and all("for the surgeon's review" in f for f in flags)
    unit = wrong.units[0]
    assert max(unit.departure_mm.values()) > cg.MIRROR_FLOOR_MM["si"]


def _departure_flagged(fit, unit, region):
    return any(n.startswith(f"{unit}: the congruence pose departs from the mirror start") and f" at {region}," in n
               for n in fit.notes)


def test_the_departure_flag_fires_exactly_past_each_regions_floor(sacral, own_targets, monkeypatch):
    """7c.4, at the boundary: a unit is flagged at a region exactly when it
    departs there by more than that region's floor. Each region is checked
    against its own kind's floor, and then the floor is moved to just above
    and just below the measured departure (the fit is deterministic)."""
    _, _, fit, *_ = _sacral_fit(sacral, own_targets, "right", "wrong")
    kinds = {name: r.kind for name, r in fit.regions.items()}
    for unit in fit.units:
        assert unit.departure_mm, f"{unit.name}: no departure measured on a unilateral injury"
        for region, moved in unit.departure_mm.items():
            past = moved > cg.MIRROR_FLOOR_MM[kinds[region]]
            assert _departure_flagged(fit, unit.name, region) == past, (unit.name, region, moved)
    # At a fracture the departure is measured over its faces' points on the
    # unit, from the mirror start (not from where the bone lies).
    unit = fit.units[0]
    for name, region in fit.regions.items():
        if region.kind != "fracture" or name not in unit.departure_mm:
            continue
        pts = np.vstack([side[units == 0] for side, units in zip(region.sides, region.side_units)])
        want = float(np.max(np.linalg.norm(transform_points(unit.transform, pts)
                                           - transform_points(unit.start, pts), axis=1)))
        assert unit.departure_mm[name] == pytest.approx(want, abs=1e-6), name
    region = "si_right"
    moved = unit.departure_mm[region]
    args, _, _ = _sacral_fit_args(sacral, "right", "wrong")
    for floor, flagged in ((moved + 0.05, False), (moved - 0.05, True)):
        monkeypatch.setitem(cg.MIRROR_FLOOR_MM, "si", floor)
        again = cg.fit_reduction(*args, **own_targets)
        assert again.units[0].departure_mm[region] == pytest.approx(moved, abs=1e-9)
        assert _departure_flagged(again, "hip_right", region) == flagged, f"floor {floor:.2f}, moved {moved:.2f}"


@pytest.mark.parametrize("side", ["right", "left"])
def test_a_joint_departure_is_measured_from_both_of_its_sides(sacral, own_targets, side):
    """The symphysis is paired from the right hip, so on a left injury the
    moving hip is only ever the side paired to; its departure there is
    measured all the same, over its own paired points, and flagged exactly
    past the floor."""
    _, _, fit, *_ = _sacral_fit(sacral, own_targets, side, "wrong")
    unit = fit.units[0]
    assert unit.name == f"hip_{side}"
    assert "symphysis" in unit.departure_mm and f"si_{side}" in unit.departure_mm, unit.departure_mm
    region = fit.regions["symphysis"]
    on_unit = np.vstack([pts[units == 0] for pts, units in zip(region.sides, region.side_units)])
    assert len(on_unit)
    want = float(np.max(np.linalg.norm(transform_points(unit.transform, on_unit)
                                       - transform_points(unit.start, on_unit), axis=1)))
    print(f"{side}: departs {unit.departure_mm['symphysis']:.2f} mm at the symphysis")
    assert unit.departure_mm["symphysis"] == pytest.approx(want, abs=1e-6)
    past = unit.departure_mm["symphysis"] > cg.MIRROR_FLOOR_MM["symphysis"]
    assert _departure_flagged(fit, unit.name, "symphysis") == past


# --------------------------------------------------------------------------
# Plan test 2: bilateral recovery, with no mirror.


def test_bilateral_recovery(bilateral):
    phantom, vol, fit, truth_of = bilateral
    assert {u.name for u in fit.units} == {"hip_right", "hip_left"}
    assert all(np.allclose(u.start, np.eye(4)) for u in fit.units), "a bilateral injury starts where it lies"
    landing = _landing(fit, truth_of)
    lines = []
    for unit in fit.units:
        truth = np.linalg.inv(phantom.moved_by[unit.side])
        surface = vol.mask_voxel_centers_world(unit.mask & ~ndi.binary_erosion(unit.mask))
        scanned = _pose_error(np.eye(4), truth, surface)
        fitted = _pose_error(unit.transform, truth, surface)
        lines.append(f"{unit.name} scanned {scanned[0]:.2f} mm / {scanned[1]:.2f} deg off, fitted {fitted[0]:.2f} mm / "
                     f"{fitted[1]:.2f} deg off")
        assert fitted[0] < scanned[0]
        assert fitted[0] <= min(SLICE_1B_BOUND_MM, _largest_bound(fit))
    _report("bilateral sacral fractures: " + "; ".join(lines), fit, landing)
    assert any("both sides injured" in n for n in fit.notes)
    _check_lands_within(fit, landing)
    assert sum(np.isfinite(r.residual_mm) for r in fit.regions.values() if r.kind == "fracture") >= 1


def test_a_bilateral_fit_has_no_mirror_to_depart_from_and_says_both_splits_are_unconfirmed(bilateral):
    phantom, vol, fit, truth_of = bilateral
    assert not any("departs from the mirror start" in n for n in fit.notes)
    assert all(not u.departure_mm for u in fit.units)
    reduction = fit.reduction()
    assert reduction.accepted_by is None and reduction.notes[0] == cg.NOT_ACCEPTED
    for side in ("right", "left"):
        assert f"{side} sacral split: {fsm.SPLIT_UNCONFIRMED}" in reduction.notes, side
        assert any(f"{side} lateral sacral fragment" in p for u in fit.units if u.side == side for p in u.parts)


def test_confirming_one_split_leaves_the_other_unconfirmed_and_the_case_unaccepted(own_targets):
    """Confirming the split (7c.5) is not accepting the reduction (7c.8),
    and confirming one side says nothing about the other."""
    phantom = bilateral_sacral_fractured_pelvis(hinge_deg=(3.0, 2.0), translate_mm=(SACRAL_MOVES["right"],
                                                                                    SACRAL_MOVES["left"]))
    vol = _vol(phantom.labels, phantom)
    found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
    splits = fsm.split_sacrum(vol, found)
    assert all(not s.refused and not s.confirmed and fsm.SPLIT_UNCONFIRMED in s.notes for s in splits.values())
    splits["right"] = fsm.confirm_split(splits["right"], "surgeon, review sheet 2026-10-03")
    reduction = cg.fit_reduction(vol, "both", found, None, splits, **own_targets).reduction()
    assert reduction.accepted_by is None and reduction.record()["accepted_by"] is None
    assert reduction.notes[0] == cg.NOT_ACCEPTED
    assert f"left sacral split: {fsm.SPLIT_UNCONFIRMED}" in reduction.notes
    assert f"right sacral split: {fsm.SPLIT_UNCONFIRMED}" not in reduction.notes
    assert "right sacral split confirmed by surgeon, review sheet 2026-10-03" in reduction.notes


# --------------------------------------------------------------------------
# Plan test 3: null.


@pytest.fixture(scope="module")
def undisplaced():
    phantom = fractured_pelvis()
    vol = _vol(phantom.labels, phantom)
    hip = phantom.labels == seg.HIP_R
    found = fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,))
    return phantom, vol, hip, found


def test_null_an_undisplaced_pelvis_is_not_moved(undisplaced, own_targets):
    phantom, vol, hip, found = undisplaced
    fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, np.eye(4))]), {},
                           **own_targets)
    unit = fit.units[0]
    moved = _pose_error(unit.transform, np.eye(4), vol.mask_voxel_centers_world(hip))
    print(f"undisplaced, its own targets: moved {moved[0]:.2f} mm, {moved[1]:.2f} deg; {fit.sentence()}")
    assert moved[0] <= STAY_MM
    # The phantom's SI joint and symphysis are flat, so with no fracture to
    # pin it the hip could slide along them: both say so, never a number.
    for name in ("si_right", "symphysis"):
        assert np.isinf(fit.regions[name].residual_mm), fit.regions[name].sentence()
        assert "no surface in the fit resists" in fit.regions[name].unconstrained


def test_a_unit_nothing_pins_is_a_region_over_all_of_its_bone(undisplaced, own_targets):
    """The hip held only by its flat SI joint and symphysis (CLINIC_0023's
    case): along the motion they leave free it stays at its start, which no
    surface checked. The joints' regions warn only within 10 mm of the
    joints; the whole hip is a region of its own, inf, so a screw in the
    iliac wing or above the acetabulum, far from both joints, is warned
    too."""
    phantom, vol, hip, found = undisplaced
    fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, np.eye(4))]), {},
                           **own_targets)
    region = fit.regions["unit_hip_right_unpinned"]
    print(region.sentence())
    assert region.kind == "unit" and region.units == ("hip_right",)
    assert np.isinf(region.residual_mm) and "not pinned down as a whole" in region.unconstrained
    assert any(n.startswith("hip_right is not pinned down as a whole") and "unit_hip_right_unpinned" in n
               for n in fit.notes)
    # Every voxel of the unit, where the fit puts it, lies within half the
    # warning radius of the region.
    unit = fit.units[0]
    bone = transform_points(unit.transform, vol.mask_voxel_centers_world(unit.mask))
    assert cKDTree(region.xyz).query(bone)[0].max() <= REGION_RADIUS_MM / 2.0
    # Bone further than the warning radius from both joints' regions: no
    # warning from them, but one from the unit.
    joints = np.vstack([np.asarray(fit.regions[k].xyz).reshape(-1, 3) for k in ("si_right", "symphysis")])
    far = bone[cKDTree(joints).query(bone)[0] > REGION_RADIUS_MM + 5.0]
    assert len(far) > 1000, "the case the region is for: hip bone far from both joints"
    screw = far[np.linspace(0, len(far) - 1, 20).astype(int)]
    regions = {w["region"] for w in reduction_warnings(screw, np.full(len(screw), 50.0), fit.reduction())}
    assert regions == {"unit_hip_right_unpinned"}, regions
    _check_residual_contract(fit)


def test_null_with_the_targets_of_7c(undisplaced):
    """7c.2 caps the SI target at 4 mm and 7c.7 closes the symphysis to
    4.93 mm; on this phantom (4.7-4.9 and 7.5 mm) that moves an undisplaced
    hip, in the directions the joints pin, and it says nothing it cannot."""
    phantom, vol, hip, found = undisplaced
    fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, np.eye(4))]), {})
    unit = fit.units[0]
    moved = _pose_error(unit.transform, np.eye(4), vol.mask_voxel_centers_world(hip))
    print(f"undisplaced, the targets of 7c: moved {moved[0]:.2f} mm, {moved[1]:.2f} deg; {fit.sentence()}")
    assert any("4.93 mm" in n or "closed to 4.93" in n for n in fit.notes)
    assert any("capped at 4.0 mm" in n for n in fit.notes)
    landing = _landing(fit, _truth(vol, []))
    _check_lands_within(fit, landing)


# --------------------------------------------------------------------------
# Plan test 4: comminution.


def _comminuted(kind):
    """The right sacral fracture with bone removed near its lateral face:
    the cancellous bone behind the face, its rim kept ("cancellous"), or the
    posterior half of the face, rim and all ("rim")."""
    phantom = sacral_fractured_pelvis(side="right", hinge_deg=3.0, translate_mm=SACRAL_MOVES["right"])
    labels = phantom.labels.copy()
    vol = _vol(labels, phantom)
    truth = np.linalg.inv(phantom.moved_by)
    fragment = phantom.lateral_fragment
    home = transform_points(truth, vol.mask_voxel_centers_world(fragment))
    depth = ndi.distance_transform_edt(labels > 0, sampling=phantom.spacing[::-1])[fragment]
    near_face = home[:, 0] < phantom.cut_point[0] + 6.0
    crushed = near_face & (depth > fsm.RIM_MM + VOXEL_MM) if kind == "cancellous" else near_face & (home[:, 1] < -42.0)
    labels[tuple(np.argwhere(fragment)[crushed].T)] = 0
    return phantom, vol, truth, float(crushed.sum()) * VOXEL_MM ** 3 / 1000.0


@pytest.mark.parametrize("kind", ["cancellous", "rim"])
def test_comminution_is_recovered_from_the_rims_or_said_unconstrained(kind, own_targets):
    phantom, vol, truth, removed = _comminuted(kind)
    found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
    splits = fsm.split_sacrum(vol, found)
    hip = vol.array == seg.HIP_R
    begin = _wrong(vol.mask_voxel_centers_world(hip)) @ truth
    fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, begin)]), splits,
                           **own_targets)
    moving = hip | (phantom.lateral_fragment & (vol.array > 0)) | (vol.array == seg.FEMUR_R)
    landing = _landing(fit, _truth(vol, [(moving, truth)]))
    _report(f"{removed:.1f} cm3 crushed ({kind}); {splits['right'].sentence()[:90]}", fit, landing)
    # Never a small wrong number: each region lands within what it reports,
    # or reports inf with the reason.
    _check_lands_within(fit, landing)
    for region in fit.regions.values():
        assert np.isfinite(region.residual_mm) or region.unconstrained
    # Never a missing key either: the crushed fracture is still a region.
    assert any(name.startswith("fracture_sacrum") for name in fit.regions), list(fit.regions)
    _check_residual_contract(fit)


# --------------------------------------------------------------------------
# Plan test 5: unconstrained.


@pytest.fixture(scope="module")
def iliac():
    """fractured_pelvis's iliac wing moved 5 mm, with slice 1's two bodies
    taken from the phantom and started from the exact mirror."""
    phantom = fractured_pelvis(translate_mm=(2.0, 1.5, 4.3))
    vol = _vol(phantom.labels, phantom)
    main = (phantom.labels == seg.HIP_R) & ~phantom.fragment
    bodies = _fragment_set("right", [_body(0, None, main, np.eye(4)), _body(1, 0, phantom.fragment,
                                                                            phantom.to_reference)])
    return phantom, vol, bodies, fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,), fragment_sets=[bodies])


def _with_rim(found, keep):
    """The same surfaces, each face keeping only its first ``keep`` rim points."""
    surfaces = []
    for s in found.surfaces:
        faces = []
        for f in s.faces:
            rim = np.zeros(len(f.rim), dtype=bool)
            rim[np.flatnonzero(f.rim)[:keep]] = True
            faces.append(fsm.Face(f.side, f.label, f.points, f.normals, f.voxels, rim))
        surfaces.append(fsm.FractureSurface(s.id, s.label, s.route, tuple(faces), s.width_mm, s.area_mm2,
                                            s.mark_distance_mm, list(s.flags), s.gap_voxels))
    return fsm.FractureSurfaces(surfaces, found.rejected, found.small_patches, found.candidate_points,
                                found.cortex_hu, found.twin_checked, found.cortex_checked, found.marks_given,
                                list(found.notes))


def test_too_little_rim_is_unconstrained_and_a_reduction_accepts_it(iliac, own_targets):
    phantom, vol, bodies, found = iliac
    region = "fracture_hip_right_fragment_1"
    full = cg.fit_reduction(vol, "right", found, bodies, {}, **own_targets)
    assert np.isfinite(full.regions[region].residual_mm), full.regions[region].sentence()
    starved = cg.fit_reduction(vol, "right", _with_rim(found, 5), bodies, {}, **own_targets)
    print(starved.regions[region].sentence())
    assert np.isinf(starved.regions[region].residual_mm)
    assert "too little rim" in starved.regions[region].unconstrained
    reduction = starved.reduction()
    assert isinstance(reduction, Reduction) and np.isinf(reduction.residual_mm[region])
    assert len(np.asarray(reduction.region_xyz[region]).reshape(-1, 3)) > 0, "a region always says where it is"
    record = reduction.record()
    assert record["residual_mm"][region] is None and region in record["unconstrained"]
    assert any(region in n and "unconstrained" in n for n in reduction.notes)
    # Corridor Finder warns at it whatever the screw's room.
    near = np.asarray(reduction.region_xyz[region]).reshape(-1, 3)[:3]
    warnings = reduction_warnings(near, np.full(len(near), 50.0), reduction)
    assert any(w["region"] == region and "not pinned down" in warning_text(w) for w in warnings)


def _with_rim_disagreeing(found, mm):
    """The same surfaces, with face A's rim points pushed alternately +mm and
    -mm along their own normals: interleaved, so no rigid pose can bring
    both halves onto face B at once. Voxels (which unit a point lies on)
    are unchanged."""
    surfaces = []
    for s in found.surfaces:
        a, b = s.faces
        points = a.points.copy()
        rim = np.flatnonzero(a.rim)
        sign = np.where(np.arange(len(rim)) % 2 == 0, 1.0, -1.0)
        points[rim] += (sign * mm)[:, None] * a.normals[rim]
        faces = (fsm.Face(a.side, a.label, points, a.normals, a.voxels, a.rim), b)
        surfaces.append(fsm.FractureSurface(s.id, s.label, s.route, faces, s.width_mm, s.area_mm2,
                                            s.mark_distance_mm, list(s.flags), s.gap_voxels))
    return fsm.FractureSurfaces(surfaces, found.rejected, found.small_patches, found.candidate_points,
                                found.cortex_hu, found.twin_checked, found.cortex_checked, found.marks_given,
                                list(found.notes))


def test_rims_that_disagree_are_unconstrained_never_a_small_number(iliac, own_targets):
    """7c.6: a region whose rims do not agree reports inf with the reason.
    With the disagreement check gone it would report its mismatch (about
    5 mm here) as if it were a bound."""
    phantom, vol, bodies, found = iliac
    region = "fracture_hip_right_fragment_1"
    fit = cg.fit_reduction(vol, "right", _with_rim_disagreeing(found, 5.0), bodies, {}, **own_targets)
    print(fit.regions[region].sentence())
    assert fit.regions[region].pairs >= cg.MIN_PAIRS, "this must fail on disagreement, not on too few pairs"
    assert np.isinf(fit.regions[region].residual_mm)
    assert "rims disagree" in fit.regions[region].unconstrained
    reduction = fit.reduction()
    assert np.isinf(reduction.residual_mm[region])
    assert any(region in n and "rims disagree" in n for n in reduction.notes)
    # What the plan keeps is JSON with no infinity in it, and still names the region.
    record = json.loads(json.dumps(reduction.record(), allow_nan=False))
    assert record["residual_mm"][region] is None and region in record["unconstrained"]
    assert record["accepted_by"] is None


def test_a_fracture_with_no_rim_at_all_is_unconstrained_and_still_placed(iliac, own_targets):
    phantom, vol, bodies, found = iliac
    region = "fracture_hip_right_fragment_1"
    fit = cg.fit_reduction(vol, "right", _with_rim(found, 0), bodies, {}, **own_targets)
    assert fit.regions[region].pairs == 0
    assert np.isinf(fit.regions[region].residual_mm) and "too little rim" in fit.regions[region].unconstrained
    assert len(fit.regions[region].xyz) > 0, "a region always says where it is"
    assert np.isinf(fit.reduction().residual_mm[region])


def _check_residual_contract(fit):
    """Every region: inf exactly when it says why, and otherwise never less
    than the phantom bound measured at its displacement (which is at least
    how far the fit moved it), its own mismatch, or, where it rests on the
    mirror, the mirror's floor, which its notes say. The Reduction carries
    the same numbers, under the same keys. (Since slice 1c: the bound was
    PHANTOM_BOUND_MM, one number per kind, before it was measured per
    displacement.)"""
    reduction = fit.reduction()
    assert set(reduction.residual_mm) == set(reduction.region_xyz) == set(fit.regions)
    assert reduction.accepted_by is None and reduction.notes[0] == cg.NOT_ACCEPTED
    # No region anywhere is inf with nothing said: the reason Corridor
    # Finder shows the surgeon is in the Reduction's notes, and not empty.
    for name, residual in reduction.residual_mm.items():
        if np.isinf(residual):
            said = [n for n in reduction.notes if n.startswith(f"{name}: unconstrained, its error is not known (")]
            assert said and not any(n.endswith("()") for n in said), f"{name}: inf with no reason given"
    # How far the fit moved each unit, at any region (7d.2's displacement).
    unit_travel = {}
    for region in fit.regions.values():
        if np.isfinite(region.travel_mm):
            for u in region.units:
                if u != "static":
                    unit_travel[u] = max(unit_travel.get(u, 0.0), region.travel_mm)
    for name, region in fit.regions.items():
        assert reduction.residual_mm[name] == region.residual_mm
        if region.kind != "unit" and np.isfinite(region.travel_mm):
            furthest = max([region.travel_mm] + [unit_travel[u] for u in region.units if u in unit_travel])
            assert region.displacement_mm == pytest.approx(furthest), (
                f"{name}: its bound is read at {region.displacement_mm:.2f} mm, but its units were displaced "
                f"{furthest:.2f} mm")
        assert np.isinf(region.residual_mm) == bool(region.unconstrained), region.sentence()
        assert not np.isnan(region.residual_mm)
        if np.isfinite(region.floor_mm):
            assert any(n.startswith("rests on the mirror") for n in region.notes), region.sentence()
            # The floor is the mirror's for that kind of region (DECISIONS,
            # the table under section 1), not any number.
            assert region.floor_mm == cg.MIRROR_FLOOR_MM[region.kind], region.sentence()
        # A region that says it rests on the mirror carries the floor.
        if any(n.startswith("rests on the mirror") for n in region.notes):
            assert np.isfinite(region.floor_mm), region.sentence()
        if not np.isfinite(region.residual_mm):
            continue
        if region.kind == "unit":
            assert region.floor_mm == cg.MIRROR_FLOOR_MM["unit"] and region.residual_mm >= region.floor_mm
            continue
        assert region.displacement_mm >= region.travel_mm, region.sentence()
        assert region.displacement_mm <= cg.PHANTOM_TRAVEL_MM[region.kind], region.sentence()
        assert region.bound_mm == cg.phantom_bound_mm(region.kind, region.displacement_mm), region.sentence()
        assert region.residual_mm >= region.bound_mm, region.sentence()
        if np.isfinite(region.mismatch_p90_mm):
            assert region.residual_mm >= region.mismatch_p90_mm, region.sentence()
        if np.isfinite(region.floor_mm):
            assert region.residual_mm >= region.floor_mm, region.sentence()


def _largest_bound(fit):
    """The largest phantom bound of any kind at the furthest any region of
    the fit was displaced: what the unit's own pose error is held to (it was
    max(PHANTOM_BOUND_MM.values()) before the bound was measured per
    displacement)."""
    furthest = max(r.displacement_mm for r in fit.regions.values() if np.isfinite(r.displacement_mm))
    return max(cg.phantom_bound_mm(kind, furthest) for kind in cg.PHANTOM_BOUND_TABLE_MM)


def test_every_region_reports_its_bound_or_inf_unilateral_and_iliac(sacral, own_targets, iliac):
    _, _, fit, *_ = _sacral_fit(sacral, own_targets, "left", "wrong")
    _check_residual_contract(fit)
    phantom, vol, bodies, found = iliac
    _check_residual_contract(cg.fit_reduction(vol, "right", found, bodies, {}, **own_targets))
    _check_residual_contract(cg.fit_reduction(vol, "right", _with_rim(found, 5), bodies, {}, **own_targets))


def test_every_region_reports_its_bound_or_inf_bilateral(bilateral):
    _check_residual_contract(bilateral[2])


def test_a_fragment_with_no_fracture_surface_is_never_missing_from_the_regions(iliac, own_targets):
    phantom, vol, bodies, found = iliac
    empty = fsm.FractureSurfaces([], [], {}, {}, {}, False, False, 0, [])
    fit = cg.fit_reduction(vol, "right", empty, bodies, {}, **own_targets)
    region = fit.regions["fracture_hip_right_fragment_1"]
    assert np.isinf(region.residual_mm) and "no fracture surface" in region.unconstrained
    assert len(region.xyz) > 0


def test_the_iliac_fracture_lands_within_its_residual(iliac, own_targets):
    phantom, vol, bodies, found = iliac
    fit = cg.fit_reduction(vol, "right", found, bodies, {}, **own_targets)
    landing = _landing(fit, _truth(vol, [(phantom.fragment, phantom.to_reference)]))
    _report("iliac wing moved 5 mm, exact start", fit, landing)
    _check_lands_within(fit, landing)
    assert np.isfinite(fit.regions["fracture_hip_right_fragment_1"].residual_mm)


# --------------------------------------------------------------------------
# Plan test 6: the round trip through reduction.apply_moves.


@pytest.fixture(scope="module", params=["unilateral-wrong", "bilateral"])
def round_trip(request, sacral, own_targets, bilateral):
    if request.param == "bilateral":
        phantom, vol, fit, truth_of = bilateral
    else:
        phantom, vol, fit, *_, truth_of = _sacral_fit(sacral, own_targets, "right", "wrong")
    return request.param, phantom, vol, fit, truth_of


def test_the_round_trip_lands_within_each_regions_residual(round_trip):
    label, phantom, vol, fit, truth_of = round_trip
    reduction = fit.reduction()
    assert reduction.accepted_by is None and reduction.source == cg.SOURCE
    reduced, overlaps = apply_moves(vol, reduction.moves)
    for lab, name in ((seg.HIP_R, "right hip"), (seg.HIP_L, "left hip"), (seg.SACRUM, "sacrum")):
        a, b = reduced.array == lab, phantom.intact_labels == lab
        dice = 2.0 * float((a & b).sum()) / float(a.sum() + b.sum())
        print(f"{label}: {name} after apply_moves overlaps the intact one {dice:.3f} (Dice)")
        assert dice >= 0.9
    for move in reduction.moves:
        assert overlaps[move.name] <= 0.02 * move.mask.sum(), f"{move.name}: {overlaps[move.name]} voxels on static bone"
    landing = _landing(fit, truth_of)
    _report(f"round trip, {label}", fit, landing)
    _check_lands_within(fit, landing)


# --------------------------------------------------------------------------
# What the Reduction carries.


def test_the_reduction_carries_every_flag_and_is_not_accepted(sacral, own_targets):
    _, _, fit, *_ = _sacral_fit(sacral, own_targets, "right", "wrong")
    reduction = fit.reduction()
    assert reduction.accepted_by is None
    assert reduction.notes[0] == cg.NOT_ACCEPTED
    assert any(fsm.SPLIT_UNCONFIRMED in n for n in reduction.notes), "the split is unconfirmed until confirmed"
    assert any("departs from the mirror start" in n for n in reduction.notes)
    assert any("mirror-twin veto not applied" in n for n in reduction.notes), "the surfaces' own notes are carried"
    assert set(reduction.residual_mm) == set(reduction.region_xyz) == set(fit.regions)
    assert all(len(np.asarray(v).reshape(-1, 3)) for v in reduction.region_xyz.values())
    assert [m.name for m in reduction.moves] == [u.name for u in fit.units]


def test_a_confirmed_split_is_said_confirmed(sacral, own_targets):
    phantom, vol, found, splits = sacral["right"]
    confirmed = dict(splits, right=fsm.confirm_split(splits["right"], "surgeon, review sheet 2026-10-03"))
    hip = phantom.labels == seg.HIP_R
    fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, np.linalg.inv(
        phantom.moved_by))]), confirmed, **own_targets)
    assert not any(fsm.SPLIT_UNCONFIRMED in n for n in fit.notes)
    assert any("confirmed by surgeon, review sheet" in n for n in fit.notes)
    # A confirmed split is not an accepted reduction (7c.5 is not 7c.8).
    reduction = fit.reduction()
    assert reduction.accepted_by is None and reduction.notes[0] == cg.NOT_ACCEPTED


def test_a_unilateral_injury_needs_its_mirror_start(sacral):
    _, vol, found, splits = sacral["right"]
    with pytest.raises(ValueError, match="starts from the mirror"):
        cg.fit_reduction(vol, "right", found, None, splits)
    refused = FragmentSet("both", "l5", "pre-selection", [], float("nan"), float("nan"), 0.0, refused="bilateral")
    with pytest.raises(ValueError):
        cg.fit_reduction(vol, "right", found, refused, splits)
    with pytest.raises(ValueError, match="injured must be"):
        cg.fit_reduction(vol, "middle", found, None, splits)
    # The other side's mirror start is not this side's.
    left = _fragment_set("left", [_body(0, None, vol.array == seg.HIP_L, np.eye(4))])
    with pytest.raises(ValueError, match="fragment set is for the left side"):
        cg.fit_reduction(vol, "right", found, left, splits)


def test_the_symphysis_is_measured_as_its_target_was():
    """The tool that measured the 4.93 mm target uses this very function."""
    import importlib.util
    import pathlib
    tool = pathlib.Path(__file__).resolve().parents[3] / "displacement-finder" / "tools" / "symphysis_gap.py"
    spec = importlib.util.spec_from_file_location("symphysis_gap_tool", tool)
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(None):
        spec.loader.exec_module(module)
    assert module.symphysis_gap is cg.symphysis_gap
    phantom = fractured_pelvis()
    median, _, levels = cg.symphysis_gap(_vol(phantom.labels, phantom))
    assert median == pytest.approx(6.0 + VOXEL_MM) and levels >= cg.SYMPHYSIS_MIN_LEVELS


def test_with_no_symphysis_the_gap_is_not_a_number():
    """One hip bone gone: there is no symphysis, and the gap is nan, never 0."""
    phantom = fractured_pelvis()
    labels = np.where(phantom.labels == seg.HIP_L, 0, phantom.labels).astype(phantom.labels.dtype)
    median, p90, levels = cg.symphysis_gap(_vol(labels, phantom))
    assert np.isnan(median) and np.isnan(p90) and levels == 0


# --------------------------------------------------------------------------
# Beyond the slides the first phantoms used (plan tests 1, 2 and 6 over the
# family the phantom bound is measured on).


def _iliac_slid():
    """fractured_pelvis's iliac wing opened 3 mm and slid 6 mm along its
    fracture."""
    n = np.array([0.2, 0.3, 1.0]) / np.linalg.norm([0.2, 0.3, 1.0])
    t = np.cross(n, [0.0, 1.0, 0.0])
    phantom = fractured_pelvis(translate_mm=tuple(3.0 * n + 6.0 * t / np.linalg.norm(t)))
    return phantom, _vol(phantom.labels, phantom)


WIDER = [("sacral", "right", (0.0, 0.0, 6.0), "wrong"), ("sacral", "right", (0.0, 6.0, 0.0), "exact"),
         ("sacral", "left", (0.0, 0.0, 6.0), "exact"), ("bilateral", None, ((0.0, 0.0, 6.0), (0.0, 6.0, 0.0)), None),
         ("iliac", "right", None, "wrong")]


@pytest.mark.parametrize("kind,side,move,start", WIDER, ids=lambda v: str(v))
def test_larger_slides_land_within_what_each_region_reports(kind, side, move, start, own_targets):
    """The sacral fracture slid 6 mm up or forward (the review's cases),
    both sides slid 6 mm, and the iliac wing slid 6 mm along its fracture.
    Every region lands within what it reports, and the fracture still
    reports a number. Each face is its body's whole broken surface: with
    faces only where the two bodies overlap as scanned, the right sacral
    fracture slid 6 mm up was fitted 5.6 mm off from the exact start."""
    if kind == "sacral":
        phantom = sacral_fractured_pelvis(side=side, hinge_deg=3.0, translate_mm=move)
        vol = _vol(phantom.labels, phantom)
        found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
        splits = fsm.split_sacrum(vol, found)
        truth = np.linalg.inv(phantom.moved_by)
        hip = phantom.labels == (seg.HIP_R if side == "right" else seg.HIP_L)
        femur = phantom.labels == (seg.FEMUR_R if side == "right" else seg.FEMUR_L)
        begin = truth if start == "exact" else _wrong(vol.mask_voxel_centers_world(hip)) @ truth
        fit = cg.fit_reduction(vol, side, found, _fragment_set(side, [_body(0, None, hip, begin)]), splits,
                               **own_targets)
        truth_of = _truth(vol, [(hip | phantom.lateral_fragment | femur, truth)])
        checked = [(fit.units[0], truth, hip)]
    elif kind == "bilateral":
        phantom = bilateral_sacral_fractured_pelvis(hinge_deg=(3.0, 2.0), translate_mm=move)
        vol = _vol(phantom.labels, phantom)
        found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
        fit = cg.fit_reduction(vol, "both", found, None, fsm.split_sacrum(vol, found), **own_targets)
        moving, checked = [], []
        for unit, hip_id, femur_id in zip(fit.units, (seg.HIP_R, seg.HIP_L), (seg.FEMUR_R, seg.FEMUR_L)):
            truth = np.linalg.inv(phantom.moved_by[unit.side])
            mask = (phantom.labels == hip_id) | phantom.lateral_fragments[unit.side] | (phantom.labels == femur_id)
            moving.append((mask, truth))
            checked.append((unit, truth, phantom.labels == hip_id))
        truth_of = _truth(vol, moving)
    else:
        phantom, vol = _iliac_slid()
        main = (phantom.labels == seg.HIP_R) & ~phantom.fragment
        begin = _wrong(vol.mask_voxel_centers_world(phantom.fragment)) @ phantom.to_reference
        bodies = _fragment_set("right", [_body(0, None, main, np.eye(4)), _body(1, 0, phantom.fragment, begin)])
        found = fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,), fragment_sets=[bodies])
        fit = cg.fit_reduction(vol, "right", found, bodies, {}, **own_targets)
        truth_of = _truth(vol, [(phantom.fragment, phantom.to_reference)])
        checked = [(fit.units[1], phantom.to_reference, phantom.fragment)]
    landing = _landing(fit, truth_of)
    lines = []
    for unit, truth, mask in checked:
        off = _pose_error(unit.transform, truth, vol.mask_voxel_centers_world(mask))
        lines.append(f"{unit.name} fitted {off[0]:.2f} mm / {off[1]:.2f} deg off")
        if start == "exact":
            assert off[0] <= STAY_MM, "the fit walked away from the exact start"
    _report(f"{kind} {side or ''} {move} from the {start or 'scanned'} start: " + "; ".join(lines), fit, landing)
    _check_lands_within(fit, landing)
    _check_residual_contract(fit)
    fractures = [r for r in fit.regions.values() if r.kind == "fracture"]
    assert fractures and any(np.isfinite(r.residual_mm) for r in fractures), [r.sentence() for r in fractures]


def test_each_face_is_its_bodys_whole_broken_surface():
    """Slid 6 mm up, the lateral fragment's face reaches 6 mm above the
    central sacrum's as scanned; carried home, both faces span the same
    height. Taken only where they overlap as scanned, the lateral face
    stopped 6 mm short of its own top, and its rim with it."""
    phantom = sacral_fractured_pelvis(side="right", hinge_deg=3.0, translate_mm=(0.0, 0.0, 6.0))
    vol = _vol(phantom.labels, phantom)
    found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
    split = fsm.split_sacrum(vol, found)["right"]
    surface = cg._split_surface(vol, split, [s for s in found.surfaces if s.id in split.surface_ids])
    lateral, central = surface.faces
    home = transform_points(np.linalg.inv(phantom.moved_by), lateral.points)
    print(f"top of the lateral face at home {home[:, 2].max():.1f} mm, of the central face "
          f"{central.points[:, 2].max():.1f} mm")
    assert abs(home[:, 2].max() - central.points[:, 2].max()) <= VOXEL_MM
    assert abs(home[:, 2].min() - central.points[:, 2].min()) <= VOXEL_MM


def test_displaced_further_than_the_phantoms_is_unconstrained(own_targets):
    """Slid 25 mm up and 25 mm back (35 mm) from the wrong mirror start: the
    fit moves its fracture further than any phantom the bound was measured on
    (PHANTOM_TRAVEL_MM, 28 mm since slice 1c), so every region of that hip
    says so. Replaces slice 1b's test, which slid the fracture 10 mm against
    the 8 mm the bound was then measured to; the 10 mm slide now lies inside
    the family (test_a_fit_that_stops_short_reads_the_bound_where_its_unit_was_displaced)."""
    phantom = sacral_fractured_pelvis(side="right", hinge_deg=3.0, translate_mm=(0.0, -25.0, 25.0))
    vol = _vol(phantom.labels, phantom)
    found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
    truth = np.linalg.inv(phantom.moved_by)
    hip = phantom.labels == seg.HIP_R
    begin = _wrong(vol.mask_voxel_centers_world(hip)) @ truth
    fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, begin)]),
                           fsm.split_sacrum(vol, found), **own_targets)
    femur = phantom.labels == seg.FEMUR_R
    landing = _landing(fit, _truth(vol, [(hip | phantom.lateral_fragment | femur, truth)]))
    _report("sacral fracture slid 35 mm (25 up, 25 back), wrong start", fit, landing)
    fracture = [r for r in fit.regions.values() if r.kind == "fracture"][0]
    assert fracture.travel_mm > cg.PHANTOM_TRAVEL_MM["fracture"]
    for region in fit.regions.values():
        assert np.isinf(region.residual_mm), region.sentence()
        assert "further than the phantoms" in region.unconstrained, region.sentence()
    _check_residual_contract(fit)


def test_a_fit_that_stops_short_reads_the_bound_where_its_unit_was_displaced(own_targets):
    """Slid 10 mm up from the wrong mirror start the fit stops short: its
    symphysis moves less than its fracture (slice 1b measured 6.5 against
    10.2 mm, the symphysis landing 8.4 mm off). Each region's bound is read at
    the furthest its units were displaced at any region, so the symphysis
    takes the fracture's displacement, and every region lands within what it
    reports."""
    phantom = sacral_fractured_pelvis(side="right", hinge_deg=3.0, translate_mm=(0.0, 0.0, 10.0))
    vol = _vol(phantom.labels, phantom)
    found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
    truth = np.linalg.inv(phantom.moved_by)
    hip = phantom.labels == seg.HIP_R
    begin = _wrong(vol.mask_voxel_centers_world(hip)) @ truth
    fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, begin)]),
                           fsm.split_sacrum(vol, found), **own_targets)
    femur = phantom.labels == seg.FEMUR_R
    landing = _landing(fit, _truth(vol, [(hip | phantom.lateral_fragment | femur, truth)]))
    _report("sacral fracture slid 10 mm up, wrong start", fit, landing)
    furthest = max(r.travel_mm for r in fit.regions.values() if "hip_right" in r.units and np.isfinite(r.travel_mm))
    for region in fit.regions.values():
        if "hip_right" in region.units and region.kind != "unit":
            assert region.displacement_mm == pytest.approx(furthest), region.sentence()
    symphysis = fit.regions["symphysis"]
    assert symphysis.travel_mm < furthest, "the fit no longer stops short here; this test needs another case"
    _check_lands_within(fit, landing)
    _check_residual_contract(fit)


# --------------------------------------------------------------------------
# What is never missing and never reads as safe.


def test_a_marked_fracture_with_no_surface_found_is_a_region_of_unknown_error(sacral, own_targets):
    """The surgeon marks a fracture low on the right hip (moving with it)
    and low on the left hip (static), and no surface is found near either:
    each is a region, inf, at the marks moved with the bone they lie on, and
    Corridor Finder warns at it whatever the screw's room."""
    phantom, vol, _, splits = sacral["right"]
    marks = []
    for hip_id in (seg.HIP_R, seg.HIP_L):
        bone = vol.mask_voxel_centers_world(phantom.labels == hip_id)
        low = bone[bone[:, 2] <= bone[:, 2].min() + 4.0]
        marks.append(fit_plane([low[np.argmin(low[:, 0])], low[np.argmax(low[:, 0])], low[np.argmin(low[:, 1])],
                                low[np.argmax(low[:, 1])]]))
    found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,), marks=marks)
    assert len(found.unmatched_marks) == 2, found.notes
    truth = np.linalg.inv(phantom.moved_by)
    hip = phantom.labels == seg.HIP_R
    fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, truth)]), splits,
                           **own_targets)
    reduction = fit.reduction()
    right, left = fit.regions["fracture_mark_1"], fit.regions["fracture_mark_2"]
    print(right.sentence())
    for region in (right, left):
        assert np.isinf(reduction.residual_mm[region.name]) and "surgeon marked a fracture" in region.unconstrained
    assert right.units == ("hip_right",) and left.units == ("static",)
    # Each region holds its marks, moved with the bone they lie on, and
    # covers the marked plane around them out to fracture.NEAR_MARKS_MM, no
    # further.
    for region, where in ((right, transform_points(fit.units[0].transform, marks[0].marks)), (left, marks[1].marks)):
        to_region = cKDTree(region.xyz).query(where)[0]
        assert np.all(to_region < 1e-6), to_region
        assert np.all(cKDTree(where).query(region.xyz)[0] <= cg.NEAR_MARKS_MM + 1e-6)
        assert len(region.xyz) > len(where)
    assert any(n.startswith("fracture_mark_1: unconstrained") for n in reduction.notes)
    near = np.asarray(reduction.region_xyz["fracture_mark_1"]).reshape(-1, 3)[:2]
    warnings = reduction_warnings(near, np.full(len(near), 50.0), reduction)
    assert any(w["region"] == "fracture_mark_1" for w in warnings)
    _check_residual_contract(fit)


def test_a_mark_no_surface_lies_near_is_a_region_though_the_others_are_matched(sacral, own_targets):
    """The surgeon marks the right sacral fracture at two points on the
    face found and once more on the sacrum far from every face found (the
    review's S1 and S3 example). The surface matches the first two; the
    third is a region of its own, inf, over the marked plane around that
    mark (out to fracture.NEAR_MARKS_MM, as far as Corridor Finder treats the
    plane as the fracture), and Corridor Finder warns there whatever the
    screw's room: at the mark, and on the plane 15 mm from it, where a
    region at the mark alone left a screw unwarned."""
    phantom, vol, found, splits = sacral["right"]
    faces = np.vstack([f.points for s in found.surfaces if s.label == seg.SACRUM for f in s.faces])
    sacrum = vol.mask_voxel_centers_world(phantom.labels == seg.SACRUM)
    away = cKDTree(faces).query(sacrum)[0]
    far = sacrum[np.argmin(np.abs(away - 40.0))]
    mark = fit_plane([faces[np.argmin(faces[:, 2])], faces[np.argmax(faces[:, 2])], far])
    assert mark is not None
    marked = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,), marks=[mark])
    assert [list(m.unmatched) for m in marked.unmatched_marks] == [[False, False, True]], marked.notes
    truth = np.linalg.inv(phantom.moved_by)
    hip = phantom.labels == seg.HIP_R
    fit = cg.fit_reduction(vol, "right", marked, _fragment_set("right", [_body(0, None, hip, truth)]),
                           fsm.split_sacrum(vol, marked), **own_targets)
    region = fit.regions["fracture_mark_1"]
    print(region.sentence())
    assert np.isinf(region.residual_mm) and "1 of its 3 marks" in region.unconstrained
    unit = cg._unit_of(np.rint(vol.world_to_zyx_indices(far[None])).astype(int).T, fit.units)[0]
    pose = np.eye(4) if unit == cg.STATIC else fit.units[unit].transform
    at_mark = transform_points(pose, far[None])[0]
    assert np.min(np.linalg.norm(region.xyz - at_mark, axis=1)) < 1e-6
    reduction = fit.reduction()
    warnings = reduction_warnings(at_mark[None], np.full(1, 50.0), reduction)
    assert any(w["region"] == "fracture_mark_1" for w in warnings)
    # On the marked plane 15 mm from the unmatched mark, inside NEAR_MARKS_MM
    # but further than REGION_RADIUS_MM from the mark itself: a screw there
    # crosses the marked fracture where nothing is known, so it is warned.
    e1, _ = cg._plane_basis(mark.normal)
    on_plane = far - float(np.dot(far - mark.point, mark.normal)) * mark.normal
    between = transform_points(pose, (on_plane + 15.0 * e1)[None])[0]
    assert np.linalg.norm(between - at_mark) > cg.REGION_RADIUS_MM
    assert np.min(np.linalg.norm(region.xyz - between, axis=1)) <= cg.REGION_RADIUS_MM
    warnings = reduction_warnings(between[None], np.full(1, 50.0), reduction)
    assert any(w["region"] == "fracture_mark_1" for w in warnings)
    _check_residual_contract(fit)


def test_surfaces_judged_unreliable_on_their_own_do_not_pin_a_unit(sacral, own_targets, monkeypatch):
    """A unit counts as pinned only by regions trustworthy in their own
    right. Here every region is made unconstrained for a reason of its own
    (as "too little rim" or "rims disagree" would), so nothing trustworthy
    pins the right hip: it must carry an unpinned region over all of its
    bone. Counting the unreliable regions' rows, as the fit first did, read
    the same hip as pinned (the unaltered fit gives it no such region), and
    a screw in it far from every joint went unwarned."""
    args, truth, _ = _sacral_fit_args(sacral, "right", "exact")
    plain = cg.fit_reduction(*args, **own_targets)
    assert "unit_hip_right_unpinned" not in plain.regions, [r.sentence() for r in plain.regions.values()]

    real_assess = cg._assess

    def unreliable_on_its_own(region, rows, poses, centres, radii, null, *rest, **kw):
        fit = real_assess(region, rows, poses, centres, radii, null, *rest, **kw)
        if not null.shape[1]:  # the fit's own-reasons pass
            return dataclasses.replace(fit, residual_mm=float("inf"), unconstrained="too little rim (forced)")
        return fit

    monkeypatch.setattr(cg, "_assess", unreliable_on_its_own)
    fit = cg.fit_reduction(*args, **own_targets)
    region = fit.regions.get("unit_hip_right_unpinned")
    assert region is not None and np.isinf(region.residual_mm), [r.sentence() for r in fit.regions.values()]
    _check_residual_contract(fit)


def test_a_fracture_left_as_scanned_is_never_a_small_number(own_targets):
    """The iliac wing opened 3 mm and slid 6 mm, fitted as both sides
    injured (CLINIC_0060's route): slice 1's fragments do not move, so the
    fracture is left as scanned. Its rims' mismatch read 4.3-5.4 mm however
    far the wing was slid; it is unconstrained, and the Reduction says the
    fracture was not reduced."""
    phantom, vol = _iliac_slid()
    found = fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,))
    assert [s.id for s in found.surfaces] == ["hip_right_1"], found.sentence()
    fit = cg.fit_reduction(vol, "both", found, None, {}, **own_targets)
    region = fit.regions["fracture_hip_right_1"]
    print(region.sentence())
    assert np.isinf(region.residual_mm) and region.unconstrained.startswith("NOT REDUCED")
    assert region.units == ("hip_right",)
    reduction = fit.reduction()
    assert np.isinf(reduction.residual_mm["fracture_hip_right_1"])
    assert any(n.startswith("fracture_hip_right_1: unconstrained") and "NOT REDUCED" in n for n in reduction.notes)
    _check_residual_contract(fit)
    # With too little rim left to pair (or none), it still says first that
    # it was never reduced, not only that its rim is short.
    for keep in (5, 0):
        starved = cg.fit_reduction(vol, "both", _with_rim(found, keep), None, {}, **own_targets).regions[region.name]
        print(starved.sentence())
        assert np.isinf(starved.residual_mm) and starved.unconstrained.startswith("NOT REDUCED"), starved.sentence()


def test_a_regions_own_notes_are_carried_under_its_name():
    region = cg.RegionFit("fracture_x", "fracture", ("hip_right",), 40, 1.0, 6.5, 6.5, np.zeros((1, 3)),
                          notes=["something the surgeon must read"])
    fit = cg.CongruenceFit("right", [], {"fracture_x": region}, {}, 4.93, 1)
    assert "fracture_x: something the surgeon must read" in fit.flags()


def test_units_that_share_voxels_are_refused(sacral, own_targets):
    """Two splits claiming the same bone would move it twice."""
    phantom, vol, found, splits = sacral["right"]
    right = splits["right"]
    both = {"right": right, "left": fsm.replace(right, side="left")}
    with pytest.raises(ValueError, match="share"):
        cg.fit_reduction(vol, "both", found, None, both, **own_targets)


# --------------------------------------------------------------------------
# Slice 1c, part B (displacement-finder DECISIONS 7d.2, 7d.6): the bound
# measured per displacement to 30 mm, and impacted fractures reduced by
# their rims and the mirror (plan tests 5 and 6).

BOUND_DISPLACEMENTS_MM = (5.0, 10.0, 15.0, 20.0, 25.0, 30.0)
# The impacted phantom's band is given twice the margin, as in
# test_fracture_surface: a band the CT route finds, not a claim about how
# dense a real one is.
IMPACTED_BAND_HU = 2.0 * fsm.IMPACTION_MARGIN_HU


def test_the_bound_is_measured_per_displacement_and_never_below_what_was_measured():
    """7d.2: at every displacement the phantoms were run at (0 to 30 mm),
    each kind's bound is at least the worst landing measured there; between
    two of them it is interpolated, so never below the smaller of the two
    (each holds every landing measured between them); it never falls as the
    displacement grows; past the furthest displacement any region reported
    a number at (PHANTOM_TRAVEL_MM, never past 30 mm) there is none; and the
    SI joint, never measured where it pins a hip, takes the largest."""
    nodes = cg.PHANTOM_DISPLACEMENTS_MM
    assert nodes[0] == 0.0 and nodes[-1] == 30.0 and set(BOUND_DISPLACEMENTS_MM) <= set(nodes)
    for kind in ("fracture", "symphysis", "si"):
        table, measured = cg.PHANTOM_BOUND_TABLE_MM[kind], cg.PHANTOM_BOUND_MEASURED_MM[kind]
        print(f"{kind}: " + ", ".join(f"{d:.0f} mm {t:.1f} (measured {m:.2f})" for d, t, m in zip(nodes, table, measured)))
        assert len(table) == len(measured) == len(nodes)
        limit = cg.PHANTOM_TRAVEL_MM[kind]
        for d, t, m in zip(nodes, table, measured):
            if d <= limit:
                assert cg.phantom_bound_mm(kind, d) == t
            if np.isfinite(m):
                assert t >= m, f"{kind} at {d} mm: bound {t} below the {m} mm measured"
        assert np.all(np.diff(table) >= 0)
        for k in range(len(nodes) - 1):
            for x in np.linspace(nodes[k], min(nodes[k + 1], limit), 7):
                assert cg.phantom_bound_mm(kind, x) >= min(table[k], table[k + 1])
        assert nodes[-2] < limit <= nodes[-1]
        assert np.isfinite(cg.phantom_bound_mm(kind, limit))
        assert np.isinf(cg.phantom_bound_mm(kind, limit + 0.01))
    for i in range(len(nodes)):
        assert cg.PHANTOM_BOUND_TABLE_MM["si"][i] >= max(cg.PHANTOM_BOUND_TABLE_MM["fracture"][i],
                                                         cg.PHANTOM_BOUND_TABLE_MM["symphysis"][i])
    with pytest.raises(ValueError):
        cg.phantom_bound_mm("unit", 5.0)


def test_the_bound_says_nothing_past_the_phantoms_and_never_a_number_for_an_unknown_displacement():
    """Past 30 mm, past each kind's travel limit, and for a displacement that
    is not a number or infinite, the bound is inf (never the last value of
    the table carried on). At or under no displacement it is the table's
    first value, never less."""
    for kind in cg.PHANTOM_BOUND_TABLE_MM:
        for beyond in (30.0 + 1e-6, 31.0, 35.0, 100.0, 1e6, float("inf"), float("nan")):
            assert np.isinf(cg.phantom_bound_mm(kind, beyond)), (kind, beyond)
        assert cg.PHANTOM_TRAVEL_MM[kind] <= 30.0
        for under in (0.0, -0.5, -10.0):
            assert cg.phantom_bound_mm(kind, under) == cg.PHANTOM_BOUND_TABLE_MM[kind][0]


def test_the_table_follows_from_what_was_measured_by_its_stated_rule():
    """The constants as their provenance states them: each kind's table is
    its worst measured landing at each displacement rounded up to half a
    millimetre and never smaller than at a smaller displacement; the SI
    joint's is the largest of all kinds' measured. A hand-edited table that
    dropped below what was measured anywhere, or below an earlier
    displacement's, differs from this."""
    nodes = cg.PHANTOM_DISPLACEMENTS_MM
    measured = cg.PHANTOM_BOUND_MEASURED_MM

    def rule(values):
        rounded = [np.ceil(v * 2.0) / 2.0 for v in values]
        return tuple(float(v) for v in np.maximum.accumulate(rounded))

    for kind in ("fracture", "symphysis"):
        assert all(np.isfinite(measured[kind])), kind
        assert cg.PHANTOM_BOUND_TABLE_MM[kind] == rule(measured[kind]), kind
    largest = [max(measured[k][i] for k in ("fracture", "symphysis", "si")) for i in range(len(nodes))]
    assert cg.PHANTOM_BOUND_TABLE_MM["si"] == rule(largest)


def _phantom_bound_tool():
    import importlib.util
    import pathlib
    tool = pathlib.Path(__file__).resolve().parents[3] / "displacement-finder" / "tools" / "phantom_bound.py"
    spec = importlib.util.spec_from_file_location("phantom_bound_tool", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("seed", range(5))
def test_the_tools_table_is_never_below_a_landing_it_was_given_at_that_displacement(seed, monkeypatch):
    """7d.2's rule ("never let the bound at a displacement be lower than what
    the phantoms measured there") on the tool that turns landings into the
    table, phantom_bound.table, fed random landings: with its table and
    travel limit in place, phantom_bound_mm at every landing's displacement
    is at least that landing, wherever it reported a number; the limit never
    passes 30 mm, covers every landing up to 30 mm, and is inf just past
    it."""
    tool = _phantom_bound_tool()
    rng = np.random.default_rng(seed)
    samples = []
    for kind in ("fracture", "symphysis", "si"):
        n = int(rng.integers(3, 40))
        displacement = rng.uniform(0.0, 34.0, n)
        if kind == "si":
            displacement = rng.uniform(0.0, 10.0, n)  # as measured: only near where it does not pin a hip
        landing = np.where(rng.random(n) < 0.2, rng.uniform(0.0, 40.0, n), rng.uniform(0.0, 1.2, n) * displacement)
        samples += [(f"case {i}", kind, float(d), float(x)) for i, (d, x) in enumerate(zip(displacement, landing))]
    measured, tables, furthest, travel = tool.table(samples)
    monkeypatch.setattr(cg, "PHANTOM_BOUND_TABLE_MM", tables)
    monkeypatch.setattr(cg, "PHANTOM_TRAVEL_MM", travel)
    worst = {}
    for _, kind, d, x in samples:
        assert travel[kind] <= 30.0
        if d <= 30.0:
            assert d <= travel[kind], (kind, d, travel[kind])
        bound = cg.phantom_bound_mm(kind, d)
        if np.isfinite(bound):
            assert bound >= x, f"{kind}: a landing of {x:.2f} mm at {d:.2f} mm, but the bound there is {bound:.2f}"
            # The SI joint is held to every kind's landings, as its table says.
            assert cg.phantom_bound_mm("si", d) >= x
            worst[kind] = max(worst.get(kind, 0.0), x)
        else:
            assert d > travel[kind]
    for kind in tables:
        assert np.isinf(cg.phantom_bound_mm(kind, travel[kind] + 0.01))
    print(f"seed {seed}: travel {travel}, worst landing held {worst}")


def test_a_region_whose_unit_was_displaced_past_its_own_kinds_limit_is_unconstrained_and_says_so(own_targets,
                                                                                                 monkeypatch):
    """The limits differ by kind (27 mm at the symphysis, 28 mm at a fracture),
    and a region's displacement is how far its unit was moved at any region.
    A fracture that moves its unit between the two limits leaves its
    symphysis displaced past the symphysis's limit, where its bound is inf:
    the region must then be unconstrained, with the reason, never an inf
    with nothing said (or, worse, a number). That 1 mm window is too narrow
    to hit with a phantom, so it is widened here: the sacral fracture slid
    10 mm from the wrong start stops short (its symphysis moves 6.5 mm, its
    fracture 10.2 mm), and the symphysis's limit is put between the two."""
    monkeypatch.setitem(cg.PHANTOM_TRAVEL_MM, "symphysis", 8.0)
    phantom = sacral_fractured_pelvis(side="right", hinge_deg=3.0, translate_mm=(0.0, 0.0, 10.0))
    vol = _vol(phantom.labels, phantom)
    found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
    truth = np.linalg.inv(phantom.moved_by)
    hip = phantom.labels == seg.HIP_R
    begin = _wrong(vol.mask_voxel_centers_world(hip)) @ truth
    fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, begin)]),
                           fsm.split_sacrum(vol, found), **own_targets)
    symphysis = fit.regions["symphysis"]
    print(symphysis.sentence(), f"(moved {symphysis.travel_mm:.2f} mm, displaced {symphysis.displacement_mm:.2f} mm, "
                                f"residual {symphysis.residual_mm})")
    assert symphysis.travel_mm <= 8.0 < symphysis.displacement_mm, "this case no longer stops short; find another"
    assert np.isinf(symphysis.residual_mm)
    assert symphysis.unconstrained, "inf with no reason given"
    _check_residual_contract(fit)


def _displaced(kind, displacement_mm, own_targets):
    """A phantom of the family displaced this far with rotation, fitted from
    the wrong mirror start: the right sacral fracture hinged 3 degrees and
    slid up, or the iliac wing opened 2 mm, turned 3 degrees about its
    fracture's normal and slid laterally along it. Returns (phantom, vol,
    fit, truth_of, (the moved piece's truth, its mask))."""
    if kind == "sacral":
        phantom = sacral_fractured_pelvis(side="right", hinge_deg=3.0, translate_mm=(0.0, 0.0, displacement_mm))
        vol = _vol(phantom.labels, phantom)
        found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
        truth = np.linalg.inv(phantom.moved_by)
        hip = phantom.labels == seg.HIP_R
        begin = _wrong(vol.mask_voxel_centers_world(hip)) @ truth
        fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, begin)]),
                               fsm.split_sacrum(vol, found), **own_targets)
        moving = hip | phantom.lateral_fragment | (phantom.labels == seg.FEMUR_R)
        return phantom, vol, fit, _truth(vol, [(moving, truth)]), (truth, hip)
    normal = np.array([0.2, 0.3, 1.0]) / np.linalg.norm([0.2, 0.3, 1.0])
    lateral = -np.cross(normal, [0.0, 1.0, 0.0])
    lateral /= np.linalg.norm(lateral)
    phantom = fractured_pelvis(translate_mm=tuple(2.0 * normal + displacement_mm * lateral), rotate_deg=3.0,
                               rotate_axis=tuple(normal))
    vol = _vol(phantom.labels, phantom)
    main = (phantom.labels == seg.HIP_R) & ~phantom.fragment
    begin = _wrong(vol.mask_voxel_centers_world(phantom.fragment)) @ phantom.to_reference
    bodies = _fragment_set("right", [_body(0, None, main, np.eye(4)), _body(1, 0, phantom.fragment, begin)])
    found = fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,), fragment_sets=[bodies])
    fit = cg.fit_reduction(vol, "right", found, bodies, {}, **own_targets)
    truth_of = _truth(vol, [(phantom.fragment, phantom.to_reference)])
    return phantom, vol, fit, truth_of, (phantom.to_reference, phantom.fragment)


@pytest.mark.parametrize("displacement", BOUND_DISPLACEMENTS_MM)
@pytest.mark.parametrize("kind", ["sacral", "iliac"])
def test_each_region_gets_the_bound_of_its_displacement_and_the_round_trip_lands_within_it(kind, displacement,
                                                                                         own_targets):
    """Plan test 5: at every measured displacement, 5 to 30 mm, a region
    moved that far gets the bound measured there (a region moved 15 mm gets
    the 15 mm bound), and the round trip through reduction.apply_moves lands
    within each region's residual, printed. Both phantoms are in the family
    the table was measured on, so this checks that the table is read where
    it was measured and kept, not a held-out error. At 30 mm no region of
    either reports a number (the sacral fracture is left unresisted along
    itself, the iliac wing leaves no fracture surface), which is why
    PHANTOM_TRAVEL_MM stops short of 30 mm; there the round trip is checked
    against inf."""
    phantom, vol, fit, truth_of, (truth, mask) = _displaced(kind, displacement, own_targets)
    reduction = fit.reduction()
    reduced, overlaps = apply_moves(vol, reduction.moves)
    dice = {}
    for lab, name in ((seg.HIP_R, "right hip"), (seg.HIP_L, "left hip"), (seg.SACRUM, "sacrum")):
        a, b = reduced.array == lab, phantom.intact_labels == lab
        dice[name] = 2.0 * float((a & b).sum()) / float(a.sum() + b.sum())
    landing = _landing(fit, truth_of)
    moved = [u for u in fit.units if (u.mask & mask).sum() >= 0.9 * mask.sum()][0]
    off = _pose_error(moved.transform, truth, vol.mask_voxel_centers_world(mask))
    _report(f"{kind} displaced {displacement:.0f} mm with rotation, wrong start, round trip (Dice "
            + ", ".join(f"{k} {v:.3f}" for k, v in dice.items()) + f"; the moved piece {off[0]:.2f} mm / "
            f"{off[1]:.2f} deg off at its worst point)", fit, landing)
    for name, region in fit.regions.items():
        if region.kind != "unit" and np.isfinite(region.residual_mm):
            print(f"  {name}: displaced {region.displacement_mm:.2f} mm, so its bound is the table's there, "
                  f"{region.bound_mm:.2f} mm")
            assert region.bound_mm == cg.phantom_bound_mm(region.kind, region.displacement_mm)
    # The Dice overlap is printed, not held to slice 1b's 0.9: from the wrong
    # start the moved piece keeps part of the mirror's error, and the right
    # hip read 0.85-0.89 at some displacements (the thin iliac wing 5 mm and
    # 25 mm off, the sacral unit at 10-20 mm). What a region reports is held
    # to where it lands, below.
    for move in reduction.moves:
        assert overlaps[move.name] <= 0.02 * move.mask.sum(), f"{move.name}: {overlaps[move.name]} voxels on static bone"
    _check_lands_within(fit, landing)
    _check_residual_contract(fit)
    fractures = [r for r in fit.regions.values() if r.kind == "fracture" and np.isfinite(r.residual_mm)]
    if displacement < cg.PHANTOM_TRAVEL_MM["fracture"]:
        assert fractures, "the fracture reports no number here, so this displacement measures nothing: " + fit.sentence()
    for r in fractures:
        assert r.displacement_mm >= displacement - VOXEL_MM, r.sentence()


@pytest.fixture(scope="module")
def straight_confirmed():
    """The untilted pelvis's mirror plane, confirmed with the sacrum
    fractured: every sacral phantom shares it (fitted to L5)."""
    reference = fractured_pelvis()
    return mirror.confirm(mirror.fit_reference(_vol(reference.labels, reference)), sacrum_fractured=True)


@pytest.fixture(scope="module")
def impacted(straight_confirmed):
    """The impacted sacral phantoms (4 and 6 mm, the band twice the margin),
    found from the CT against the confirmed mirror, and split."""
    confirmed = straight_confirmed
    out = {}
    for depth in (4.0, 6.0):
        phantom = impacted_sacral_pelvis(depth_mm=depth, band_excess_hu=IMPACTED_BAND_HU)
        vol = _vol(phantom.labels, phantom)
        found = fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=_vol(phantom.ct, phantom), bones=(seg.SACRUM,),
                                           injured="right")
        out[depth] = (phantom, vol, found, fsm.split_sacrum(vol, found, confirmed))
    return out


def _impacted_fit(impacted, own_targets, depth, start, injured="right"):
    phantom, vol, found, splits = impacted[depth]
    sacral = phantom.sacral
    truth = np.linalg.inv(sacral.moved_by)
    hip = sacral.labels == seg.HIP_R
    begin = truth if start == "exact" else _wrong(vol.mask_voxel_centers_world(hip)) @ truth
    bodies = _fragment_set("right", [_body(0, None, hip, begin)]) if injured != "both" else None
    fit = cg.fit_reduction(vol, injured, found, bodies, splits, **own_targets)
    moving = hip | sacral.lateral_fragment | (sacral.labels == seg.FEMUR_R)
    return phantom, vol, found, fit, truth, begin, _truth(vol, [(moving, truth)])


@pytest.mark.parametrize("start", ["exact", "wrong"])
def test_an_impacted_fracture_is_reduced_by_its_rims_and_the_mirror(impacted, own_targets, start):
    """Plan test 6 (7d.6): the lateral fragment driven 4 mm into the sacrum,
    one solid label, the band found from the CT. Its rims are fitted along
    the fracture and the length lost across it is the mirror start's: from
    the exact start the fit pulls the impaction back out (the fragment moves
    laterally by the depth, to within a voxel) and does not walk; from either
    start the hip lands within what the fracture reports, every region lands
    within what it reports, the fracture reports at least the mirror's
    floor, and its notes, and the Reduction's, say it rests on the mirror."""
    phantom, vol, found, fit, truth, begin, truth_of = _impacted_fit(impacted, own_targets, 4.0, start)
    assert [s.source for s in found.surfaces] == [fsm.CT_IMPACTED], found.sentence()
    surface = found.surfaces[0]
    region = fit.regions[surface.region]
    unit = fit.units[0]
    outline = vol.mask_voxel_centers_world(unit.mask & ~ndi.binary_erosion(unit.mask))
    before, after = _pose_error(begin, truth, outline), _pose_error(unit.transform, truth, outline)
    on_unit = np.vstack([side[units == 0] for side, units in zip(region.sides, region.side_units)])
    pulled = float(np.median(transform_points(unit.transform, on_unit)[:, 0] - on_unit[:, 0]))
    landing = _landing(fit, truth_of)
    _report(f"impacted 4 mm (band read {surface.impaction_depth_mm:.2f} mm) from the {start} start: start off "
            f"{before[0]:.2f} mm / {before[1]:.2f} deg, fitted off {after[0]:.2f} mm / {after[1]:.2f} deg; the fragment's "
            f"face moved {pulled:.2f} mm laterally", fit, landing)
    print("  " + "\n  ".join(region.notes))
    assert np.isfinite(region.residual_mm), region.sentence()
    assert region.floor_mm == cg.MIRROR_FLOOR_MM["fracture"] and region.residual_mm >= region.floor_mm
    assert any(n.startswith("rests on the mirror") and "7d.6" in n for n in region.notes)
    assert any(n.startswith(f"{region.name}: rests on the mirror") for n in fit.reduction().notes)
    assert after[0] <= region.residual_mm, "the fit does not recover the pose within what the fracture reports"
    if start == "exact":
        assert after[0] <= STAY_MM, "the fit walked away from the exact start"
        assert abs(pulled - phantom.depth_mm) <= VOXEL_MM, "the impaction was not pulled back out"
    else:
        assert after[0] < before[0]
    _check_lands_within(fit, landing)
    _check_residual_contract(fit)


def test_a_unit_whose_pose_rests_on_the_mirror_is_a_region_over_all_of_its_bone(impacted, own_targets):
    """Where only the mirror's length across the impacted fracture pins a
    motion of the hip, the hip rests on the mirror as a whole: a region over
    all its bone carries the mirror's floor for a whole hemipelvis, so a
    screw far from the fracture and the joints is still warned when its room
    is less than that. Without it the mirror's rows would read the hip as
    pinned and that screw as safe."""
    phantom, vol, found, fit, *_ = _impacted_fit(impacted, own_targets, 4.0, "wrong")
    region = fit.regions["unit_hip_right_on_mirror"]
    print(region.sentence(), region.notes)
    assert region.kind == "unit" and region.units == ("hip_right",)
    assert region.residual_mm == cg.MIRROR_FLOOR_MM["unit"] and not region.unconstrained
    unit = fit.units[0]
    bone = transform_points(unit.transform, vol.mask_voxel_centers_world(unit.mask))
    assert cKDTree(region.xyz).query(bone)[0].max() <= REGION_RADIUS_MM / 2.0
    others = np.vstack([np.asarray(r.xyz).reshape(-1, 3) for k, r in fit.regions.items() if k != region.name])
    far = bone[cKDTree(others).query(bone)[0] > REGION_RADIUS_MM + 5.0]
    assert len(far) > 1000, "the case the region is for: hip bone far from every other region"
    screw = far[np.linspace(0, len(far) - 1, 20).astype(int)]
    warned = {w["region"] for w in reduction_warnings(screw, np.full(len(screw), 5.0), fit.reduction())}
    assert warned == {region.name}, warned
    assert not reduction_warnings(screw, np.full(len(screw), cg.MIRROR_FLOOR_MM["unit"] + 1.0), fit.reduction())
    _check_residual_contract(fit)


def test_an_impacted_fracture_with_no_mirror_is_not_restored_and_says_so(impacted, own_targets):
    """Both sides injured (2.4): there is no mirror to take the length lost
    to impaction from, so the region is unconstrained, with the reason, and
    the fit has no row across it that would hold the impaction as scanned."""
    phantom, vol, found, fit, *_ = _impacted_fit(impacted, own_targets, 4.0, None, injured="both")
    region = fit.regions[found.surfaces[0].region]
    print(region.sentence())
    assert np.isinf(region.residual_mm) and region.unconstrained.startswith("IMPACTION NOT RESTORED")
    assert "no mirror" in region.unconstrained
    _check_residual_contract(fit)


@pytest.mark.parametrize("start", ["exact", "wrong"])
def test_a_deeper_impaction_is_never_a_small_number(impacted, own_targets, start):
    """Driven in 6 mm: whatever the split and the fit make of it, every
    region lands within what it reports or reports inf with the reason, and
    the fracture is never missing from the regions."""
    phantom, vol, found, fit, truth, begin, truth_of = _impacted_fit(impacted, own_targets, 6.0, start)
    split = impacted[6.0][3]["right"]
    landing = _landing(fit, truth_of)
    _report(f"impacted 6 mm from the {start} start; {split.sentence()[:150]}", fit, landing)
    assert [s.source for s in found.surfaces] == [fsm.CT_IMPACTED], found.sentence()
    assert found.surfaces[0].region in fit.regions
    _check_lands_within(fit, landing)
    _check_residual_contract(fit)


# The surgeon's marks on the impacted phantom's fracture (x = 12 mm, in the
# band), as in test_fracture_surface.
SACRAL_MARKS = [[12.0, -45.0, 0.0], [12.0, -40.0, 20.0], [12.0, -48.0, 40.0], [12.0, -38.0, 10.0]]


def test_a_reduction_cut_along_the_surgeons_marks_never_reads_as_found(straight_confirmed, own_targets):
    """7d.1: where the CT shows nothing (the impacted phantom's CT with no
    band in it), the marked plane is the fracture surface and the sacrum is
    split along it, but it is never presented as found: the Reduction says
    so, every mark stays a region of unknown error (inf), and a screw
    crossing the marks surface anywhere, as reduced, is warned however much
    room it has. The reduction is not accepted."""
    phantom = impacted_sacral_pelvis(depth_mm=4.0, band_excess_hu=IMPACTED_BAND_HU)
    vol = _vol(phantom.labels, phantom)
    blind = Volume(pelvis_ct(phantom.labels, phantom.spacing, phantom.origin), phantom.spacing, phantom.origin)
    found = fsm.find_fracture_surfaces(vol, mirror=straight_confirmed, ct=blind, marks=[fit_plane(SACRAL_MARKS)],
                                       bones=(seg.SACRUM,), injured="right")
    assert [s.source for s in found.surfaces] == [fsm.SURGEON_MARKS], found.sentence()
    surface = found.surfaces[0]
    splits = fsm.split_sacrum(vol, found, straight_confirmed)
    sacral = phantom.sacral
    truth = np.linalg.inv(sacral.moved_by)
    hip = sacral.labels == seg.HIP_R
    begin = _wrong(vol.mask_voxel_centers_world(hip)) @ truth
    fit = cg.fit_reduction(vol, "right", found, _fragment_set("right", [_body(0, None, hip, begin)]), splits,
                           **own_targets)
    reduction = fit.reduction()
    _report(f"marked, not found; {splits['right'].sentence()[:120]}", fit,
            _landing(fit, _truth(vol, [(hip | sacral.lateral_fragment | (sacral.labels == seg.FEMUR_R), truth)])))
    assert reduction.accepted_by is None and reduction.notes[0] == cg.NOT_ACCEPTED
    assert any(fsm.MARKS_SURFACE_FLAG in n for n in reduction.notes), "the Reduction does not say it was not found"
    marked = [r for k, r in fit.regions.items() if k.startswith("fracture_mark_")]
    assert len(marked) == 1 and np.isinf(marked[0].residual_mm) and "surgeon marked a fracture" in marked[0].unconstrained
    # Every point of the marks surface's faces, where the fit puts it.
    points = []
    for face in surface.faces:
        unit = cg._unit_of(face.voxels, fit.units)
        for k in np.unique(unit):
            pose = np.eye(4) if k == cg.STATIC else fit.units[k].transform
            points.append(transform_points(pose, face.points[unit == k]))
    points = np.vstack(points)
    unknown = {k for k, r in reduction.residual_mm.items() if np.isinf(r)}
    near_unknown = np.zeros(len(points), dtype=bool)
    for k in unknown:
        near_unknown |= cKDTree(np.asarray(reduction.region_xyz[k]).reshape(-1, 3)).query(points)[0] <= REGION_RADIUS_MM
    print(f"marks surface {surface.id}: {int(near_unknown.sum())} of {len(points)} face points, as reduced, within "
          f"{REGION_RADIUS_MM:.0f} mm of a region of unknown error ({sorted(unknown)}); its own region: "
          f"{fit.regions[surface.region].sentence() if surface.region in fit.regions else 'none'}")
    assert near_unknown.all(), "a screw crossing the marks surface there is not warned as unknown"
    sample = points[np.linspace(0, len(points) - 1, 12).astype(int)]
    for p in sample:
        assert any(np.isinf(w["residual_mm"]) for w in reduction_warnings(p[None], np.full(1, 50.0), reduction))
    _check_residual_contract(fit)


def _with_impacted_rim(found, keep):
    """The same surfaces, each face keeping only its first ``keep`` rim
    points, with everything else (source, impaction depth) as found."""
    surfaces = []
    for s in found.surfaces:
        faces = []
        for f in s.faces:
            rim = np.zeros(len(f.rim), dtype=bool)
            rim[np.flatnonzero(f.rim)[:keep]] = True
            faces.append(dataclasses.replace(f, rim=rim))
        surfaces.append(dataclasses.replace(s, faces=tuple(faces)))
    return dataclasses.replace(found, surfaces=surfaces)


def _inf_cover(fit, vol, unit):
    """The share of a unit's voxels, as reduced, within Corridor Finder's
    warning radius of a region of unknown error (inf): where a screw is
    warned whatever its room."""
    reduction = fit.reduction()
    bone = transform_points(unit.transform, vol.mask_voxel_centers_world(unit.mask))
    near = np.zeros(len(bone), dtype=bool)
    for name, residual in reduction.residual_mm.items():
        if np.isinf(residual):
            near |= cKDTree(np.asarray(reduction.region_xyz[name]).reshape(-1, 3)).query(bone)[0] <= REGION_RADIUS_MM
    return float(near.mean())


@pytest.mark.parametrize("keep", [0, 5])
def test_an_impacted_fracture_its_rims_cannot_pin_is_unconstrained_and_the_mirror_pins_nothing(impacted, own_targets,
                                                                                               keep):
    """7d.6: "where the rims cannot pin it, inf". The 4 mm impacted fracture
    with its rims taken away (none left, or five per face): the length
    across it cannot be taken from the mirror, or too few rims are left to
    trust, so the fracture is inf with the reason, never a small number;
    no region that reports a number rests on the mirror, and there is no
    unit_<name>_on_mirror region, whose finite number would read the hip as
    known; and since nothing
    trustworthy pins the hip (the phantom's joints are flat), every voxel of
    it is within the warning radius of a region of unknown error."""
    phantom, vol, found, splits = impacted[4.0]
    starved = _with_impacted_rim(found, keep)
    surface = starved.surfaces[0]
    assert surface.source == fsm.CT_IMPACTED and surface.impaction_depth_mm == found.surfaces[0].impaction_depth_mm
    assert all(int(f.rim.sum()) <= keep for f in surface.faces)
    sacral = phantom.sacral
    truth = np.linalg.inv(sacral.moved_by)
    hip = sacral.labels == seg.HIP_R
    begin = _wrong(vol.mask_voxel_centers_world(hip)) @ truth
    fit = cg.fit_reduction(vol, "right", starved, _fragment_set("right", [_body(0, None, hip, begin)]), splits,
                           **own_targets)
    region = fit.regions[surface.region]
    cover = _inf_cover(fit, vol, fit.units[0])
    print(f"impacted 4 mm, {keep} rim points per face: {region.sentence()}; the hip within "
          f"{REGION_RADIUS_MM:.0f} mm of a region of unknown error: {100 * cover:.1f}%")
    assert np.isinf(region.residual_mm) and region.unconstrained, region.sentence()
    if keep == 0:
        assert region.unconstrained.startswith("IMPACTION NOT RESTORED") and "no rim pairs" in region.unconstrained
    # With five rim points left, the length across is still taken at the
    # mirror start, so the fracture's own notes say it rests on the mirror
    # (as the fit did) while it reads inf for too little rim; no region that
    # reports a number may lean on the mirror.
    leaning = [r.sentence() for r in fit.regions.values() if np.isfinite(r.floor_mm) and np.isfinite(r.residual_mm)]
    assert not leaning, leaning
    assert not any(k.endswith("_on_mirror") for k in fit.regions)
    assert cover == 1.0
    _check_residual_contract(fit)


def test_with_no_mirror_a_screw_anywhere_in_the_impacted_hip_is_warned(impacted, own_targets):
    """Both sides injured: the impacted fracture is not restored (inf), so
    its rows pin nothing; the phantom's flat joints pin nothing either. A
    screw anywhere in either hip, as the fit leaves it, is then within
    the warning radius of a region of unknown error, whatever its room:
    never read as safe because the only surface near it was not trusted."""
    phantom, vol, found, fit, *_ = _impacted_fit(impacted, own_targets, 4.0, None, injured="both")
    assert np.isinf(fit.regions[found.surfaces[0].region].residual_mm)
    for unit in fit.units:
        cover = _inf_cover(fit, vol, unit)
        print(f"{unit.name}: {100 * cover:.1f}% of it within {REGION_RADIUS_MM:.0f} mm of a region of unknown error")
        assert cover == 1.0, unit.name
    assert not any(np.isfinite(r.floor_mm) and np.isfinite(r.residual_mm) for r in fit.regions.values())
    assert not any(k.endswith("_on_mirror") for k in fit.regions)
    _check_residual_contract(fit)
