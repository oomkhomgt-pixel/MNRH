"""Fracture surfaces and the sacral split (displacement-finder slice 1b,
plan tests 7 and 8, and the vetoes, routes and seeds they stand on). All
on fractured_pelvis's synthetic pelvis, turned 6 degrees where the mirror
is used, so the two sides are not voxel-identical."""
import numpy as np
import pytest
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from corridor_engine import fracture_surface as fsm
from corridor_engine import mirror
from corridor_engine import segmentation as seg
from corridor_engine.fracture import fit_plane
from corridor_engine.fragments import Fragment, FragmentSet
from corridor_engine import phantoms as ph
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


# --------------------------------------------------------------------------
# Slice 1c (displacement-finder DECISIONS 7d.1, 7d.5): fractures found from
# the CT inside the bone label, and the surgeon's marks as the backup. On
# the synthetic CTs of phantoms.py: cortex, patchy cancellous bone, white
# noise and dense subchondral bone under every joint, thicker on the right.

DEPTH_TOLERANCE_MM = VOXEL_MM  # an impaction depth is a band's thickness on the grid: within one voxel
# A CT surface's faces are the first voxels either side of the line or band,
# stepped along one of the 13 grid directions (the line's) or its normal:
# off the true face by up to one such step, at most a voxel's diagonal.
NEXT_VOXEL_MM = float(np.sqrt(3.0)) * VOXEL_MM
# The impacted phantom's band is given twice the margin: a test of finding a
# band denser than the margin, not a claim about how dense a real one is
# (the two fragments' bone laid one on the other, its default, is fainter).
BAND_EXCESS_HU = 2.0 * fsm.IMPACTION_MARGIN_HU
SACRAL_MARKS = [[12.0, -45.0, 0.0], [12.0, -40.0, 20.0], [12.0, -48.0, 40.0], [12.0, -38.0, 10.0]]  # x = 12: the band


def _ct(phantom, ct=None):
    return Volume(phantom.ct if ct is None else ct, phantom.spacing, phantom.origin)


def _sources(found):
    return [(fsm.BONE_KEYS[s.label], s.source) for s in found.surfaces]


@pytest.fixture(scope="module")
def lucent(turned_reference):
    phantom = ph.lucent_fractured_pelvis(gap_mm=3.0, yaw_deg=YAW_DEG)
    vol = _vol(phantom)
    confirmed = _confirmed(turned_reference[2], sacrum_fractured=False)
    return phantom, vol, confirmed, fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=_ct(phantom), injured="right")


def test_a_gaping_fracture_the_label_is_painted_across_is_found_from_the_ct(lucent):
    """Plan test 1 (CLINIC_0060's label runs solid across a line the CT
    shows): no gap in the label, so slice 1b's route finds nothing; the CT
    route finds the lucent line and its broken cortex where it was cut."""
    phantom, vol, confirmed, found = lucent
    assert phantom.painted.sum() > 100, "the phantom's label is not painted across the fracture"
    bare = fsm.find_fracture_surfaces(vol, mirror=confirmed)
    assert bare.surfaces == [], bare.sentence()
    assert found.ct_checked and _sources(found) == [("hip_right", fsm.CT_LUCENT)], found.sentence()
    surface = found.surfaces[0]
    assert surface.route == fsm.LUCENT_LINE and surface.impaction_depth_mm is None
    fragment = phantom.fractured.fragment
    main, moved = sorted(surface.faces, key=lambda f: fragment[tuple(f.voxels.T)].mean())
    on_main = float(((vol.array == seg.HIP_R) & ~fragment & ~phantom.painted)[tuple(main.voxels.T)].mean())
    on_fragment = float(fragment[tuple(moved.voxels.T)].mean())
    point, normal = phantom.cut_point, phantom.cut_normal
    off_main = np.abs((main.points - point) @ normal)
    off_moved = np.abs((transform_points(phantom.fractured.to_reference, moved.points) - point) @ normal)
    tilt = _angle_deg(main.normals.mean(axis=0), normal)
    print(f"lucent line: {surface.area_mm2:.0f} mm2, faces on their own side {on_main:.2f} / {on_fragment:.2f}, off the "
          f"cut p90 {np.percentile(off_main, 90):.2f} / {np.percentile(off_moved, 90):.2f} mm, normal {tilt:.1f} deg off, "
          f"gap {surface.width_mm:.2f} mm (moved {phantom.gap_mm:.1f} mm), rim {main.rim.sum()} / {len(main.points)} and "
          f"{moved.rim.sum()} / {len(moved.points)}; {surface.flags[0]}")
    assert on_main >= 0.9 and on_fragment >= 0.9
    assert np.percentile(off_main, 90) <= NEXT_VOXEL_MM and np.percentile(off_moved, 90) <= NEXT_VOXEL_MM
    assert main.normals.mean(axis=0) @ normal > 0 and tilt <= 10.0
    assert abs(surface.width_mm - phantom.gap_mm) <= VOXEL_MM
    for face in surface.faces:
        assert 0 < face.rim.sum() < len(face.points)
    assert "a lucent line through the bone with a break in its cortex" in surface.flags[0]
    assert np.all(vol.array[tuple(surface.zone_voxels.T)] == seg.HIP_R), "the line is looked for inside the label"


@pytest.fixture(scope="module", params=[4.0, 6.0])
def impacted(request, straight_reference):
    phantom = ph.impacted_sacral_pelvis(depth_mm=request.param, band_excess_hu=BAND_EXCESS_HU)
    vol = _vol(phantom)
    confirmed = _confirmed(straight_reference, sacrum_fractured=True)
    return phantom, vol, confirmed, fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=_ct(phantom), injured="right")


