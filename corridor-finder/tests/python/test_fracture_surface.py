"""Fracture surfaces and the sacral split (displacement-finder slice 1b,
plan tests 7 and 8, and the vetoes, routes and seeds they stand on). All
on fractured_pelvis's synthetic pelvis, turned 6 degrees where the mirror
is used, so the two sides are not voxel-identical."""
import numpy as np
import pytest
from scipy import ndimage as ndi

from corridor_engine import fracture_surface as fsm
from corridor_engine import mirror
from corridor_engine import segmentation as seg
from corridor_engine.fracture import fit_plane
from corridor_engine.fragments import Fragment, FragmentSet
from corridor_engine.phantoms import fractured_pelvis, sacral_fractured_pelvis
from corridor_engine.register import transform_points
from corridor_engine.si_joint import facing
from corridor_engine.volume import Volume

YAW_DEG = 6.0
VOXEL_MM = 1.5  # the phantoms' spacing: nothing voxelised is claimed finer than this
CUT_POINT = (75.0, 0.0, 45.0)  # fractured_pelvis's default cut, patient frame
CUT_NORMAL = (0.2, 0.3, 1.0)
# Empty space within this of two different bones is their joint: half the
# widest joint space in the phantom (L5/S1, 10.5 mm centre to centre) plus
# a voxel.
JOINT_REACH_MM = 10.5 / 2.0 + VOXEL_MM
JOINTS = {
    "right SI joint": (seg.SACRUM, seg.HIP_R),
    "left SI joint": (seg.SACRUM, seg.HIP_L),
    "symphysis": (seg.HIP_R, seg.HIP_L),
    "right hip joint": (seg.HIP_R, seg.FEMUR_R),
    "left hip joint": (seg.HIP_L, seg.FEMUR_L),
    "L5/S1": (seg.LUMBAR, seg.SACRUM),
}


def _vol(phantom):
    return Volume(phantom.labels, phantom.spacing, phantom.origin)


def _confirmed(ref, sacrum_fractured=None):
    fractured = ref.sacrum_fractured_preselected if sacrum_fractured is None else sacrum_fractured
    return mirror.confirm(ref, sacrum_fractured=fractured)


def _yaw(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a), 0.0], [np.sin(a), np.cos(a), 0.0], [0.0, 0.0, 1.0]])


def _true_cut(yaw_deg=YAW_DEG):
    """fractured_pelvis's cut plane in world coordinates: a point, and the
    unit normal pointing into the fragment."""
    normal = np.asarray(CUT_NORMAL) / np.linalg.norm(CUT_NORMAL)
    return _yaw(yaw_deg) @ np.asarray(CUT_POINT), _yaw(yaw_deg) @ normal


def _in(vol, mask, points):
    idx = np.rint(vol.world_to_zyx_indices(points)).astype(int)
    return mask[tuple(idx)]


def _angle_deg(u, v):
    return float(np.degrees(np.arccos(np.clip(abs(u @ v) / np.linalg.norm(u) / np.linalg.norm(v), -1.0, 1.0))))


# The mirror plane is fitted to L5 and the sacrum only, which every phantom
# of one orientation shares (the sacral fracture phantom is confirmed to L5
# alone), so it is fitted once per orientation: each fit takes about 30 s.


@pytest.fixture(scope="module")
def turned_reference():
    phantom = fractured_pelvis(yaw_deg=YAW_DEG)
    vol = _vol(phantom)
    return phantom, vol, mirror.fit_reference(vol)


@pytest.fixture(scope="module")
def straight_reference():
    return mirror.fit_reference(_vol(fractured_pelvis()))


@pytest.fixture(scope="module")
def intact(turned_reference):
    phantom, vol, ref = turned_reference
    return phantom, vol, _confirmed(ref)


@pytest.fixture(scope="module")
def gapped(turned_reference):
    """A 5 mm move that opens the fracture into a slot."""
    phantom = fractured_pelvis(yaw_deg=YAW_DEG, translate_mm=(2.0, 1.5, 4.3))
    vol = _vol(phantom)
    confirmed = _confirmed(turned_reference[2])
    return phantom, vol, confirmed, fsm.find_fracture_surfaces(vol, mirror=confirmed)


