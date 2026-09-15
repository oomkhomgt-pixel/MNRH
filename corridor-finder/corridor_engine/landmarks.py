"""Bony landmark detection from segmentation labels.

All detection is done by extreme-point heuristics on label masks in the
scanner's native (LPS-like) axes: x = patient right(-)/left(+),
y = posterior(-)/anterior(+), z = caudal(-)/cephalad(+) (see volume.py for
the array/world convention — these are just how we choose to interpret the
x/y/z world axes before an APP frame exists).

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
    "femoral_head_center_left", "si_joint_center_right", "s1_body_center",
    "s2_body_center", "iliac_crest_apex_right"), each an auto-sourced Landmark.
    """
    arr = labels_vol.array
    out: Dict[str, Landmark] = {}

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

        x_mid = pts[:, 0].mean()
        near_midline = pts[np.abs(pts[:, 0] - x_mid) < np.ptp(pts[:, 0]) * 0.35]
        if near_midline.shape[0] == 0:
            near_midline = pts
        z2 = near_midline[:, 2]
        lower_medial = near_midline[z2 < z2.min() + 0.5 * (z2.max() - z2.min())]
        if lower_medial.shape[0] == 0:
            lower_medial = near_midline
        score_dir = np.array([0.0, 0.7, 0.7])
        out[f"pubic_tubercle_{side}"] = Landmark(_extreme_point(lower_medial, score_dir / np.linalg.norm(score_dir)))

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

    sac_pts = labels_vol.mask_voxel_centers_world(sacrum_mask)
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
        if d > 40.0:
            warnings.append(f"Pubic tubercles are {d:.0f} mm apart (expected <= 40 mm)")

    if asis_r is not None and pt_r is not None and asis_r[2] < pt_r[2]:
        warnings.append("Right ASIS is not superior to the right pubic tubercle")
    if asis_l is not None and pt_l is not None and asis_l[2] < pt_l[2]:
        warnings.append("Left ASIS is not superior to the left pubic tubercle")

    return warnings