def test_an_impacted_sacral_fracture_is_found_with_its_depth(impacted):
    """Plan test 2: the lateral fragment driven into the sacrum, so the
    label is one solid sacrum with no gap; the dense band is found as
    ct_impacted, compared with the mirrored side, and its depth is the
    phantom's overlap within DEPTH_TOLERANCE_MM."""
    phantom, vol, confirmed, found = impacted
    assert ndi.label(vol.array == seg.SACRUM, structure=np.ones((3, 3, 3)))[1] == 1
    assert fsm.find_fracture_surfaces(vol, mirror=confirmed).surfaces == []
    assert _sources(found) == [("sacrum", fsm.CT_IMPACTED)], found.sentence()
    surface = found.surfaces[0]
    assert surface.route == fsm.DENSE_BAND and surface.width_mm == 0.0
    assert found.density_reference == surface.density_reference == fsm.MIRROR_REFERENCE
    assert found.impaction_margin_hu == fsm.IMPACTION_MARGIN_HU
    zone = np.ravel_multi_index(surface.zone_voxels.T, vol.array.shape)
    band = np.ravel_multi_index(np.argwhere(phantom.band).T, vol.array.shape)
    in_band, band_found = float(np.isin(zone, band).mean()), float(np.isin(band, zone).mean())
    to_band = ndi.distance_transform_edt(~phantom.band, sampling=VOXEL_MM)[tuple(surface.zone_voxels.T)]
    beside = float(np.mean(to_band <= NEXT_VOXEL_MM))
    print(f"impacted {phantom.depth_mm:.1f} mm: depth read {surface.impaction_depth_mm:.2f} mm (error "
          f"{surface.impaction_depth_mm - phantom.depth_mm:+.2f}, tolerance {DEPTH_TOLERANCE_MM:.1f}); "
          f"{surface.excess_hu:.0f} HU denser than the mirror (median over the band); {100 * in_band:.0f}% of the zone "
          f"in the phantom's band and {100 * beside:.0f}% within a voxel of it, {100 * band_found:.0f}% of the band "
          f"found; {surface.area_mm2:.0f} mm2")
    assert abs(surface.impaction_depth_mm - phantom.depth_mm) <= DEPTH_TOLERANCE_MM
    assert surface.signed_gap_mm == pytest.approx(-surface.impaction_depth_mm)
    assert beside >= 0.95 and band_found >= 0.9
    medial, lateral = sorted(surface.faces, key=lambda f: f.points[:, 0].mean())
    cut_now = phantom.sacral.cut_point[0] - phantom.depth_mm  # the fragment's face, driven in
    assert medial.points[:, 0].mean() < cut_now and lateral.points[:, 0].mean() > phantom.sacral.cut_point[0]
    assert medial.normals.mean(axis=0)[0] > 0 > lateral.normals.mean(axis=0)[0], "each face looks at the other"
    assert f"impacted {surface.impaction_depth_mm:.1f} mm" in surface.sentence()


def test_an_impaction_no_denser_than_its_two_layers_of_bone_is_not_found_and_says_so(straight_reference):
    """The phantom's own band, the two fragments' bone laid one on the
    other, adds about 160 HU, under IMPACTION_MARGIN_HU: not found, and
    the result never reads as an intact sacrum. A limit of the margin,
    pinned so that it is seen."""
    phantom = ph.impacted_sacral_pelvis(depth_mm=4.0)
    vol = _vol(phantom)
    found = fsm.find_fracture_surfaces(vol, mirror=_confirmed(straight_reference, sacrum_fractured=True),
                                       ct=_ct(phantom), injured="right")
    print(found.sentence())
    assert not any(s.source == fsm.CT_IMPACTED for s in found.surfaces)
    assert any("no fracture surface found in the sacrum" in n and "does not say" in n
               and f"{fsm.IMPACTION_MARGIN_HU:.0f} HU denser" in n for n in found.notes)


def test_dense_subchondral_bone_is_never_read_as_a_fracture(intact):
    """Plan test 3: the intact pelvis with dense subchondral bone under
    every joint (SI joints, hip joints, symphysis, L5/S1), thicker on the
    right, gives no fracture, lucent or impacted, against the mirror or
    against its own nearby bone. That bone is dense enough to be looked at:
    against its own nearby bone it is examined, and removed because it is
    dense against one side only."""
    phantom = ph.intact_pelvis_with_ct(yaw_deg=YAW_DEG)
    _, vol, confirmed = intact
    assert np.array_equal(vol.array, phantom.labels)
    sx, sy, sz = phantom.spacing
    for name, (a, b) in JOINTS.items():
        bone = phantom.labels == a
        near = bone & (ndi.distance_transform_edt(phantom.labels != b, sampling=(sz, sy, sx)) <= 2.0 * JOINT_REACH_MM)
        depth = ndi.distance_transform_edt(bone, sampling=(sz, sy, sx))
        under = near & (depth > fsm.CORTEX_RIND_MM) & (depth <= 3.0)
        assert np.median(phantom.ct[under]) >= ph.CT_CANCELLOUS_HU + 150.0, f"no dense subchondral bone at the {name}"
    for with_mirror in (confirmed, None):
        found = fsm.find_fracture_surfaces(vol, mirror=with_mirror, ct=_ct(phantom),
                                           injured="right" if with_mirror is not None else None)
        examined = [p for p in found.rejected if p.source == fsm.CT_IMPACTED]
        print(f"{found.density_reference}: {found.sentence()[:60]}; dense bands examined and removed {len(examined)}, "
              f"lucent patches removed {sum(p.source == fsm.CT_LUCENT for p in found.rejected)}")
        assert found.ct_checked and found.surfaces == [], [s.sentence() for s in found.surfaces]
        if with_mirror is None:
            assert found.density_reference == fsm.NEARBY_REFERENCE
            assert examined and all(any("one side" in r for r in p.reasons) for p in examined)
            assert any("there is no confirmed mirror" in n for n in found.notes)


def test_the_marks_are_the_backup_only_where_the_ct_finds_nothing(straight_reference):
    """Plan test 4. With the CT blinded (the CT of the same labels with no
    band in it) the plane through the marks becomes the surface, source
    surgeon_marks, flagged as not found, and its marks stay unmatched. With
    the band in the CT the marks only seed: the band is the surface and no
    marks surface is added."""
    phantom = ph.impacted_sacral_pelvis(depth_mm=4.0, band_excess_hu=BAND_EXCESS_HU)
    vol = _vol(phantom)
    confirmed = _confirmed(straight_reference, sacrum_fractured=True)
    marks = [fit_plane(SACRAL_MARKS)]
    assert np.all(vol.array[tuple(np.rint(vol.world_to_zyx_indices(np.array(SACRAL_MARKS))).astype(int))] == seg.SACRUM)
    blind = fsm.find_fracture_surfaces(vol, mirror=confirmed, marks=marks, injured="right",
                                       ct=_ct(phantom, ph.pelvis_ct(phantom.labels, phantom.spacing, phantom.origin)))
    assert _sources(blind) == [("sacrum", fsm.SURGEON_MARKS)], blind.sentence()
    backup = blind.surfaces[0]
    assert backup.route == fsm.MARKED_PLANE and fsm.MARKS_SURFACE_FLAG in backup.flags
    assert not np.isfinite(backup.width_mm) and backup.impaction_depth_mm is None
    cut = vol.zyx_indices_to_world(backup.zone_voxels)
    assert np.abs((cut - marks[0].point) @ marks[0].normal).max() <= VOXEL_MM / 2.0 + 1e-6
    assert cKDTree(marks[0].marks).query(cut)[0].max() <= fsm.NEAR_MARKS_MM
    assert np.all(vol.array[tuple(backup.zone_voxels.T)] == seg.SACRUM)
    assert [m.unmatched.all() for m in blind.unmatched_marks] == [True], "a marks surface is not a surface found"
    assert any("no fracture surface found in the sacrum" in n for n in blind.notes)
    seeded = fsm.find_fracture_surfaces(vol, mirror=confirmed, marks=marks, ct=_ct(phantom), injured="right")
    assert _sources(seeded) == [("sacrum", fsm.CT_IMPACTED)], seeded.sentence()
    assert seeded.unmatched_marks == [] and not seeded.surfaces[0].far_from_marks
    print(f"blinded: {backup.sentence()[:110]}...; seeded: {seeded.surfaces[0].sentence()[:110]}...")