def test_the_facing_helper_is_si_joints_test():
    a = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]).T  # components first
    b = np.array([[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [np.cos(np.radians(121)), np.sin(np.radians(121)), 0.0]]).T
    assert list(facing(a, b, np.ones(3), np.ones(3))) == [True, False, True]  # opposite, square, just past 120
    # Just short of 120 degrees is not facing: this pins the threshold, not only its side.
    short = np.array([[np.cos(np.radians(119)), np.sin(np.radians(119)), 0.0]]).T
    assert not facing(a[:, :1], short, np.ones(1), np.ones(1))[0]
    # Lengths scale the vectors: the same directions at other lengths give the same answer.
    assert facing(3.0 * a[:, :1], 0.5 * b[:, :1], np.array([3.0]), np.array([0.5]))[0]


# --------------------------------------------------------------------------
# Plan test 7: the facing test never sees a joint.


def _joint_regions(phantom):
    sx, sy, sz = phantom.spacing
    near = {lab: ndi.distance_transform_edt(phantom.labels != lab, sampling=(sz, sy, sx)) <= JOINT_REACH_MM
            for lab in {lab for pair in JOINTS.values() for lab in pair}}
    return {name: (phantom.labels == 0) & near[a] & near[b] for name, (a, b) in JOINTS.items()}


def test_no_slot_is_found_in_any_joint_of_the_intact_pelvis(intact):
    phantom, vol, confirmed = intact
    regions = _joint_regions(phantom)
    for name, region in regions.items():
        assert region.sum() > 50, f"the phantom has no {name} to test"
    for with_mirror in (None, confirmed):
        found = fsm.find_fracture_surfaces(vol, mirror=with_mirror)
        for bone, points in found.candidate_points.items():
            for name, region in regions.items():
                hits = int(_in(vol, region, points).sum()) if len(points) else 0
                assert hits == 0, f"{hits} slot voxels of the {bone} in the {name}"
        if with_mirror is not None:
            assert found.surfaces == [], [s.sentence() for s in found.surfaces]


def test_what_keeps_the_joints_out_is_the_label():
    """The same test with every bone given one label does see joints: the
    test above passes because the joints lie between different labels."""
    phantom = fractured_pelvis(yaw_deg=YAW_DEG)
    merged = np.where(phantom.labels > 0, seg.SACRUM, 0).astype(np.uint8)
    vol = Volume(merged, phantom.spacing, phantom.origin)
    points = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,)).candidate_points["sacrum"]
    regions = _joint_regions(phantom)
    seen = {name: int(_in(vol, region, points).sum()) for name, region in regions.items()}
    print("slot voxels in each joint once the labels are merged:", seen)
    for name in ("right SI joint", "left SI joint", "right hip joint", "left hip joint"):
        assert seen[name] > 0, f"merged labels should see the {name}"


# --------------------------------------------------------------------------
# The slot route on a displaced hemipelvis.


def test_a_gapped_fracture_is_found_where_it_was_cut(gapped):
    phantom, vol, _, found = gapped
    assert [s.label for s in found.surfaces] == [seg.HIP_R], found.sentence()
    surface = found.surfaces[0]
    assert surface.id == "hip_right_1" and surface.region == "fracture_hip_right_1"
    main, moved = sorted(surface.faces, key=lambda f: phantom.fragment[tuple(f.voxels.T)].mean())
    on_main = float(((phantom.labels == seg.HIP_R) & ~phantom.fragment)[tuple(main.voxels.T)].mean())
    on_fragment = float(phantom.fragment[tuple(moved.voxels.T)].mean())
    point, normal = _true_cut()
    off_main = np.abs((main.points - point) @ normal)
    off_moved = np.abs((transform_points(phantom.to_reference, moved.points) - point) @ normal)
    gap = float(np.array([2.0, 1.5, 4.3]) @ normal)
    tilt = _angle_deg(main.normals.mean(axis=0), normal)
    print(f"faces on their own side {on_main:.2f} / {on_fragment:.2f}; off the cut p90 {np.percentile(off_main, 90):.2f}"
          f" / {np.percentile(off_moved, 90):.2f} mm; normal {tilt:.1f} deg off; gap {surface.width_mm:.2f} mm "
          f"(true {gap:.2f}); rim {main.rim.sum()} / {len(main.points)} and {moved.rim.sum()} / {len(moved.points)}")
    assert on_main >= 0.9 and on_fragment >= 0.9
    assert np.percentile(off_main, 90) <= VOXEL_MM and np.percentile(off_moved, 90) <= VOXEL_MM
    assert main.normals.mean(axis=0) @ normal > 0  # the main body's face looks into the fragment
    assert tilt <= 10.0
    assert abs(surface.width_mm - gap) <= VOXEL_MM
    for face in surface.faces:
        assert 0 < face.rim.sum() < len(face.points)  # a band along the edge, not the whole face
        assert np.allclose(np.linalg.norm(face.normals, axis=1), 1.0)
        assert len(face.rim_points) == len(face.rim_normals) == face.rim.sum()


