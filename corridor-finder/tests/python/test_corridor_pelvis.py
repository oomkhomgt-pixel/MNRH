import numpy as np

from corridor_engine import segmentation as seg
from corridor_engine.corridor import search_corridor
from corridor_engine.edt import bone_edt_mm
from corridor_engine.landmarks import detect_landmarks
from corridor_engine.phantoms import pelvis_like
from corridor_engine.volume import Volume


def _phantom_volume():
    labels, spacing = pelvis_like()
    nx = labels.shape[2]
    origin = (-(nx / 2.0) * spacing[0], 0.0, 0.0)
    return Volume(labels, spacing, origin)


def test_iliosacral_corridor_crosses_hip_and_sacrum():
    labels_vol = _phantom_volume()
    landmarks = detect_landmarks(labels_vol)
    assert "si_joint_center_right" in landmarks
    assert "s1_body_center" in landmarks

    union_mask = (labels_vol.array == seg.HIP_R) | (labels_vol.array == seg.SACRUM)
    edt = bone_edt_mm(union_mask, labels_vol.spacing)
    edt_vol = Volume(edt, labels_vol.spacing, labels_vol.origin)

    entry_mask = labels_vol.array == seg.HIP_R
    exit_mask = labels_vol.array == seg.SACRUM

    entry_center = landmarks["si_joint_center_right"].xyz + np.array([40.0, 0.0, 0.0])
    exit_center = landmarks["s1_body_center"].xyz

    results = search_corridor(
        entry_mask=entry_mask,
        exit_mask=exit_mask,
        entry_center_xyz=entry_center,
        entry_radius_mm=30.0,
        exit_center_xyz=exit_center,
        exit_radius_mm=12.0,
        edt_vol=edt_vol,
        labels_vol=labels_vol,
        margin_mm=1.0,
        screw_diameters_mm=[6.5, 7.0, 7.3],
        length_range_mm=(60.0, 140.0),
        n_entry=80,
        n_exit=80,
        top_k=1,
    )
    assert results, "expected a corridor crossing the hip and sacrum"
    best = results[0]
    assert seg.HIP_R in best.traversed_labels
    assert seg.SACRUM in best.traversed_labels