def test_the_sacral_split_works_from_every_source(straight_reference):
    """7c.5 from the CT and the marks: the lateral fragment is cut off along
    a lucent line the label is painted across, along a dense band (the band
    is bone of both fragments: recall is over the fragment outside it), and
    along the surgeon's marked plane, where the split says it rests on his
    marks and counts none of the cut as found."""
    confirmed = _confirmed(straight_reference, sacrum_fractured=True)
    painted_sacrum = ph.lucent_sacral_pelvis(side="left", gap_mm=3.0)
    impacted = ph.impacted_sacral_pelvis(depth_mm=4.0, band_excess_hu=BAND_EXCESS_HU)
    blinded = ph.pelvis_ct(impacted.labels, impacted.spacing, impacted.origin)
    nothing = np.zeros(impacted.labels.shape, dtype=bool)
    outside_band = impacted.sacral.lateral_fragment & ~impacted.band
    cases = [(fsm.CT_LUCENT, painted_sacrum, painted_sacrum.ct, None, painted_sacrum.sacral.lateral_fragment,
              painted_sacrum.painted),
             (fsm.CT_IMPACTED, impacted, impacted.ct, None, outside_band, nothing),
             (fsm.SURGEON_MARKS, impacted, blinded, [fit_plane(SACRAL_MARKS)], outside_band, nothing)]
    for source, phantom, ct, marks, truth, painted in cases:
        vol = _vol(phantom)
        found = fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=_ct(phantom, ct), marks=marks, injured=phantom.side)
        assert _sources(found) == [("sacrum", source)], found.sentence()
        split = fsm.split_sacrum(vol, found, confirmed)[phantom.side]
        assert not split.refused, split.refused
        whole = phantom.sacral.lateral_fragment
        recall = float((split.mask & truth).sum() / truth.sum())
        purity = float((split.mask & whole).sum() / (split.mask & ~painted).sum())
        print(f"{source}: recall {recall:.3f}, purity {purity:.3f} (painted voxels left out); {split.sentence()[:120]}")
        assert recall >= 0.9 and purity >= 0.9
        assert split.plane_normal @ phantom.sacral.cut_normal > 0
        assert _angle_deg(split.plane_normal, phantom.sacral.cut_normal) <= 10.0
        if source == fsm.SURGEON_MARKS:
            assert split.slot_share == 0.0 and any("surgeon's marks" in n for n in split.notes)
        else:
            assert split.slot_share > 0.0 and not any("surgeon's marks" in n for n in split.notes)


# --------------------------------------------------------------------------
# Slice 1c, what the tests above leave open: arguments, the reference a band
# is compared with, sclerosis dense enough to be looked at against the
# mirror, and the marks with no CT.


def test_an_injured_side_that_is_not_right_left_or_both_is_refused(intact):
    _, vol, confirmed = intact
    for wrong in ("Right", "bilateral", "", 1):
        with pytest.raises(ValueError, match="injured must be"):
            fsm.find_fracture_surfaces(vol, mirror=confirmed, injured=wrong)


# Asymmetric subchondral sclerosis at every joint: denser and twice as deep
# on the right as the phantom's default, 3 mm on the left, so the right
# side's dense bone reaches the interior that is compared
# (IMPACTION_INTERIOR_MM) and is denser than its mirrored place by more than
# the margin. The default phantom's subchondral bone fades out before that
# depth, so against the mirror nothing in it is even examined (its dense
# points are empty); this one is. Sclerosis of this kind (degenerative, or
# osteitis condensans ilii) is often one-sided.
SCLEROSIS_HU = 1000.0
SCLEROSIS_MM = (8.0, 3.0)
# Joints whose dense bone, in the bones searched, must be examined: the right
# SI joint from either bone, the right acetabular roof and the sacral
# promontory (L5/S1, the right half denser).
SCLEROSED = {"right SI joint, sacral side": (seg.SACRUM, seg.HIP_R),
             "right SI joint, iliac side": (seg.HIP_R, seg.SACRUM),
             "right acetabular roof": (seg.HIP_R, seg.FEMUR_R),
             "sacral promontory": (seg.SACRUM, seg.LUMBAR)}


def test_asymmetric_subchondral_sclerosis_denser_than_the_mirror_is_never_impaction(intact, monkeypatch):
    """7d.5 and plan test 3 where it bites: sclerosis under the right SI
    joint, the right acetabular roof and the promontory that is denser than
    the same place on the left by more than IMPACTION_MARGIN_HU, so the
    mirror comparison does not remove it. It is examined at every one of
    those joints (it is in the result's dense points), and never becomes a
    fracture surface, against the mirror, against nearby bone (no mirror),
    or with both sides injured; each dense patch examined is rejected with a
    reason."""
    _, vol, confirmed = intact
    monkeypatch.setattr(ph, "CT_SUBCHONDRAL_HU", SCLEROSIS_HU)
    monkeypatch.setattr(ph, "CT_SUBCHONDRAL_MM", SCLEROSIS_MM)
    labels = vol.array
    ct = Volume(ph.pelvis_ct(labels, vol.spacing, vol.origin), vol.spacing, vol.origin)
    sx, sy, sz = vol.spacing
    for with_mirror, injured, reference in ((confirmed, "right", fsm.MIRROR_REFERENCE),
                                            (None, None, fsm.NEARBY_REFERENCE),
                                            (confirmed, "both", fsm.NEARBY_REFERENCE)):
        found = fsm.find_fracture_surfaces(vol, mirror=with_mirror, ct=ct, injured=injured)
        examined = [p for p in found.rejected if p.source == fsm.CT_IMPACTED]
        counts = {}
        for name, (own, other) in SCLEROSED.items():
            dense = found.dense_points[fsm.BONE_KEYS[own]]
            at = np.rint(vol.world_to_zyx_indices(dense)).astype(int) if len(dense) else np.zeros((3, 0), int)
            to_joint = ndi.distance_transform_edt(labels != other, sampling=(sz, sy, sx))[tuple(at)]
            counts[name] = int(np.sum(to_joint <= 2.0 * JOINT_REACH_MM))
        print(f"{reference} (injured {injured}): dense voxels at each joint {counts}; {len(examined)} dense patches "
              f"examined and rejected: " + "; ".join(f"{fsm.BONE_KEYS[p.label]} {p.area_mm2:.0f} mm2 {p.reasons[0][:70]}"
                                                     for p in examined))
        assert found.density_reference == reference
        for name, n in counts.items():
            assert n > 0, f"the sclerosis at the {name} is not examined against the {reference}: the test is vacuous"
        assert examined and all(p.reasons for p in examined)
        assert found.surfaces == [], [s.sentence() for s in found.surfaces]


