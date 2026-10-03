import numpy as np
import pytest

from corridor_engine.reduction import Move, Reduction, apply_moves, reduction_warnings, warning_text
from corridor_engine.volume import Volume

SACRUM, HIP = 1, 2


def _pelvis_with_a_gap(shift_mm=6):
    """A 'sacrum' block and a 'hip' block beside it, the hip displaced
    shift_mm laterally (along +x) from where it belongs (touching at x=30)."""
    labels = np.zeros((40, 40, 80), dtype=np.uint8)
    labels[10:30, 10:30, 10:30] = SACRUM
    labels[10:30, 10:30, 30 + shift_mm:50 + shift_mm] = HIP
    return Volume(labels, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0))


def _shift(dx):
    t = np.eye(4)
    t[0, 3] = dx
    return t


def test_moving_the_hip_back_closes_the_gap_and_leaves_nothing_behind():
    vol = _pelvis_with_a_gap(6)
    moved, overlap = apply_moves(vol, [Move("hip_right", vol.array == HIP, _shift(-6.0))])
    expected = _pelvis_with_a_gap(0).array
    assert np.array_equal(moved.array, expected)
    assert overlap == {"hip_right": 0}
    assert (vol.array == HIP).sum() == (moved.array == HIP).sum(), "a rigid move keeps the bone's size"


def test_a_rotation_keeps_the_bone_whole():
    vol = _pelvis_with_a_gap(6)
    a = np.deg2rad(10.0)
    rot = np.eye(4)
    rot[:3, :3] = [[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]]
    centre = np.array([45.5, 19.5, 19.5])
    rot[:3, 3] = centre - rot[:3, :3] @ centre
    moved, _ = apply_moves(vol, [Move("hip_right", vol.array == HIP, rot)])
    before, after = (vol.array == HIP).sum(), (moved.array == HIP).sum()
    assert abs(after - before) / before < 0.03
    assert (moved.array == SACRUM).sum() == (vol.array == SACRUM).sum()


def test_overshooting_into_the_sacrum_is_counted():
    vol = _pelvis_with_a_gap(6)
    _, overlap = apply_moves(vol, [Move("hip_right", vol.array == HIP, _shift(-9.0))])
    assert overlap["hip_right"] == 3 * 20 * 20


def test_only_rigid_moves_are_accepted():
    vol = _pelvis_with_a_gap(6)
    stretch = np.diag([1.1, 1.0, 1.0, 1.0])
    with pytest.raises(ValueError, match="rigid"):
        Move("hip_right", vol.array == HIP, stretch)


def _reduction(residual):
    return Reduction(moves=[], residual_mm={"si_right": residual, "symphysis": 9.0},
                     region_xyz={"si_right": (30.0, 20.0, 20.0), "symphysis": (200.0, 0.0, 0.0)})


def test_a_screw_with_less_to_spare_than_the_reduction_error_is_warned_about():
    """DECISIONS 3.6: shown, with an amber warning, where its fit depends on
    the reduction; not refused."""
    points = np.array([[x, 20.0, 20.0] for x in range(0, 61, 5)], dtype=float)
    spare = np.full(len(points), 3.0)
    spare[6] = 1.5  # tightest right at the joint
    warnings = reduction_warnings(points, spare, _reduction(4.7))
    assert [w["region"] for w in warnings] == ["si_right"]
    assert warnings[0]["spare_mm"] == pytest.approx(1.5)
    assert "4.7 mm" in warning_text(warnings[0]) and "1.5 mm to spare" in warning_text(warnings[0])


def test_no_warning_when_the_screw_has_room_or_is_far_from_the_region():
    points = np.array([[x, 20.0, 20.0] for x in range(0, 61, 5)], dtype=float)
    assert reduction_warnings(points, np.full(len(points), 6.0), _reduction(4.7)) == []
    # The symphysis is uncertain by 9 mm, but this screw is nowhere near it.
    assert all(w["region"] != "symphysis"
               for w in reduction_warnings(points, np.full(len(points), 0.5), _reduction(0.1)))