def test_missing_vetoes_are_said(gapped):
    _, vol, confirmed, with_both = gapped
    bare = fsm.find_fracture_surfaces(vol)
    assert not bare.twin_checked and not bare.cortex_checked
    assert any("mirror-twin veto not applied" in n for n in bare.flags())
    assert any("cortex contrast veto not applied" in n for n in bare.flags())
    assert with_both.twin_checked and not any("mirror-twin veto not applied" in n for n in with_both.flags())


def test_an_unconfirmed_mirror_or_a_ct_off_the_grid_is_refused(turned_reference, gapped):
    _, vol, _, _ = gapped
    with pytest.raises(mirror.ReferenceNotConfirmed):
        fsm.find_fracture_surfaces(vol, mirror=turned_reference[2])
    with pytest.raises(mirror.ReferenceNotConfirmed):
        fsm.split_sacrum(vol, fsm.find_fracture_surfaces(vol), turned_reference[2])
    with pytest.raises(ValueError):
        fsm.find_fracture_surfaces(vol, ct=Volume(np.zeros((4, 4, 4)), vol.spacing, vol.origin))


@pytest.mark.parametrize("label", [seg.LUMBAR, seg.FEMUR_R, seg.FEMUR_L])
def test_only_the_sacrum_and_the_hips_are_searched(gapped, label):
    _, vol, _, _ = gapped
    with pytest.raises(ValueError, match="sacrum and the hips"):
        fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R, label))


def test_no_surface_is_never_no_fracture(intact):
    _, vol, confirmed = intact
    found = fsm.find_fracture_surfaces(vol, mirror=confirmed)
    for name in ("sacrum", "right hip", "left hip"):
        assert any(f"no fracture surface found in the {name}" in n and "does not say" in n for n in found.notes)


# --------------------------------------------------------------------------
# The mirror twin, and the surgeon's marks overriding it.


def _carved(right=True, left=True, sacrum=False):
    """The untilted (exactly symmetric) pelvis with a 3 mm slab cut out of
    the upper ilium on each side asked for, and across the sacrum."""
    phantom = fractured_pelvis()
    labels = phantom.labels.copy()
    vol = Volume(labels, phantom.spacing, phantom.origin)
    x, y, z = (vol.zyx_indices_to_world(np.argwhere(np.ones(labels.shape, bool))).T.reshape((3,) + labels.shape))
    slab = (np.abs(z - 40.0) <= VOXEL_MM) & (y > -20.0) & (y < 10.0)
    for wanted, sign, hip in ((right, 1.0, seg.HIP_R), (left, -1.0, seg.HIP_L)):
        if wanted:
            labels[slab & (sign * x > 60.0) & (labels == hip)] = 0
    if sacrum:
        labels[(np.abs(z - 30.0) <= VOXEL_MM) & (labels == seg.SACRUM)] = 0
    return vol


@pytest.fixture(scope="module")
def carved_both(straight_reference):
    return _carved(right=True, left=True, sacrum=True), _confirmed(straight_reference)


def test_a_symmetric_slot_is_anatomy_and_a_one_sided_one_is_not(carved_both):
    vol, confirmed = carved_both
    bare = fsm.find_fracture_surfaces(vol)
    assert {s.label for s in bare.surfaces} >= {seg.HIP_R, seg.HIP_L}
    vetoed = fsm.find_fracture_surfaces(vol, mirror=confirmed)
    assert not any(s.label in (seg.HIP_R, seg.HIP_L) for s in vetoed.surfaces), vetoed.sentence()
    assert any("mirror twin" in r for p in vetoed.rejected if p.label == seg.HIP_R for r in p.reasons)
    one_sided = _carved(right=True, left=False)
    found = fsm.find_fracture_surfaces(one_sided, mirror=confirmed)
    assert [s.label for s in found.surfaces] == [seg.HIP_R], found.sentence()


