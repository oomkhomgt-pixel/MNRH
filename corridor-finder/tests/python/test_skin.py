import numpy as np

from corridor_engine.skin import skin_entry_auto, landmark_offsets
from corridor_engine.volume import Volume


def test_skin_entry_found_at_ellipsoid_surface():
    n = 100
    spacing = (1.0, 1.0, 1.0)
    zz, yy, xx = np.mgrid[0:n, 0:n, 0:n]
    c = n / 2.0

    soft_tissue_radius = 35.0
    bone_radius = 10.0
    d = np.sqrt((zz - c) ** 2 + (yy - c) ** 2 + (xx - c) ** 2)

    hu = np.full((n, n, n), -1000.0)  # air everywhere
    hu[d <= soft_tissue_radius] = -50.0  # soft tissue ellipsoid (here: sphere)
    hu[d <= bone_radius] = 800.0  # bone at the center

    vol = Volume(hu, spacing)
    bone_entry = np.array([c, c, c]) + np.array([bone_radius, 0.0, 0.0])
    direction_out = np.array([1.0, 0.0, 0.0])  # walk outward along +x

    point, found = skin_entry_auto(vol, bone_entry, direction_out, max_search_mm=60.0, step_mm=0.5)
    assert found
    # The skin should be found near x = c + soft_tissue_radius
    expected_x = c + soft_tissue_radius
    assert abs(point[0] - expected_x) < 2.0


def test_landmark_offsets_sorted_by_distance():
    skin = np.array([0.0, 0.0, 0.0])
    landmarks = {
        "near": np.array([10.0, 0.0, 0.0]),
        "far": np.array([100.0, 0.0, 0.0]),
        "medium": np.array([50.0, 0.0, 0.0]),
    }
    offsets = landmark_offsets(skin, landmarks, n_nearest=2)
    assert len(offsets) == 2
    assert offsets[0].landmark == "near"
    assert offsets[1].landmark == "medium"
    assert offsets[0].distance_cm == 1.0
