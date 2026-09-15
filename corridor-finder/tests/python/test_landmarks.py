import numpy as np

from corridor_engine.landmarks import detect_landmarks, sanity_warnings
from corridor_engine.phantoms import pelvis_like
from corridor_engine.volume import Volume


def _labels_volume():
    labels, spacing = pelvis_like()
    nx = labels.shape[2]
    # Center the world x origin on the phantom's midline so "left"/"right"
    # correspond to negative/positive world x, matching the APP convention.
    origin = (-(nx / 2.0) * spacing[0], 0.0, 0.0)
    return Volume(labels, spacing, origin)


def test_detects_bilateral_landmarks():
    vol = _labels_volume()
    landmarks = detect_landmarks(vol)

    for name in ("asis_right", "asis_left", "psis_right", "psis_left",
                 "pubic_tubercle_right", "pubic_tubercle_left",
                 "ischial_tuberosity_right", "ischial_tuberosity_left"):
        assert name in landmarks, f"missing landmark {name}"

    # right-side landmarks should be on the +x side, left on -x
    assert landmarks["asis_right"].xyz[0] > 0
    assert landmarks["asis_left"].xyz[0] < 0


def test_sacrum_and_si_joint_landmarks_present():
    vol = _labels_volume()
    landmarks = detect_landmarks(vol)
    assert "s1_body_center" in landmarks
    assert "s2_body_center" in landmarks
    # s1 should be more superior (higher z) than s2 in this phantom
    assert landmarks["s1_body_center"].xyz[2] > landmarks["s2_body_center"].xyz[2]


def test_sanity_warnings_is_a_list_of_strings():
    vol = _labels_volume()
    landmarks = detect_landmarks(vol)
    warnings = sanity_warnings(landmarks)
    assert isinstance(warnings, list)
    for w in warnings:
        assert isinstance(w, str)
