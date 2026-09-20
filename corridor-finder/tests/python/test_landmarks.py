import numpy as np

from corridor_engine import segmentation as seg
from corridor_engine.landmarks import detect_landmarks, sanity_warnings
from corridor_engine.phantoms import pelvis_like
from corridor_engine.volume import Volume


def _labels_volume():
    labels, spacing = pelvis_like()
    nx = labels.shape[2]
    # Center the world x origin on the phantom's midline so "left"/"right"
    # correspond to negative/positive world x, as in the engine's RAS convention.
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


def _two_lump_pelvis():
    """A pelvis whose hemipelvis has two anterior parts: a big one high and
    far out (the iliac wing, with an ASIS bump at its front corner) and a
    small one low and near the midline (the pubic body). Only the second
    carries the pubic tubercle. Roughly life-sized, in millimetres, on 1 mm
    voxels, with x = 0 at the midline."""
    nz, ny, nx = 150, 120, 280
    labels = np.zeros((nz, ny, nx), dtype=np.uint8)
    origin = (-140.0, 0.0, 0.0)

    def block(label, x_lo, x_hi, y_lo, y_hi, z_lo, z_hi):
        if x_lo > x_hi:
            x_lo, x_hi = x_hi, x_lo
        labels[z_lo:z_hi, y_lo:y_hi, int(x_lo - origin[0]):int(x_hi - origin[0])] = label

    for label, sign in ((seg.HIP_R, 1), (seg.HIP_L, -1)):
        block(label, sign * 70, sign * 125, 55, 95, 60, 130)   # wing and acetabular roof
        block(label, sign * 95, sign * 110, 95, 102, 100, 115)  # the ASIS itself
        block(label, sign * 5, sign * 22, 70, 100, 25, 45)      # pubic body
        block(label, sign * 22, sign * 70, 60, 80, 40, 70)      # anterior column between them
    block(seg.SACRUM, -12, 12, 15, 45, 50, 110)
    return Volume(labels, (1.0, 1.0, 1.0), origin)


def test_pubic_tubercle_is_on_the_pubic_body_not_the_acetabular_roof():
    landmarks = detect_landmarks(_two_lump_pelvis())
    for side, sign in (("right", 1), ("left", -1)):
        x, y, z = landmarks[f"pubic_tubercle_{side}"].xyz
        assert 8 <= sign * x <= 38, f"{side} tubercle at x={x:.0f}, off the pubic body"
        assert 25 <= z <= 45, f"{side} tubercle at z={z:.0f}, off the pubic body"
        assert y >= 90, f"{side} tubercle at y={y:.0f}, not on the front of it"
    gap = float(np.linalg.norm(landmarks["pubic_tubercle_right"].xyz - landmarks["pubic_tubercle_left"].xyz))
    assert gap <= 80.0
    assert sanity_warnings(landmarks) == [] or all("tubercle" not in w for w in sanity_warnings(landmarks))


def test_sanity_warning_names_a_tubercle_found_far_off_the_midline():
    landmarks = detect_landmarks(_two_lump_pelvis())
    landmarks["pubic_tubercle_right"].xyz = np.array([95.0, 90.0, 60.0])  # on the roof, as before the fix
    assert any("Right pubic tubercle is" in w for w in sanity_warnings(landmarks))