def test_the_sacrums_own_mirror_image_is_not_a_twin(carved_both):
    """A transverse sacral fracture is symmetric by nature; it is not
    removed for matching itself."""
    vol, confirmed = carved_both
    found = fsm.find_fracture_surfaces(vol, mirror=confirmed)
    sacral = [s for s in found.surfaces if s.label == seg.SACRUM]
    print([s.sentence() for s in sacral], [p.reasons for p in found.rejected if p.label == seg.SACRUM])
    assert sacral, found.sentence()


def test_a_mark_keeps_a_slot_the_twin_veto_would_remove(carved_both):
    vol, confirmed = carved_both
    mark = fit_plane([[75.0, -10.0, 40.0], [85.0, 0.0, 40.0], [70.0, 5.0, 40.5], [88.0, -12.0, 39.5]])
    found = fsm.find_fracture_surfaces(vol, mirror=confirmed, marks=[mark])
    right = [s for s in found.surfaces if s.label == seg.HIP_R]
    assert right and not any(s.label == seg.HIP_L for s in found.surfaces)
    assert found.surfaces[0] in right  # the marked fracture first
    assert right[0].mark_distance_mm <= fsm.FAR_FROM_MARKS_MM and not right[0].far_from_marks
    assert any("kept although" in f and "surgeon marked" in f for f in right[0].flags)


def test_surfaces_are_listed_marked_first_then_largest_with_ids_in_that_order(carved_both):
    """No mirror, so every carved slot is a surface: the marked right slab
    first, then by area; ids count per bone in listing order."""
    vol, _ = carved_both
    mark = fit_plane([[75.0, -10.0, 40.0], [85.0, 0.0, 40.0], [70.0, 5.0, 40.5], [88.0, -12.0, 39.5]])
    found = fsm.find_fracture_surfaces(vol, marks=[mark])
    assert len(found.surfaces) >= 3, found.sentence()
    near = [not s.far_from_marks for s in found.surfaces]
    assert near[0] and found.surfaces[0].label == seg.HIP_R
    assert near == sorted(near, reverse=True), "a marked surface after an unmarked one"
    for group in (True, False):
        areas = [s.area_mm2 for s, n in zip(found.surfaces, near) if n == group]
        assert areas == sorted(areas, reverse=True)
    for label, key in fsm.BONE_KEYS.items():
        ids = [s.id for s in found.surfaces if s.label == label]
        assert ids == [f"{key}_{k}" for k in range(1, len(ids) + 1)]
    flagged = [line for line in found.flags() if line.startswith("fracture ")]
    assert len(flagged) == sum(len(s.flags) for s in found.surfaces)
    assert all(any(line.startswith(f"fracture {s.id}: ") for line in flagged) for s in found.surfaces if s.flags)


def _surface_at(distance):
    face = fsm.Face("a", seg.HIP_R, np.zeros((1, 3)), np.array([[1.0, 0.0, 0.0]]), np.zeros((1, 3), int),
                    np.zeros(1, bool))
    return fsm.FractureSurface("hip_right_1", seg.HIP_R, fsm.SLOT, (face, face), 1.0, 50.0, distance)


def test_far_from_marks_is_strictly_beyond_the_trusted_distance():
    assert not _surface_at(None).far_from_marks, "with no marks nothing is far from them"
    assert not _surface_at(fsm.FAR_FROM_MARKS_MM).far_from_marks
    assert _surface_at(fsm.FAR_FROM_MARKS_MM + 0.01).far_from_marks
    assert fsm.FAR_FROM_MARKS_MM == 20.0


def test_a_surface_far_from_every_mark_is_flagged(gapped):
    _, vol, confirmed, _ = gapped
    elsewhere = fit_plane([[-60.0, 40.0, -30.0], [-50.0, 45.0, -35.0], [-55.0, 35.0, -25.0]])
    found = fsm.find_fracture_surfaces(vol, mirror=confirmed, marks=[elsewhere])
    assert found.marks_given == 1
    surface = found.surfaces[0]
    assert surface.far_from_marks
    assert any("from every mark the surgeon placed" in f for f in found.flags())
    assert any("no fracture surface found within" in n for n in found.notes)
    # The mark itself is kept, so a reduction can say it knows nothing there.
    assert [m.plane is elsewhere for m in found.unmatched_marks] == [True]
    assert found.unmatched_marks[0].unmatched.all()
    unmarked = fsm.find_fracture_surfaces(vol, mirror=confirmed)
    assert unmarked.surfaces[0].mark_distance_mm is None and not unmarked.surfaces[0].far_from_marks
    assert unmarked.unmatched_marks == []


