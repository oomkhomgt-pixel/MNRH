import numpy as np

from corridor_engine.segmentation import threshold_bone, largest_components, HIP_L, HIP_R


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