def test_symmetric_subchondral_sclerosis_is_removed_by_the_mirror_itself(intact, monkeypatch):
    """7d.5's reason for the mirror: subchondral bone dense in everyone is
    dense on the intact side too. Sclerosis as dense and as deep as above
    (1000 HU, 8 mm) under every joint, but the same on both sides: compared
    with the mirrored side not one voxel of any bone is denser than its
    reference by the margin, so nothing is even examined, whatever the vetoes
    after it would do. Compared with the patient's own nearby bone (no
    mirror) the same sclerosis is dense at every joint, which is what the
    mirror comparison is for, and the flanking veto has to remove it."""
    _, vol, confirmed = intact
    monkeypatch.setattr(ph, "CT_SUBCHONDRAL_HU", SCLEROSIS_HU)
    monkeypatch.setattr(ph, "CT_SUBCHONDRAL_MM", (SCLEROSIS_MM[0], SCLEROSIS_MM[0]))
    labels = vol.array
    ct = Volume(ph.pelvis_ct(labels, vol.spacing, vol.origin), vol.spacing, vol.origin)
    sx, sy, sz = vol.spacing
    against_mirror = fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=ct, injured="right")
    nearby = fsm.find_fracture_surfaces(vol, ct=ct)
    counts = {}
    for name, (own, other) in SCLEROSED.items():
        dense = nearby.dense_points[fsm.BONE_KEYS[own]]
        at = np.rint(vol.world_to_zyx_indices(dense)).astype(int) if len(dense) else np.zeros((3, 0), int)
        counts[name] = int(np.sum(ndi.distance_transform_edt(labels != other, sampling=(sz, sy, sx))[tuple(at)]
                                  <= 2.0 * JOINT_REACH_MM))
    print(f"symmetric sclerosis: dense voxels against the mirror "
          f"{ {k: len(v) for k, v in against_mirror.dense_points.items()} }, against nearby bone at each joint {counts}")
    assert against_mirror.density_reference == fsm.MIRROR_REFERENCE
    assert {k: len(v) for k, v in against_mirror.dense_points.items()} == {k: 0 for k in against_mirror.dense_points}
    assert not any(p.source == fsm.CT_IMPACTED for p in against_mirror.rejected)
    assert against_mirror.surfaces == [] and nearby.surfaces == [], (against_mirror.sentence(), nearby.sentence())
    assert nearby.density_reference == fsm.NEARBY_REFERENCE and all(n > 0 for n in counts.values()), counts


@pytest.mark.parametrize("depth", [4.0, 6.0])
def test_with_both_sides_injured_a_band_is_compared_with_nearby_bone_found_and_said(depth, straight_reference):
    """7d.5: with both sides injured the mirror is not used even when given;
    the band is compared with the patient's own cancellous bone nearby, is
    still found at the band with its depth within DEPTH_TOLERANCE_MM, and
    the result and the surface each say what it was compared with and why."""
    phantom = ph.impacted_sacral_pelvis(depth_mm=depth, band_excess_hu=BAND_EXCESS_HU)
    vol = _vol(phantom)
    found = fsm.find_fracture_surfaces(vol, mirror=_confirmed(straight_reference, sacrum_fractured=True),
                                       ct=_ct(phantom), injured="both")
    assert found.density_reference == fsm.NEARBY_REFERENCE
    assert any("because both sides are injured" in n for n in found.notes)
    assert _sources(found) == [("sacrum", fsm.CT_IMPACTED)], found.sentence()
    surface = found.surfaces[0]
    print(f"both injured, impacted {depth:.0f} mm: depth read {surface.impaction_depth_mm:.2f} mm, "
          f"{surface.excess_hu:.0f} HU denser than the {surface.density_reference}")
    assert surface.density_reference == fsm.NEARBY_REFERENCE
    assert any("compared with this patient's own bone nearby" in f for f in surface.flags)
    assert f"denser than the {fsm.NEARBY_REFERENCE}" in surface.sentence()
    assert abs(surface.impaction_depth_mm - depth) <= DEPTH_TOLERANCE_MM


# The band's zone is the band read from the CT, blurred by the smoothing up
# to a voxel past the phantom's own overlap, and carried on through the rind
# level with it; each face is the next voxel beyond the zone.
ZONE_REACH_MM = 2.0 * NEXT_VOXEL_MM
FACE_REACH_MM = 3.0 * NEXT_VOXEL_MM


@pytest.mark.parametrize("injured", ["right", "both"], ids=["mirror", "nearby"])
@pytest.mark.parametrize("depth", [4.0, 6.0])
def test_an_impacted_bands_zone_and_faces_never_stray_from_the_band(depth, injured, straight_reference):
    """The zone read as the band and the faces either side of it lie at the
    phantom's band, against the mirror and against nearby bone: a face voxel
    tens of millimetres from the fracture is rim the reduction would fit, and
    stray zone voxels on the bone's surface are what made the split refuse
    the 6 mm phantom (slice 1c part B). The face on each side lies on its own
    side of the band."""
    phantom = ph.impacted_sacral_pelvis(depth_mm=depth, band_excess_hu=BAND_EXCESS_HU)
    vol = _vol(phantom)
    found = fsm.find_fracture_surfaces(vol, mirror=_confirmed(straight_reference, sacrum_fractured=True),
                                       ct=_ct(phantom), injured=injured)
    assert _sources(found) == [("sacrum", fsm.CT_IMPACTED)], found.sentence()
    surface = found.surfaces[0]
    to_band = ndi.distance_transform_edt(~phantom.band, sampling=VOXEL_MM)
    zone = to_band[tuple(surface.zone_voxels.T)]
    faces = [to_band[tuple(f.voxels.T)] for f in surface.faces]
    print(f"impacted {depth:.0f} mm against the {found.density_reference}: zone {len(zone)} voxels, "
          f"{int((zone > ZONE_REACH_MM).sum())} further than {ZONE_REACH_MM:.1f} mm from the band (furthest "
          f"{zone.max():.1f} mm); faces " + ", ".join(
              f"{f.side} {int((d > FACE_REACH_MM).sum())} of {len(d)} further than {FACE_REACH_MM:.1f} mm (furthest "
              f"{d.max():.1f} mm, x {f.points[d > FACE_REACH_MM][:, 0].round(1).tolist()[:6]})"
              for f, d in zip(surface.faces, faces)))
    assert zone.max() <= ZONE_REACH_MM
    for d in faces:
        assert d.max() <= FACE_REACH_MM
    medial, lateral = sorted(surface.faces, key=lambda f: f.points[:, 0].mean())
    assert np.all(medial.points[:, 0] < phantom.sacral.cut_point[0])
    assert np.all(lateral.points[:, 0] > phantom.sacral.cut_point[0] - depth)