def _two_slabs_and_a_vertebra():
    """A right hip in two slabs with a 4 mm slot between them (centre to
    centre, faces at x = 27 and x = 31 mm), and a block of L5 4 mm past the
    slabs' edge, across the slot. 1 mm voxels, origin 0: index = mm."""
    labels = np.zeros((60, 60, 60), dtype=np.uint8)  # (z, y, x)
    labels[10:50, 10:50, 10:28] = seg.HIP_R
    labels[10:50, 10:50, 31:51] = seg.HIP_R
    labels[15:35, 53:58, 22:38] = seg.LUMBAR
    return Volume(labels, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0))


def test_each_mark_is_matched_on_its_own_bone_within_the_warning_radius():
    """A mark is matched only by a surface on the bone it lies on, with a
    face within MARK_MATCH_MM (Corridor Finder's warning radius) of that
    mark itself. Matched as a whole within 20 mm, each of these would have
    read as matched, and a reduction would have said nothing at the marks
    no surface lies near."""
    vol = _two_slabs_and_a_vertebra()
    assert fsm.MARK_MATCH_MM == fsm.REGION_RADIUS_MM == 10.0
    in_slot = [[29.0, 20.0, 20.0], [29.0, 40.0, 22.0], [29.0, 30.0, 40.0]]
    beside = fit_plane([[22.0, 20.0, 20.0], [22.0, 40.0, 25.0], [22.0, 30.0, 40.0]])  # 5 mm off the face
    one_end = fit_plane(in_slot + [[12.0, 30.0, 30.0]])  # its fourth mark 15 mm off the face
    on_l5 = fit_plane([[23.0, 55.0, 16.0], [37.0, 55.0, 18.0], [30.0, 55.0, 34.0]])  # 6-9 mm off the faces
    assert None not in (beside, one_end, on_l5)
    found = fsm.find_fracture_surfaces(vol, marks=[beside, one_end, on_l5], bones=(seg.HIP_R,))
    assert [s.label for s in found.surfaces] == [seg.HIP_R], found.sentence()
    print(found.notes)
    by_plane = {id(m.plane): m for m in found.unmatched_marks}
    assert id(beside) not in by_plane, "every mark within 5 mm of the surface on its own bone"
    partial = by_plane[id(one_end)]
    assert list(partial.unmatched) == [False, False, False, True]
    assert np.allclose(partial.points, [[12.0, 30.0, 30.0]])
    assert partial.nearest_mm[3] == pytest.approx(15.0, abs=1.0) and partial.bone[3] == seg.HIP_R
    assert fsm.MARK_MATCH_MM < partial.nearest_mm[3] <= fsm.FAR_FROM_MARKS_MM
    vertebra = by_plane[id(on_l5)]
    assert vertebra.unmatched.all() and set(vertebra.bone) == {seg.LUMBAR}
    assert np.all(np.isinf(vertebra.nearest_mm)), "no surface on L5, however near the hip's"
    assert all(seg.LUMBAR == vol.array[tuple(v)] for v in vertebra.bone_voxel)
    assert any("1 of the 4 marks" in n and "(12, 30, 30) on the right hip, nearest surface on it 15 mm" in n
               for n in found.notes), found.notes
    assert any("3 of the 3 marks" in n and "on the lumbar spine, no surface on it" in n for n in found.notes), \
        found.notes


# --------------------------------------------------------------------------
# Cortex contrast, with a CT.


def _synthetic_ct(phantom, faces_cortical):
    """HU on the phantom's grid: cortex (600) within the rind of each bone,
    cancellous (180) inside. With ``faces_cortical`` False the rind is the
    intact pelvis's, carried with the fragment, so the fracture faces are
    cancellous as in life; True paints the displaced bones' own rind, so
    the faces are cortex."""
    sx, sy, sz = phantom.spacing
    source = phantom.labels if faces_cortical else phantom.intact_labels
    rind = np.zeros(source.shape, dtype=bool)
    for lab in np.unique(source[source > 0]):
        bone = source == lab
        rind |= bone & (ndi.distance_transform_edt(bone, sampling=(sz, sy, sx)) <= fsm.CORTEX_RIND_MM)
    hu = np.where(phantom.labels > 0, 180.0, 0.0).astype(np.float32)
    if faces_cortical:
        hu[rind] = 600.0
        return hu
    hu[rind & (phantom.labels > 0) & ~phantom.fragment] = 600.0
    vol = _vol(phantom)
    frag = np.argwhere(phantom.fragment)
    home = np.rint(vol.world_to_zyx_indices(
        transform_points(phantom.to_reference, vol.zyx_indices_to_world(frag)))).astype(int)
    hu[tuple(frag.T)] = np.where(rind[tuple(home)], 600.0, 180.0)
    return hu


