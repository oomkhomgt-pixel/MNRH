import numpy as np
import pytest

from corridor_engine.edt import bone_edt_mm
from corridor_engine.structures import articular_clearance, articular_field, joint_space
from corridor_engine.validate import validate_screw
from corridor_engine.volume import Volume

HIP, FEMUR = 2, 5
SOCKET_BOTTOM = 55.0  # z of the deepest point of the socket


def _hip_with_socket():
    """A block of hip bone with a spherical socket in its top face and a
    femoral head sitting in it across a 3 mm joint space: the geometry that
    decides whether a screw may run just under the acetabulum."""
    n = 90
    zz, yy, xx = np.mgrid[0:n, 0:n, 0:n].astype(float)
    labels = np.zeros((n, n, n), dtype=np.uint8)
    # Clear of the array's edge on every side: a distance transform does not
    # treat the edge as a surface.
    block = (xx >= 5) & (xx <= 80) & (yy >= 5) & (yy <= 80) & (zz >= 5) & (zz <= 80)
    socket = np.sqrt((xx - 40) ** 2 + (yy - 40) ** 2 + (zz - 80) ** 2)
    labels[block & (socket > 25)] = HIP
    labels[socket <= 22] = FEMUR
    return Volume(labels, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0))


def _fields(margin=2.0):
    vol = _hip_with_socket()
    bone = vol.array == HIP
    plain = Volume(bone_edt_mm(bone, vol.spacing), vol.spacing, vol.origin)
    joint = joint_space(vol.array, vol.spacing, HIP, FEMUR)
    return vol, plain, joint, articular_field(plain, bone, joint, margin)


def _screw_under_socket(field, depth_mm, margin=2.0):
    """A 3.5 mm screw along x whose surface passes ``depth_mm`` below the
    socket's floor (negative: into the joint)."""
    z = SOCKET_BOTTOM - 1.75 - depth_mm
    return validate_screw((2.0, 40.0, z), (70.0, 40.0, z), 3.5, margin, field, None, tip_rule="inside")


def test_the_joint_space_is_found_between_the_socket_and_the_head():
    vol, _, joint, _ = _fields()
    assert joint.any()
    zz, yy, xx = np.nonzero(joint)
    r = np.sqrt((xx - 40) ** 2 + (yy - 40) ** 2 + (zz - 80) ** 2)
    assert r.min() >= 21.0 and r.max() <= 26.0, "only the 3 mm shell between head and socket"
    assert not (vol.array[joint] != 0).any(), "and only empty space"


def test_a_screw_may_run_just_under_the_joint_surface():
    """0.5 mm from the articular surface: a breach under the plain rule,
    allowed under DECISIONS 7.9, since it touches nothing it may not."""
    _, plain, _, articular = _fields()
    assert _screw_under_socket(plain, 0.5).breach
    ok = _screw_under_socket(articular, 0.5)
    assert not ok.breach
    assert articular_clearance(plain, np.array([ok.worst_point_xyz]), 1.75) == pytest.approx(0.5, abs=0.6)


def test_a_screw_may_not_cross_into_the_joint():
    _, _, _, articular = _fields()
    assert _screw_under_socket(articular, -1.0).breach


def test_every_other_surface_keeps_the_full_margin():
    """Away from the joint the field is the plain one, and a screw 0.5 mm
    from the block's floor is a breach either way."""
    _, plain, joint, articular = _fields()
    far = np.zeros_like(joint)
    far[:25] = True  # nearer the block's floor (z = 5) than the socket (whose floor is at z = 55)
    inside = plain.array > 0
    assert np.allclose(articular.array[far & inside], plain.array[far & inside])
    z = 5.0 + 1.75 + 0.5
    floor = validate_screw((2.0, 40.0, z), (70.0, 40.0, z), 3.5, 2.0, articular, None, tip_rule="inside")
    assert floor.breach


def test_the_bone_ends_where_it_did():
    """Outside bone the field is untouched, so every cortex crossing found
    from it is where it was."""
    _, plain, _, articular = _fields()
    assert np.array_equal(articular.array > 0, plain.array > 0)


def test_without_a_femur_nothing_changes():
    vol = _hip_with_socket()
    vol.array[vol.array == FEMUR] = 0
    bone = vol.array == HIP
    plain = Volume(bone_edt_mm(bone, vol.spacing), vol.spacing, vol.origin)
    joint = joint_space(vol.array, vol.spacing, HIP, FEMUR)
    assert not joint.any()
    assert articular_field(plain, bone, joint, 2.0) is plain