def test_without_a_ct_the_marks_stay_unmatched_and_are_never_made_a_surface(straight_reference):
    """7d.1's backup is for where the CT shows nothing; with no CT that is
    not known. The marks stay what slice 1b made them (every one unmatched,
    so a reduction keeps a region of unknown error there), no surface comes
    from them, and the notes say why."""
    phantom = ph.impacted_sacral_pelvis(depth_mm=4.0, band_excess_hu=BAND_EXCESS_HU)
    vol = _vol(phantom)
    found = fsm.find_fracture_surfaces(vol, mirror=_confirmed(straight_reference, sacrum_fractured=True),
                                       marks=[fit_plane(SACRAL_MARKS)], injured="right")
    assert not found.ct_checked and found.impaction_margin_hu is None
    assert found.surfaces == [], found.sentence()
    assert [m.unmatched.all() for m in found.unmatched_marks] == [True]
    assert any("not made a fracture surface" in n and "there is no CT" in n for n in found.notes)
    assert any("CT route not run" in n for n in found.notes)


def test_a_marks_surface_carries_its_not_found_flag_into_what_a_reduction_carries(straight_reference):
    """What a reduction carries (FractureSurfaces.flags) says, under the
    surface's id, that the marked plane is not a surface found; its gap is
    not a number (never 0, which would read as anatomically reduced), and it
    is not impacted."""
    phantom = ph.impacted_sacral_pelvis(depth_mm=4.0, band_excess_hu=BAND_EXCESS_HU)
    vol = _vol(phantom)
    blind = fsm.find_fracture_surfaces(vol, mirror=_confirmed(straight_reference, sacrum_fractured=True),
                                       marks=[fit_plane(SACRAL_MARKS)], injured="right",
                                       ct=_ct(phantom, ph.pelvis_ct(phantom.labels, phantom.spacing, phantom.origin)))
    assert _sources(blind) == [("sacrum", fsm.SURGEON_MARKS)], blind.sentence()
    surface = blind.surfaces[0]
    assert f"fracture {surface.id}: {fsm.MARKS_SURFACE_FLAG}" in blind.flags()
    assert np.isnan(surface.signed_gap_mm) and "gap not measured" in surface.sentence()
    assert surface.impaction_depth_mm is None and surface.density_reference is None and surface.excess_hu is None
    assert f"from {fsm.SURGEON_MARKS}" in surface.sentence()


def test_a_lucent_lines_signed_gap_is_its_width(lucent):
    """7d.4: one variable from impacted (negative) through gaping (positive);
    a lucent line gapes, so its signed gap is its width, positive."""
    surface = lucent[3].surfaces[0]
    assert surface.source == fsm.CT_LUCENT
    assert surface.signed_gap_mm == surface.width_mm > 0.0
    assert surface.density_reference is None and surface.excess_hu is None


# --------------------------------------------------------------------------
# Slice 1c: what the CT route must never read as a fracture. Each case is
# the intact pelvis's CT with one thing planted in the sacrum that is not a
# fracture, and each veto that removes it is pinned by the case it is for:
# without it, each of these was a fracture surface in an intact pelvis.


@pytest.fixture(scope="module")
def intact_ct(straight_reference):
    """The untilted intact pelvis, its mirror confirmed with the sacrum
    intact, its CT, and per sacrum voxel its depth under the bone's surface
    (mm) and its world x."""
    phantom = fractured_pelvis()
    vol = _vol(phantom)
    sx, sy, sz = phantom.spacing
    sacrum = phantom.labels == seg.SACRUM
    depth = ndi.distance_transform_edt(sacrum, sampling=(sz, sy, sx))
    x = phantom.origin[0] + np.arange(phantom.labels.shape[2]) * sx
    x = np.broadcast_to(x[None, None, :], phantom.labels.shape)
    return (vol, _confirmed(straight_reference, sacrum_fractured=False),
            ph.pelvis_ct(phantom.labels, phantom.spacing, phantom.origin), sacrum, depth, x)


def _planted(intact_ct, mask, hu=None, add=None):
    """The intact pelvis's fracture surfaces with ``mask`` set to ``hu`` (or
    raised by ``add``) in its CT, against the mirror; the CT route's
    rejected patches centred within 10 mm of the planted voxels' bounding
    box (a ring's centre is not near any of its voxels)."""
    vol, confirmed, ct, *_ = intact_ct
    ct = ct.copy()
    if hu is not None:
        ct[mask] = hu
    else:
        ct[mask] += add
    found = fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=Volume(ct, vol.spacing, vol.origin), injured="right")
    world = vol.zyx_indices_to_world(np.argwhere(mask))
    lo, hi = world.min(axis=0), world.max(axis=0)
    near = [p for p in found.rejected
            if p.source != fsm.GAP and np.linalg.norm(np.maximum(np.maximum(lo - p.centre, p.centre - hi), 0.0)) <= 10.0]
    print(f"{int(mask.sum())} voxels planted: {found.sentence()[:60]}; rejected there: "
          + "; ".join(f"{p.source} {p.area_mm2:.0f} mm2: {' / '.join(r[:50] for r in p.reasons)}" for p in near))
    return found, near