def test_a_cancellous_face_is_kept_and_a_cortical_one_is_anatomy(gapped):
    phantom, vol, confirmed, _ = gapped
    kept = fsm.find_fracture_surfaces(vol, mirror=confirmed,
                                      ct=Volume(_synthetic_ct(phantom, False), vol.spacing, vol.origin))
    assert kept.cortex_checked and [s.label for s in kept.surfaces] == [seg.HIP_R]
    assert not any("cortex contrast veto not applied" in n for n in kept.notes)
    vetoed = fsm.find_fracture_surfaces(vol, mirror=confirmed,
                                        ct=Volume(_synthetic_ct(phantom, True), vol.spacing, vol.origin))
    assert vetoed.surfaces == []
    reasons = [r for p in vetoed.rejected if p.label == seg.HIP_R for r in p.reasons]
    print(f"cortex {vetoed.cortex_hu}, reasons {reasons}")
    assert any("cortex, so anatomy" in r for r in reasons)


# --------------------------------------------------------------------------
# The zero-width route: slice 1's fragment boundary.


def _truth_fragments(phantom, unexplained=None):
    """A FragmentSet built from the phantom's own fragment, so the route is
    tested apart from how well slice 1 finds the mask."""
    main = (phantom.labels == seg.HIP_R) & ~phantom.fragment

    def body(index, parent, mask, home):
        return Fragment(index, parent, mask, float(mask.sum()) * VOXEL_MM ** 3 / 1000.0, home,
                        home if parent is not None else np.eye(4), 0.5, 0.0, 0.0, 0.5, False, False, int(mask.sum()))

    found = FragmentSet("right", "l5", "pre-selection",
                        [body(0, None, main, np.eye(4)), body(1, 0, phantom.fragment, phantom.to_reference)],
                        0.5, 1.5, 0.5)
    if unexplained is not None:
        found.unexplained = unexplained
        found.unexplained_cm3 = float(unexplained.sum()) * VOXEL_MM ** 3 / 1000.0
        found.unexplained_pieces = 1
    return found


@pytest.fixture(scope="module")
def slid():
    """The fragment slid 5 mm along its own fracture plane: the faces stay
    in contact, so there is no slot to see."""
    phantom = fractured_pelvis(yaw_deg=YAW_DEG, translate_mm=(0.0, 5.0, -1.5))
    return phantom, _vol(phantom)


def test_where_faces_touch_the_surface_is_the_fragment_boundary(slid):
    phantom, vol = slid
    alone = fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,))
    found = fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,), fragment_sets=[_truth_fragments(phantom)])
    route = [s for s in found.surfaces if s.id == "hip_right_fragment_1"]
    assert len(route) == 1, found.sentence()
    surface = route[0]
    assert surface.route.startswith(fsm.FRAGMENT_BOUNDARY) and surface.width_mm == 0.0
    fragment_face, main_face = surface.faces
    assert fragment_face.side == "right hip fragment 1" and main_face.side == "right hip main body"
    point, normal = _true_cut()
    off_main = np.abs((main_face.points - point) @ normal)
    off_fragment = np.abs((transform_points(phantom.to_reference, fragment_face.points) - point) @ normal)
    print(f"slot route alone: {alone.sentence()}; boundary off the cut p90 {np.percentile(off_main, 90):.2f} / "
          f"{np.percentile(off_fragment, 90):.2f} mm, rim {main_face.rim.sum()} / {len(main_face.points)}")
    assert np.percentile(off_main, 90) <= VOXEL_MM and np.percentile(off_fragment, 90) <= VOXEL_MM
    assert np.all(phantom.fragment[tuple(fragment_face.voxels.T)])
    assert main_face.rim.any() and not main_face.rim.all()
    assert any("slice 1's boundary" in f for f in surface.flags)


