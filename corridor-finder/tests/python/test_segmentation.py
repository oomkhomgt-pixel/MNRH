import numpy as np

from corridor_engine.segmentation import FEMUR_R, HIP_L, HIP_R, SACRUM, check_hip_sides, largest_components, sacroiliac_gap_fill, split_pelvis_labels, threshold_bone


def test_threshold_bone_isolates_dense_region():
    hu = np.full((30, 30, 30), -500.0)
    hu[10:20, 10:20, 10:20] = 600.0
    mask = threshold_bone(hu, hu_threshold=250.0)
    assert mask[15, 15, 15]
    assert not mask[0, 0, 0]


def test_largest_components_orders_by_size():
    mask = np.zeros((20, 20, 20), dtype=bool)
    mask[2:4, 2:4, 2:4] = True  # small: 8 voxels
    mask[10:16, 10:16, 10:16] = True  # large: 216 voxels
    _labeled, components = largest_components(mask, n=5)
    assert components[0][1] > components[1][1]


def test_fallback_split_puts_patient_right_at_high_x():
    # World coordinates are RAS with positive spacing, so a higher x index is
    # the patient's RIGHT. A bar spanning both sides stands in for the fused
    # pelvic ring; a separate blob on the high-x side stands in for a femur.
    hu = np.full((20, 20, 60), -500.0)
    hu[8:12, 8:12, 2:58] = 800.0
    hu[0:3, 8:12, 50:56] = 800.0
    labels = split_pelvis_labels(hu, (1.0, 1.0, 1.0))
    assert labels[10, 10, 55] == HIP_R
    assert labels[10, 10, 5] == HIP_L
    assert labels[1, 10, 53] == FEMUR_R


def _two_hip_labels(x_right_mm, x_left_mm, nx=200):
    """1 mm grid centred on x = 0 (world x = index - nx/2), with a soft-tissue
    body across the middle and two hip blocks at the given x centroids."""
    labels = np.zeros((30, 40, nx), dtype=np.uint8)
    hu = np.full(labels.shape, -1000.0)
    hu[:, :, 20:nx - 20] = 40.0  # body, symmetric about x = 0
    for x_mm, label in ((x_right_mm, HIP_R), (x_left_mm, HIP_L)):
        i = int(x_mm + nx / 2)
        labels[10:20, 10:30, i - 5:i + 5] = label
    return labels, hu, (1.0, 1.0, 1.0), (-nx / 2, 0.0, 0.0)


def test_hip_side_check_accepts_anatomical_sides():
    labels, hu, spacing, origin = _two_hip_labels(80.0, -80.0)
    verdict, _ = check_hip_sides(labels, hu, spacing, origin)
    assert verdict == "ok"


def test_hip_side_check_flags_mirrored_sides():
    # Right hip on the patient's left: the scan's left/right orientation may
    # be wrong, which only an anatomy-based segmenter can reveal.
    labels, hu, spacing, origin = _two_hip_labels(-80.0, 80.0)
    verdict, reason = check_hip_sides(labels, hu, spacing, origin)
    assert verdict == "mirrored"
    assert "left" in reason


def test_hip_side_check_rejects_both_hips_on_one_side():
    # What TotalSegmentator returned for the synthetic phantom in Slicer
    # (x = 140.6 and 77.6 mm): two "hips", both on the patient's right.
    labels, hu, spacing, origin = _two_hip_labels(60.0, 25.0)
    verdict, _ = check_hip_sides(labels, hu, spacing, origin)
    assert verdict == "implausible"


def _hip_sacrum_blocks(gap_vox, canal=False):
    """Right hip block and sacrum block side by side along x, separated by a
    gap of gap_vox 1 mm voxels (an SI joint); optionally a 6 mm canal hole
    through the sacrum."""
    labels = np.zeros((40, 40, 80), dtype=np.uint8)
    labels[5:35, 5:35, 40 + gap_vox:75] = HIP_R  # higher x = patient right
    labels[5:35, 5:35, 5:40] = SACRUM
    if canal:
        labels[:, 17:23, 17:23] = 0
    return labels


def test_si_gap_fill_bridges_only_a_joint_within_the_allowance():
    spacing = (1.0, 1.0, 1.0)
    narrow = _hip_sacrum_blocks(gap_vox=2)
    fill = sacroiliac_gap_fill(narrow, spacing, gap_mm=2.0)
    assert fill[20, 20, 40:42].all()  # the 2 mm joint is bridged
    assert not fill[narrow > 0].any()  # never relabels bone
    assert not fill[0, 20, 41] and not fill[20, 0, 41]  # outside the bones' cross-section
    wide = _hip_sacrum_blocks(gap_vox=6)
    assert not sacroiliac_gap_fill(wide, spacing, gap_mm=2.0)[20, 20, 40:46].any()


def test_si_gap_fill_leaves_holes_inside_the_sacrum_alone():
    labels = _hip_sacrum_blocks(gap_vox=2, canal=True)
    fill = sacroiliac_gap_fill(labels, (1.0, 1.0, 1.0), gap_mm=2.0)
    assert not fill[:, 17:23, 17:23].any()  # the "spinal canal" is not bone


def test_si_gap_fill_does_not_bulge_past_the_joint_line():
    # Finer voxels than the allowance: a voxel just in front of the joint
    # line (outside both bones' cross-section) is within the allowance of
    # both bones but not between them, and must stay unfilled.
    labels = np.zeros((40, 40, 160), dtype=np.uint8)
    labels[10:70, 10:30, 83:150] = HIP_R  # 0.5 mm voxels; 3-voxel (1.5 mm) joint
    labels[10:70, 10:30, 10:80] = SACRUM
    fill = sacroiliac_gap_fill(labels, (0.5, 0.5, 0.5), gap_mm=2.0)
    assert fill[20, 20, 80:83].all()  # inside the joint
    assert not fill[20, 8, 80:83].any()  # 1 mm in front of the joint line