def test_a_lucency_inside_intact_bone_is_never_a_fracture(intact_ct):
    """A dark sheet wholly inside the sacrum (soft tissue HU at least 4.5 mm
    under its surface, a vessel channel or a cyst flattened by the slice),
    crossing no cortex: a fracture breaks the cortex, so this is examined as
    a lucent line and removed for having no break in the cortex."""
    _, _, _, sacrum, depth, x = intact_ct
    sheet = sacrum & (np.abs(x - 12.0) <= VOXEL_MM / 2.0) & (depth >= 4.5)
    found, near = _planted(intact_ct, sheet, hu=ph.CT_SOFT_TISSUE_HU)
    assert found.surfaces == [], [s.sentence() for s in found.surfaces]
    lucent = [p for p in near if p.label == seg.SACRUM and p.source == fsm.CT_LUCENT]
    assert lucent, "the planted lucency was never examined: the test is vacuous"
    assert all(any(r.startswith("no break in the cortex") for r in p.reasons) for p in lucent)
    read = cKDTree(found.lucent_points["sacrum"]).query(intact_ct[0].zyx_indices_to_world(np.argwhere(sheet)))[0]
    # Measured 76%: the sheet is two voxels thick, and part of it lies
    # within reach of the rind, where the interior is not compared.
    assert np.mean(read <= VOXEL_MM / 2.0) >= 0.5, "most of the sheet was not read as lucent"


def test_a_dark_line_in_the_cortex_only_is_never_a_fracture(intact_ct):
    """A dark line round the sacrum's cortex at one level with the bone
    beneath it untouched (a groove, or a cortex thinned to nothing): a
    fracture crosses the bone beneath its broken cortex, so this is removed
    as in the cortex only."""
    _, _, _, sacrum, depth, x = intact_ct
    strip = sacrum & (np.abs(x - 12.0) <= VOXEL_MM / 2.0) & (depth <= fsm.CORTEX_RIND_MM)
    found, near = _planted(intact_ct, strip, hu=ph.CT_SOFT_TISSUE_HU)
    assert found.surfaces == [], [s.sentence() for s in found.surfaces]
    lucent = [p for p in near if p.label == seg.SACRUM and p.source == fsm.CT_LUCENT]
    assert lucent, "the planted line was never examined: the test is vacuous"
    assert all(any(r.startswith("in the cortex only") for r in p.reasons) for p in lucent)


def test_a_bone_island_is_never_impaction(intact_ct):
    """A bone island (enostosis): an oval of dense bone 14 mm long and 3 mm
    in radius, its long axis toward the bone's surface so that it reaches
    the outer layers, 600 HU denser than its mirrored place, with bone of
    the usual density either side of it. It is examined as a dense band
    against the mirror and removed as a lump, not a band, and for nothing
    else: every other test an impaction must pass, it passes."""
    _, _, _, sacrum, depth, x = intact_ct
    vol = intact_ct[0]
    at = np.argwhere(sacrum & (np.abs(depth - 9.0) <= 0.5) & (np.abs(x + 18.0) <= 3.0))
    at = at[len(at) // 2]
    centre = vol.zyx_indices_to_world(at[None])[0]
    deeper = np.array([np.gradient(depth, axis=k)[tuple(at)] for k in range(3)])[::-1]
    deeper /= np.linalg.norm(deeper)
    idx = np.argwhere(sacrum)
    rel = vol.zyx_indices_to_world(idx) - centre
    along = rel @ deeper
    across = np.linalg.norm(rel - along[:, None] * deeper, axis=1)
    island = np.zeros(sacrum.shape, dtype=bool)
    island[tuple(idx[(np.abs(along) <= 7.0) & (across <= 3.0)].T)] = True
    assert depth[island].min() <= fsm.IMPACTION_INTERIOR_MM, "the island does not reach the bone's outer layers"
    found, near = _planted(intact_ct, island, add=600.0)
    assert found.surfaces == [], [s.sentence() for s in found.surfaces]
    dense = [p for p in near if p.label == seg.SACRUM and p.source == fsm.CT_IMPACTED]
    assert dense, "the planted island was never examined as a dense band: the test is vacuous"
    for p in dense:
        assert len(p.reasons) == 1 and p.reasons[0].startswith("a lump, not a band"), p.reasons


def test_a_dense_sheet_wholly_inside_the_bone_is_never_impaction(intact_ct):
    """A dense sheet 3 mm thick, 400 HU denser than its mirrored place, with
    normal bone either side, but wholly inside the sacrum (at least 7 mm
    under its surface): an impacted fracture runs through the bone to its
    cortex, so this is removed as reaching none of its outer layers, and is
    otherwise a band like an impaction's (a sheet, flanked)."""
    _, _, _, sacrum, depth, x = intact_ct
    sheet = sacrum & (np.abs(x - 12.0) <= VOXEL_MM) & (depth >= 7.0)
    found, near = _planted(intact_ct, sheet, add=400.0)
    assert found.surfaces == [], [s.sentence() for s in found.surfaces]
    dense = [p for p in near if p.label == seg.SACRUM and p.source == fsm.CT_IMPACTED]
    assert dense, "the planted sheet was never examined as a dense band: the test is vacuous"
    for p in dense:
        assert len(p.reasons) == 1 and p.reasons[0].startswith("wholly inside the bone"), p.reasons


# --------------------------------------------------------------------------
# Slice 1c: the mirror twin on the CT route, marks matched in part, and the
# impacted fracture on the left (every impacted test above is on the right).


def _sheet(intact_ct, x_mm):
    """The sacrum's voxels within 1.5 mm of x = ``x_mm``: a sheet two voxels
    thick through the whole sacrum, cortex and interior."""
    _, _, _, sacrum, _, x = intact_ct
    return sacrum & (np.abs(x - x_mm) <= VOXEL_MM)


def _with_soft_tissue(intact_ct, mask):
    vol, _, ct, *_ = intact_ct
    ct = ct.copy()
    ct[mask] = ph.CT_SOFT_TISSUE_HU
    return Volume(ct, vol.spacing, vol.origin)


def _mean_x(surface):
    return float(np.vstack([f.points for f in surface.faces])[:, 0].mean())


def test_a_lucent_line_with_a_mirror_twin_is_anatomy_unless_the_surgeon_marked_it(intact_ct):
    """The mirror-twin veto on the CT route (7d.1 runs the same vetoes on a
    lucent line as on a slot). A lucent sheet through the right ala, cortex
    and bone beneath, is a fracture; the same sheet on both sides, each the
    other's mirror image, is anatomy (a symmetric channel), and each is
    removed for its twin on the other side, not for matching itself. A mark
    on the right one keeps it, flagged, and only it. Without a mirror the
    veto is not applied, so both are surfaces: the veto is what removes
    them. (A bilateral fracture this symmetric is removed the same way; the
    docstring says the marks are what override it.)"""
    vol, confirmed, *_ = intact_ct
    right, left = _sheet(intact_ct, 12.0), _sheet(intact_ct, -12.0)
    reflected = confirmed.plane.reflect(vol.zyx_indices_to_world(np.argwhere(right)))
    assert cKDTree(vol.zyx_indices_to_world(np.argwhere(left))).query(reflected)[0].max() <= VOXEL_MM, \
        "the two sheets are not each other's mirror image: the test is vacuous"
    one = fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=_with_soft_tissue(intact_ct, right), injured="right")
    assert _sources(one) == [("sacrum", fsm.CT_LUCENT)], one.sentence()
    assert _mean_x(one.surfaces[0]) > 0.0
    assert not any("kept although" in f for f in one.surfaces[0].flags)
    both_ct = _with_soft_tissue(intact_ct, right | left)
    both = fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=both_ct, injured="right")
    twins = [p for p in both.rejected if p.source == fsm.CT_LUCENT and p.label == seg.SACRUM
             and any("mirror twin" in r for r in p.reasons)]
    print(f"both sides: {both.sentence()[:60]}; removed as twins: "
          + "; ".join(f"x {p.centre[0]:.1f} mm, {p.area_mm2:.0f} mm2, {100 * p.twin_share:.0f}% twinned" for p in twins))
    assert both.surfaces == [], [s.sentence() for s in both.surfaces]
    assert sorted(np.sign(p.centre[0]) for p in twins) == [-1.0, 1.0], "each sheet is removed for its twin"
    assert all(p.twin_share > fsm.SYMMETRY_TWIN_FRACTION for p in twins)
    marks = [fit_plane(SACRAL_MARKS)]  # x = 12: on the right sheet, more than 20 mm from the left one
    marked = fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=both_ct, marks=marks, injured="right")
    assert _sources(marked) == [("sacrum", fsm.CT_LUCENT)], marked.sentence()
    kept = marked.surfaces[0]
    assert np.vstack([f.points for f in kept.faces])[:, 0].min() > 0.0, "the kept line is not the marked one"
    assert kept.mark_distance_mm <= fsm.FAR_FROM_MARKS_MM and not kept.far_from_marks
    assert any("kept although" in f and "surgeon marked a fracture" in f for f in kept.flags), kept.flags
    assert any(p.centre[0] < 0.0 and any("mirror twin" in r for r in p.reasons)
               for p in marked.rejected if p.source == fsm.CT_LUCENT), "the unmarked twin was kept too"
    assert marked.unmatched_marks == []
    bare = fsm.find_fracture_surfaces(vol, ct=both_ct)
    assert not bare.twin_checked and any("mirror-twin veto not applied" in n for n in bare.notes)
    assert sorted(np.sign(_mean_x(s)) for s in bare.surfaces if s.source == fsm.CT_LUCENT) == [-1.0, 1.0], \
        bare.sentence()


