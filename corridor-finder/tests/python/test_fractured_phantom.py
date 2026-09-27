import numpy as np
import pytest
from scipy import ndimage as ndi

from corridor_engine import segmentation as seg
from corridor_engine.phantoms import fractured_pelvis
from corridor_engine.register import transform_points
from corridor_engine.volume import Volume

SWAP = {seg.HIP_L: seg.HIP_R, seg.HIP_R: seg.HIP_L, seg.FEMUR_L: seg.FEMUR_R, seg.FEMUR_R: seg.FEMUR_L}


def test_the_untilted_phantom_is_exactly_symmetric():
    phantom = fractured_pelvis(spacing_mm=3.0)
    flipped = phantom.labels[:, :, ::-1]
    swapped = flipped.copy()
    for a, b in SWAP.items():
        swapped[flipped == a] = b
    assert np.array_equal(swapped, phantom.labels)
    assert set(np.unique(phantom.labels)) == {0, seg.HIP_L, seg.HIP_R, seg.SACRUM, seg.LUMBAR, seg.FEMUR_L, seg.FEMUR_R}


def test_each_hip_is_on_its_own_side():
    phantom = fractured_pelvis(spacing_mm=3.0, yaw_deg=8.0)
    body = np.where(phantom.labels > 0, 700, 40)  # the check wants a CT; the bones will do as a body
    verdict, reason = seg.check_hip_sides(phantom.labels, body, phantom.spacing, phantom.origin)
    assert verdict == "ok", reason


def test_with_no_motion_it_is_the_intact_pelvis():
    phantom = fractured_pelvis(spacing_mm=3.0)
    assert np.array_equal(phantom.labels, phantom.intact_labels)
    assert np.array_equal(phantom.fragment, phantom.fragment_before)
    assert np.allclose(phantom.to_reference, np.eye(4))


@pytest.mark.parametrize("side", ["right", "left"])
def test_the_fragment_moved_by_exactly_the_transform_it_reports(side):
    phantom = fractured_pelvis(translate_mm=(3.0, -2.0, 6.0), rotate_deg=7.0, rotate_axis=(0.3, 1.0, 0.2),
                               side=side, spacing_mm=2.0)
    vol = Volume(phantom.labels, phantom.spacing, phantom.origin)
    hip = seg.HIP_R if side == "right" else seg.HIP_L
    assert phantom.fragment_before.sum() * 8e-3 > 20.0  # a real fragment, cm3
    assert np.all(phantom.labels[phantom.fragment] == hip)
    # Carried back by to_reference, every one of the fragment's voxels lands
    # within a voxel of where it was: the motion is exact, and only the
    # rounding onto the grid is not.
    home = transform_points(phantom.to_reference, vol.mask_voxel_centers_world(phantom.fragment))
    idx = np.rint(vol.world_to_zyx_indices(home)).astype(int)
    assert np.all(ndi.binary_dilation(phantom.fragment_before, structure=np.ones((3, 3, 3)))[tuple(idx)])
    # And the rest of that hip did not move.
    rest = (phantom.intact_labels == hip) & ~phantom.fragment_before
    assert np.all(phantom.labels[rest] == hip)
