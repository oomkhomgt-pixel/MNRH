"""Bony landmark detection from segmentation labels.

All detection is done by extreme-point heuristics on label masks in the
engine's world axes, RAS: x = patient left(-)/right(+),
y = posterior(-)/anterior(+), z = caudal(-)/cephalad(+) (see volume.py).
Only the signs of y and z are used here; which side a landmark belongs to
comes from the hip/femur label it was found on, never from its x sign.

This is inherently approximate. Results carry source="auto" and a caller
(the Slicer UI) lets the surgeon drag any landmark, recording source="manual"
and the resulting angles are recomputed from wherever the point ends up.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from . import segmentation as seg
from .volume import Volume


# The pubic body is the part of a hemipelvis that reaches furthest across
# toward the other side. This is how much of the bone, ranked by that reach,
# is searched for the tubercle on its front.
PUBIS_MEDIAL_PERCENTILE = 90.0
# The pelvic brim runs along the inner edge of the hemipelvis. Its front
# half, which is what a posterior column screw aims at or starts from, lies
# this close to the midline and in front of the sacrum.
BRIM_HALF_WIDTH_MM = 60.0


@dataclass
class Landmark:
    xyz: np.ndarray
    source: str = "auto"


def _extreme_point(points: np.ndarray, direction: np.ndarray, top_frac: float = 0.01) -> np.ndarray:
    """Centroid of the top ``top_frac`` of points ranked by projection onto
    ``direction`` (a unit vector), i.e. a robust "most extreme" point."""
    if points.shape[0] == 0:
        raise ValueError("no points to extract landmark from")
    proj = points @ direction
    n_keep = max(1, int(np.ceil(points.shape[0] * top_frac)))
    order = np.argsort(proj)[::-1]
    top = points[order[:n_keep]]
    return top.mean(axis=0)


def detect_landmarks(labels_vol: Volume) -> Dict[str, Landmark]:
    """Detect the standard pelvic landmark set from a labelled Volume.

    Returns a dict keyed by landmark name (e.g. "asis_right", "psis_left",
    "pubic_tubercle_right", "ischial_tuberosity_left", "greater_trochanter_right",
    "pelvic_brim_left",
    "femoral_head_center_left", "si_joint_center_right", "s1_body_center",
    "s2_body_center", "iliac_crest_apex_right"), each an auto-sourced Landmark.
    """
    arr = labels_vol.array
    out: Dict[str, Landmark] = {}

    sac_pts = labels_vol.mask_voxel_centers_world(arr == seg.SACRUM)
    hip_masks = {"right": arr == seg.HIP_R, "left": arr == seg.HIP_L}
    femur_masks = {"right": arr == seg.FEMUR_R, "left": arr == seg.FEMUR_L}
    sacrum_mask = arr == seg.SACRUM
    for side, hip_mask in hip_masks.items():
        pts = labels_vol.mask_voxel_centers_world(hip_mask)
        if pts.shape[0] == 0:
            continue
        z = pts[:, 2]
        z_lo, z_hi = z.min(), z.max()
        upper_band = pts[z > z_lo + 0.6 * (z_hi - z_lo)]

        if upper_band.shape[0] > 0:
            out[f"asis_{side}"] = Landmark(_extreme_point(upper_band, np.array([0.0, 1.0, 0.0])))
            out[f"psis_{side}"] = Landmark(_extreme_point(upper_band, np.array([0.0, -1.0, 0.0])))

        out[f"iliac_crest_apex_{side}"] = Landmark(_extreme_point(pts, np.array([0.0, 0.0, 1.0])))
        out[f"ischial_tuberosity_{side}"] = Landmark(_extreme_point(pts, np.array([0.0, 0.0, -1.0])))

        # Pubic tubercle: on the front of the pubic body, beside the
        # symphysis. The pubic body is what reaches furthest across toward
        # the other hemipelvis, so of the bone that reaches furthest that
        # way, take the point that reaches furthest forward. (Patient right
        # is +x, so "across" is -x for the right hip and +x for the left;
        # which hip this is comes from its label, not from any x sign.)
        # Ranking the whole hemipelvis by anterior and superior together
        # instead lands on the acetabular roof, a hand's breadth too far
        # out, and ranking the bone near the midline by height alone slides
        # outward along the superior ramus as it climbs.
        toward_other_side = -1.0 if side == "right" else 1.0
        reach = pts[:, 0] * toward_other_side
        medial = pts[reach >= np.percentile(reach, PUBIS_MEDIAL_PERCENTILE)]
        out[f"pubic_tubercle_{side}"] = Landmark(_extreme_point(medial, np.array([0.0, 1.0, 0.0])))

        # Pelvic brim: the top of the hemipelvis's inner edge in front of the
        # sacrum, i.e. the arcuate and pectineal lines where they rise over
        # the hip joint. A posterior column screw runs between here and the
        # ischial tuberosity, either way round, so this is the far end of
        # that corridor.
        if sac_pts.shape[0] > 0:
            midline_x = float(sac_pts[:, 0].mean())
            in_front = float(np.percentile(sac_pts[:, 1], 90.0))
            brim = pts[(np.abs(pts[:, 0] - midline_x) <= BRIM_HALF_WIDTH_MM) & (pts[:, 1] >= in_front)]
            if brim.shape[0] > 0:
                out[f"pelvic_brim_{side}"] = Landmark(_extreme_point(brim, np.array([0.0, 0.0, 1.0])))

    for side, femur_mask in femur_masks.items():
        pts = labels_vol.mask_voxel_centers_world(femur_mask)
        if pts.shape[0] == 0:
            continue
        z = pts[:, 2]
        top = pts[z > z.max() - 60.0]
        if top.shape[0] == 0:
            top = pts
        head_center = top.mean(axis=0)
        out[f"femoral_head_center_{side}"] = Landmark(head_center)
        far = pts[np.linalg.norm(pts[:, [0]] - head_center[0], axis=1) > 15.0] if pts.shape[0] else pts
        candidates = far if far.shape[0] > 0 else pts
        out[f"greater_trochanter_{side}"] = Landmark(_extreme_point(candidates, np.array([0.0, 0.0, 1.0])))

    if sac_pts.shape[0] > 0:
        z = sac_pts[:, 2]
        z_lo, z_hi = z.min(), z.max()
        s1_band = sac_pts[(z > z_lo + 0.55 * (z_hi - z_lo)) & (z < z_lo + 0.75 * (z_hi - z_lo))]
        s2_band = sac_pts[(z > z_lo + 0.35 * (z_hi - z_lo)) & (z < z_lo + 0.55 * (z_hi - z_lo))]
        if s1_band.shape[0] > 0:
            out["s1_body_center"] = Landmark(s1_band.mean(axis=0))
        if s2_band.shape[0] > 0:
            out["s2_body_center"] = Landmark(s2_band.mean(axis=0))

    for side, hip_mask in hip_masks.items():
        near_sacrum = hip_mask & _dilate_touch(sacrum_mask)
        pts = labels_vol.mask_voxel_centers_world(near_sacrum & hip_mask)
        if pts.shape[0] > 0:
            out[f"si_joint_center_{side}"] = Landmark(pts.mean(axis=0))

    return out


def _dilate_touch(mask: np.ndarray, iterations: int = 3) -> np.ndarray:
    from scipy.ndimage import binary_dilation

    return binary_dilation(mask, iterations=iterations)


def sanity_warnings(landmarks: Dict[str, Landmark]) -> list:
    """Plausibility checks on detected landmarks; returns human-readable
    warning strings (never raises) so the UI can flag a likely mis-detection."""
    warnings = []

    def get(name: str) -> Optional[np.ndarray]:
        lm = landmarks.get(name)
        return lm.xyz if lm else None

    asis_r, asis_l = get("asis_right"), get("asis_left")
    if asis_r is not None and asis_l is not None:
        d = np.linalg.norm(asis_r - asis_l)
        if not (180.0 <= d <= 300.0):
            warnings.append(f"ASIS-to-ASIS distance {d:.0f} mm is outside the expected 180-300 mm range")

    pt_r, pt_l = get("pubic_tubercle_right"), get("pubic_tubercle_left")
    if pt_r is not None and pt_l is not None:
        d = np.linalg.norm(pt_r - pt_l)
        # Each point sits on the front of its own pubic body, so up to about
        # 25 mm out from the midline; beyond 60 mm apart the symphysis is
        # either sprung or the points are not on the pubis at all.
        if d > 60.0:
            warnings.append(f"Pubic tubercles are {d:.0f} mm apart (expected <= 60 mm): either the symphysis is "
                            f"disrupted or a landmark is misplaced")

    if asis_r is not None and asis_l is not None:
        mid_x = (asis_r[0] + asis_l[0]) / 2.0
        for side, pt in (("Right", pt_r), ("Left", pt_l)):
            if pt is not None and abs(pt[0] - mid_x) > 60.0:
                warnings.append(f"{side} pubic tubercle is {abs(pt[0] - mid_x):.0f} mm from the midline "
                                f"(expected within 60 mm)")

    if asis_r is not None and pt_r is not None and asis_r[2] < pt_r[2]:
        warnings.append("Right ASIS is not superior to the right pubic tubercle")
    if asis_l is not None and pt_l is not None and asis_l[2] < pt_l[2]:
        warnings.append("Left ASIS is not superior to the left pubic tubercle")

    return warnings