def test_a_transverse_lucent_line_in_the_sacrum_is_not_its_own_mirror_twin(intact_ct):
    """A transverse sacral fracture is symmetric by nature: a lucent sheet
    across the whole sacrum at one level, cortex and bone beneath, is its
    own mirror image. On the CT route, as on the slot route, the sacrum's
    own line does not count as its twin, so it is found against the mirror,
    with no mark to keep it."""
    vol, confirmed, *_ = intact_ct
    _, _, _, sacrum, _, _ = intact_ct
    z = vol.origin[2] + np.arange(vol.array.shape[0]) * vol.spacing[2]
    level = sacrum & (np.abs(z - 30.0) <= VOXEL_MM)[:, None, None]
    assert level.sum() > 100
    found = fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=_with_soft_tissue(intact_ct, level), injured="right")
    print(found.sentence()[:80], [p.reasons for p in found.rejected if p.source == fsm.CT_LUCENT])
    assert found.twin_checked
    sacral = [s for s in found.surfaces if s.label == seg.SACRUM and s.source == fsm.CT_LUCENT]
    assert sacral, found.sentence()
    assert not any("kept although" in f for s in sacral for f in s.flags)


def test_where_the_ct_finds_some_marks_the_marks_surface_is_made_from_the_others_only(straight_reference):
    """7d.1 mark by mark: two of a fracture's marks lie on the impacted
    band the CT finds, two on the intact left ala where it finds nothing.
    The band is the surface at the first two, which are matched; the plane
    through all four marks is the surface only near the other two (within
    NEAR_MARKS_MM of them, never out to the marks the CT already explains),
    flagged as not found, and those two stay unmatched, exactly. Built from
    every mark, its cut would run on to the band."""
    phantom = ph.impacted_sacral_pelvis(depth_mm=4.0, band_excess_hu=BAND_EXCESS_HU)
    vol = _vol(phantom)
    on_band, away = SACRAL_MARKS[:2], [[-12.0, -45.0, 0.0], [-12.0, -40.0, 20.0]]
    every = np.array(on_band + away)
    assert np.all(vol.array[tuple(np.rint(vol.world_to_zyx_indices(every)).astype(int))] == seg.SACRUM)
    plane = fit_plane(on_band + away)
    found = fsm.find_fracture_surfaces(vol, mirror=_confirmed(straight_reference, sacrum_fractured=True),
                                       ct=_ct(phantom), marks=[plane], injured="right")
    assert sorted(_sources(found)) == [("sacrum", fsm.CT_IMPACTED), ("sacrum", fsm.SURGEON_MARKS)], found.sentence()
    band = next(s for s in found.surfaces if s.source == fsm.CT_IMPACTED)
    backup = next(s for s in found.surfaces if s.source == fsm.SURGEON_MARKS)
    assert [list(m.unmatched) for m in found.unmatched_marks] == [[False, False, True, True]]
    cut = vol.zyx_indices_to_world(backup.zone_voxels)
    to_away, to_band_marks = cKDTree(away).query(cut)[0], cKDTree(on_band).query(cut)[0]
    print(f"marks surface: {len(cut)} cut voxels, x {cut[:, 0].min():.1f} to {cut[:, 0].max():.1f} mm, furthest from "
          f"the unmatched marks {to_away.max():.1f} mm, nearest the matched ones {to_band_marks.min():.1f} mm; "
          f"band {band.sentence()[:80]}")
    assert to_away.max() <= fsm.NEAR_MARKS_MM, "the marks surface reaches past the marks the CT found nothing at"
    assert np.abs((cut - plane.point) @ plane.normal).max() <= VOXEL_MM / 2.0 + 1e-6
    assert np.all(vol.array[tuple(backup.zone_voxels.T)] == seg.SACRUM)
    shape = vol.array.shape
    assert not np.isin(np.ravel_multi_index(backup.zone_voxels.T, shape),
                       np.ravel_multi_index(band.zone_voxels.T, shape)).any(), "the marks surface is cut through the band"
    assert fsm.MARKS_SURFACE_FLAG in backup.flags and fsm.MARKS_SURFACE_FLAG not in band.flags
    assert not band.far_from_marks
    assert any("nothing was found near 2 of its marks" in n for n in found.notes), found.notes