def test_a_region_is_its_surface_not_its_centre():
    """A long joint: the screw crosses one end of it, far from its centre."""
    joint = np.array([[30.0, 20.0, z] for z in np.arange(-40.0, 41.0, 2.0)])
    r = Reduction(moves=[], residual_mm={"si_right": 4.7}, region_xyz={"si_right": joint})
    points = np.array([[x, 20.0, 35.0] for x in range(0, 61, 2)], dtype=float)
    assert np.linalg.norm(points - joint.mean(axis=0), axis=1).min() > 30.0
    assert [w["region"] for w in reduction_warnings(points, np.full(len(points), 1.0), r)] == ["si_right"]
    assert len(Reduction(moves=[], residual_mm={"x": 1.0}, region_xyz={"x": np.zeros((5000, 3))}).record()["region_xyz"]["x"]) == 200


def test_the_record_keeps_what_redoes_the_reduction():
    vol = _pelvis_with_a_gap(6)
    r = Reduction(moves=[Move("hip_right", vol.array == HIP, _shift(-6.0))], residual_mm={"si_right": 1.2},
                  region_xyz={"si_right": (30, 20, 20)}, source="test")
    rec = r.record()
    assert rec["units"][0]["transform"][0][3] == -6.0 and rec["units"][0]["voxels"] == 20 * 20 * 20
    assert rec["residual_mm"] == {"si_right": 1.2}
    assert rec["accepted_by"] is None, "not accepted unless someone accepted it"


def test_an_unconstrained_region_always_warns():
    """The displacement engine gives inf where too little surface pins the
    reduction down: never safe, however much room the screw has."""
    r = Reduction(moves=[], residual_mm={"si_right": float("inf")}, region_xyz={"si_right": (30.0, 20.0, 20.0)},
                  notes=["si_right: unconstrained"])
    points = np.array([[x, 20.0, 20.0] for x in range(0, 61, 5)], dtype=float)
    found = reduction_warnings(points, np.full(len(points), 50.0), r)
    assert [w["region"] for w in found] == ["si_right"]
    assert "not pinned down" in warning_text(found[0])
    rec = r.record()
    assert rec["residual_mm"] == {"si_right": None} and rec["unconstrained"] == ["si_right"]


def test_a_region_missing_its_error_or_its_surface_is_refused():
    with pytest.raises(ValueError, match="both an error and a surface"):
        Reduction(moves=[], residual_mm={"si_right": 1.0, "symphysis": 2.0}, region_xyz={"si_right": (0, 0, 0)})
    with pytest.raises(ValueError, match="both an error and a surface"):
        Reduction(moves=[], residual_mm={}, region_xyz={"si_right": (0, 0, 0)})
    for bad in (float("nan"), -1.0, None):
        with pytest.raises(ValueError):
            Reduction(moves=[], residual_mm={"si_right": bad}, region_xyz={"si_right": (0, 0, 0)})


def test_the_displacement_engines_region_kinds_read_plainly():
    inf = float("inf")
    r = Reduction(moves=[], residual_mm={"unit_hip_right_unpinned": inf, "fracture_mark_2": inf},
                  region_xyz={"unit_hip_right_unpinned": np.zeros((3000, 3)), "fracture_mark_2": (0.0, 0.0, 0.0)})
    found = reduction_warnings(np.zeros((3, 3)), np.full(3, 9.0), r)
    texts = {w["region"]: warning_text(w) for w in found}
    assert "the hip right (nothing pins where it goes)" in texts["unit_hip_right_unpinned"]
    assert "marked fracture 2 (no fracture surface found there)" in texts["fracture_mark_2"]
    assert all("not pinned down" in t for t in texts.values())
    rec = r.record()
    assert rec["region_points"]["unit_hip_right_unpinned"] == 3000 and len(rec["region_xyz"]["unit_hip_right_unpinned"]) == 200