def test_a_refused_fragment_set_is_skipped(slid):
    """A refused slice 1 result has no trustworthy masks: no fragment
    boundary is made from it, even though it still lists the bodies."""
    phantom, vol = slid
    refused = _truth_fragments(phantom)
    refused.refused = "the mirror plane was not confirmed"
    found = fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,), fragment_sets=[refused])
    assert not any(fsm.FRAGMENT_BOUNDARY in s.route for s in found.surfaces), found.sentence()
    assert not any("fragment" in s.id for s in found.surfaces)


def test_a_slot_between_a_fragment_and_its_parent_joins_its_surface(gapped):
    phantom, vol, confirmed, _ = gapped
    found = fsm.find_fracture_surfaces(vol, mirror=confirmed, fragment_sets=[_truth_fragments(phantom)])
    assert [s.id for s in found.surfaces] == ["hip_right_fragment_1"], found.sentence()
    surface = found.surfaces[0]
    assert fsm.SLOT in surface.route
    assert np.mean(phantom.fragment[tuple(surface.faces[0].voxels.T)]) >= 0.9


def test_unexplained_bone_is_looked_in_but_never_a_surface(slid):
    phantom, vol = slid
    hip = phantom.labels == seg.HIP_R
    far_away = hip & (vol.zyx_indices_to_world(np.argwhere(np.ones(hip.shape, bool)))[:, 2] < -30.0).reshape(hip.shape)
    found = fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,), fragment_sets=[_truth_fragments(phantom, far_away)])
    assert any("carried home by no body" in n and "not taken as a surface by itself" in n for n in found.notes)
    assert all(s.id == "hip_right_fragment_1" for s in found.surfaces)
    at_the_fracture = ndi.binary_dilation(phantom.fragment, iterations=2) & hip & ~phantom.fragment
    found = fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,),
                                       fragment_sets=[_truth_fragments(phantom, at_the_fracture)])
    assert any("no body carries home" in f for f in found.surfaces[0].flags)


# --------------------------------------------------------------------------
# Plan test 8: the sacral split.


@pytest.fixture(scope="module", params=["right", "left"])
def sacral(request, straight_reference):
    phantom = sacral_fractured_pelvis(side=request.param)
    vol = _vol(phantom)
    confirmed = _confirmed(straight_reference, sacrum_fractured=True)
    found = fsm.find_fracture_surfaces(vol, mirror=confirmed)
    return phantom, vol, confirmed, found, fsm.split_sacrum(vol, found, confirmed)


def test_the_sacral_split_finds_the_lateral_fragment(sacral):
    phantom, vol, _, found, splits = sacral
    # The faces still touch at the hinge, so the label is one sacrum.
    assert ndi.label(phantom.labels == seg.SACRUM, structure=np.ones((3, 3, 3)))[1] == 1
    split = splits[phantom.side]
    assert not split.refused, split.refused
    truth = phantom.lateral_fragment
    recall = float((split.mask & truth).sum() / truth.sum())
    purity = float((split.mask & truth).sum() / split.mask.sum())
    print(f"{phantom.side}: recall {recall:.3f}, purity {purity:.3f}; {split.sentence()}")
    assert recall >= 0.9 and purity >= 0.9
    assert _angle_deg(split.plane_normal, phantom.cut_normal) <= 10.0
    assert split.plane_normal @ phantom.cut_normal > 0  # pointing lateral
    other = splits["left" if phantom.side == "right" else "right"]
    assert other.mask is None and "no split is guessed" in other.refused


def test_the_split_is_a_piece_of_the_sacrum_cut_along_its_own_surfaces(sacral):
    phantom, vol, _, found, splits = sacral
    split = splits[phantom.side]
    assert split.mask.shape == vol.array.shape and split.mask.dtype == bool
    assert np.all(vol.array[split.mask] == seg.SACRUM), "the split takes nothing but sacrum"
    assert split.volume_cm3 == pytest.approx(split.mask.sum() * VOXEL_MM ** 3 / 1000.0)
    assert split.volume_cm3 >= fsm.SPLIT_MIN_CM3
    assert np.linalg.norm(split.plane_normal) == pytest.approx(1.0)
    sacral_ids = {s.id for s in found.surfaces if s.label == seg.SACRUM}
    assert split.surface_ids and set(split.surface_ids) <= sacral_ids
    assert 0.0 <= split.slot_share <= 1.0
    # The central sacrum stays: the split is a part of it, not all of it.
    assert (vol.array == seg.SACRUM).sum() > 2 * split.mask.sum()