@pytest.mark.parametrize("depth", [4.0, 6.0])
def test_an_impacted_fracture_on_the_left_is_found_its_faces_named_and_split(depth, straight_reference):
    """Plan test 2 and 7c.5 on the left, so nothing that depends on the side
    (which way is lateral, which face is which, the split's direction) is
    right only on the right: found as ct_impacted against the mirror with
    its depth within DEPTH_TOLERANCE_MM and denser than its reference by
    the margin; the lateral face (so named) lies beyond the central sacrum's
    old face and the medial one beyond the fragment's driven-in face, each
    looking at the other, each with a cortical rim; the band read stays at
    the band; and the left lateral fragment is split off along it."""
    phantom = ph.impacted_sacral_pelvis(side="left", depth_mm=depth, band_excess_hu=BAND_EXCESS_HU)
    vol = _vol(phantom)
    confirmed = _confirmed(straight_reference, sacrum_fractured=True)
    found = fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=_ct(phantom), injured="left")
    assert _sources(found) == [("sacrum", fsm.CT_IMPACTED)], found.sentence()
    surface = found.surfaces[0]
    assert surface.density_reference == fsm.MIRROR_REFERENCE
    by_side = {f.side: f for f in surface.faces}
    assert set(by_side) == {"sacrum, lateral side", "sacrum, medial side"}, set(by_side)
    lateral, medial = by_side["sacrum, lateral side"], by_side["sacrum, medial side"]
    cut_x = phantom.sacral.cut_point[0]  # negative: the left ala
    to_band = ndi.distance_transform_edt(~phantom.band, sampling=VOXEL_MM)[tuple(surface.zone_voxels.T)]
    split = fsm.split_sacrum(vol, found, confirmed)["left"]
    print(f"left, impacted {depth:.0f} mm: depth read {surface.impaction_depth_mm:.2f} mm, {surface.excess_hu:.0f} HU "
          f"denser than the mirror; lateral face x {lateral.points[:, 0].mean():.2f}, medial "
          f"{medial.points[:, 0].mean():.2f} (cut {cut_x:.1f}, driven in to {cut_x + depth:.1f}); rims "
          f"{lateral.rim.sum()} / {medial.rim.sum()}; zone furthest from the band {to_band.max():.1f} mm; "
          f"{split.sentence()[:90]}")
    assert abs(surface.impaction_depth_mm - depth) <= DEPTH_TOLERANCE_MM
    assert surface.excess_hu >= fsm.IMPACTION_MARGIN_HU
    assert lateral.points[:, 0].mean() < cut_x and medial.points[:, 0].mean() > cut_x + depth
    assert lateral.normals.mean(axis=0)[0] > 0 > medial.normals.mean(axis=0)[0], "each face looks at the other"
    for face in (lateral, medial):
        assert 0 < face.rim.sum() < len(face.points)
    assert to_band.max() <= ZONE_REACH_MM
    assert not split.refused, split.refused
    truth = phantom.sacral.lateral_fragment & ~phantom.band
    recall = float((split.mask & truth).sum() / truth.sum())
    purity = float((split.mask & phantom.sacral.lateral_fragment).sum() / split.mask.sum())
    assert recall >= 0.9 and purity >= 0.9, (recall, purity)
    assert split.plane_normal @ phantom.sacral.cut_normal > 0 and split.plane_normal[0] < 0, "lateral is to the left"


# --------------------------------------------------------------------------
# DECISIONS 7e.2: probable disc remnants are flagged, never dropped.


def _plate(centre, normal, radius_mm=10.0, half_gap_mm=1.0, step_mm=1.5):
    """A thin synthetic fracture: two planar faces either side of a plane."""
    normal = np.asarray(normal, float) / np.linalg.norm(normal)
    helper = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(normal, helper)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(normal, e1)
    g = np.arange(-radius_mm, radius_mm + 1e-9, step_mm)
    u, v = np.meshgrid(g, g)
    disc = np.hypot(u, v) <= radius_mm
    flat = centre + u[disc][:, None] * e1 + v[disc][:, None] * e2
    faces = []
    for sign in (1.0, -1.0):
        pts = flat + sign * half_gap_mm * normal
        faces.append(fsm.Face("sacrum", seg.SACRUM, pts, np.tile(sign * normal, (len(pts), 1)),
                              np.zeros((len(pts), 3), dtype=np.int64), np.zeros(len(pts), dtype=bool)))
    return fsm.FractureSurface("sacrum_test", seg.SACRUM, fsm.SLOT, tuple(faces), 2.0, float(disc.sum() * step_mm ** 2),
                               None)


def _remnant_flagged(surface):
    return any(f.startswith("probable disc remnant") for f in surface.flags)


def test_a_transverse_plate_across_the_sacral_body_is_flagged_and_kept(intact):
    """A thin plate square to the S1-S2 line, between the two body centres:
    where a fused segment junction lies. It is flagged, and it is still
    there. The same plate 40 mm lateral (in the ala), or tilted 60 degrees
    off square, is not flagged."""
    from corridor_engine import landmarks as lm

    phantom, vol, _ = intact
    marks = lm.detect_landmarks(vol)
    s1 = np.asarray(marks["s1_body_center"].xyz, float)
    s2 = np.asarray(marks["s2_body_center"].xyz, float)
    axis = (s1 - s2) / np.linalg.norm(s1 - s2)
    centre = 0.5 * (s1 + s2)

    across = [_plate(centre, axis)]
    notes = []
    fsm._flag_disc_remnants(vol, across, notes)
    assert len(across) == 1 and _remnant_flagged(across[0]), (across[0].flags, notes)

    lateral = [_plate(centre + np.array([40.0, 0.0, 0.0]), axis)]
    fsm._flag_disc_remnants(vol, lateral, [])
    assert not _remnant_flagged(lateral[0])

    side = np.cross(axis, [0.0, 1.0, 0.0])
    side /= np.linalg.norm(side)
    tilted_normal = np.cos(np.radians(60.0)) * axis + np.sin(np.radians(60.0)) * side
    tilted = [_plate(centre, tilted_normal)]
    fsm._flag_disc_remnants(vol, tilted, [])
    assert not _remnant_flagged(tilted[0])


def test_a_lateral_sacral_fracture_is_not_flagged_as_a_disc_remnant(impacted):
    """The impacted phantom's fracture runs up and down through the ala, as
    the surgeon's lateral sacral fractures do: it is not a disc remnant."""
    _, _, _, found = impacted
    assert found.surfaces and not any(_remnant_flagged(s) for s in found.surfaces), [s.flags for s in found.surfaces]