def test_every_split_says_it_is_unconfirmed(sacral):
    phantom, *_, splits = sacral
    split = splits[phantom.side]
    assert not split.confirmed and split.confirmed_by is None
    assert "UNCONFIRMED" in split.sentence() and fsm.SPLIT_UNCONFIRMED in split.notes
    confirmed = fsm.confirm_split(split, "surgeon, review sheet 2026-10-03")
    assert confirmed.confirmed and "UNCONFIRMED" not in confirmed.sentence()
    assert fsm.SPLIT_UNCONFIRMED not in confirmed.notes
    assert not split.confirmed  # the proposal itself is unchanged
    with pytest.raises(ValueError):
        fsm.confirm_split(split, "")
    with pytest.raises(ValueError):
        fsm.confirm_split(splits["left" if phantom.side == "right" else "right"], "surgeon")


def test_with_no_sacral_fracture_no_split_is_guessed(intact):
    _, vol, confirmed = intact
    splits = fsm.split_sacrum(vol, fsm.find_fracture_surfaces(vol, mirror=confirmed), confirmed)
    assert set(splits) == {"right", "left"}
    for split in splits.values():
        assert split.mask is None and "no split is guessed" in split.refused
        assert "no split" in split.sentence()


def _transverse(left_end_mm=-10.0):
    """The untilted pelvis with a 3 mm transverse slot across the sacrum at
    z = 30 mm, from ``left_end_mm`` rightward: its centroid lies right of the
    midline, so split_sacrum takes it for a right sacral fracture."""
    phantom = fractured_pelvis()
    labels = phantom.labels.copy()
    vol = Volume(labels, phantom.spacing, phantom.origin)
    x, _, z = vol.zyx_indices_to_world(np.argwhere(np.ones(labels.shape, bool))).T.reshape((3,) + labels.shape)
    labels[(np.abs(z - 30.0) <= VOXEL_MM) & (x > left_end_mm) & (labels == seg.SACRUM)] = 0
    return vol


def test_a_transverse_sacral_fracture_is_never_split_as_a_lateral_fragment(monkeypatch):
    """Cut along a transverse fracture, the "lateral" piece is the whole
    sacrum above it, both alae and both SI joints. Each of the three checks
    refuses it on its own: the plane is not lateral, the piece reaches past
    the midline, and it comes within AURICULAR_MAX_MM of the other hip."""
    vol = _transverse()
    found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
    assert [s.label for s in found.surfaces] == [seg.SACRUM], found.sentence()
    assert np.vstack([f.points for f in found.surfaces[0].faces]).mean(axis=0)[0] > 0
    expected = [({}, "not lateral"),
                ({"SPLIT_MIN_LATERAL_COS": -1.0}, "past the midline"),
                ({"SPLIT_MIN_LATERAL_COS": -1.0, "SPLIT_MIDLINE_MM": np.inf}, "would carry the left SI joint")]
    for patch, why in expected:
        with monkeypatch.context() as m:
            for name, value in patch.items():
                m.setattr(fsm, name, value)
            split = fsm.split_sacrum(vol, found)["right"]
        print(f"{patch}: {split.refused}")
        assert split.mask is None and why in split.refused and "no split is guessed" in split.refused


def test_two_splits_sharing_bone_are_both_refused(monkeypatch):
    """Both sides' pieces claiming one voxel would move it twice, once with
    each hip: neither is a lateral fragment. Here each side is handed the
    same real piece."""
    phantom = sacral_fractured_pelvis(side="right")
    vol = _vol(phantom)
    found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
    right = fsm.split_sacrum(vol, found)["right"]
    assert not right.refused, right.refused
    # A surface on each side, so that split_sacrum asks for both.
    mirrored = fsm.replace(found.surfaces[0], id="sacrum_left", faces=tuple(
        fsm.replace(f, points=f.points * np.array([-1.0, 1.0, 1.0])) for f in found.surfaces[0].faces))
    both = fsm.replace(found, surfaces=[found.surfaces[0], mirrored])
    monkeypatch.setattr(fsm, "_split_one", lambda labels_vol, side, *rest: fsm.replace(right, side=side))
    splits = fsm.split_sacrum(vol, both)
    for side in ("right", "left"):
        assert splits[side].mask is None and "shares" in splits[side].refused, splits[side].refused
