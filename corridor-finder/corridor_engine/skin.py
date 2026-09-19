"""Skin entry point and incision-guidance offsets.

The skin entry point is found by walking outward from the bony entry point
along the (reversed) screw axis until leaving the body outline (HU below a
threshold approximating air), then reporting that point's offset from the
nearest bony landmarks so the surgeon has a tactile way to find the incision
without relying on navigation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .volume import Volume

BODY_HU_THRESHOLD = -300.0


def body_mask(volume_hu: np.ndarray, threshold: float = BODY_HU_THRESHOLD) -> np.ndarray:
    """True where tissue (not air) — a coarse body-outline mask."""
    from scipy.ndimage import binary_fill_holes, binary_opening

    mask = volume_hu >= threshold
    mask = binary_opening(mask, iterations=1)
    mask = binary_fill_holes(mask)
    return mask


def body_mask_volume(hu_vol: Volume) -> Volume:
    return Volume(body_mask(hu_vol.array).astype(np.uint8), hu_vol.spacing, hu_vol.origin)


def skin_entry_auto(hu_vol: Volume, bone_entry_xyz, direction_out, max_search_mm: float = 150.0, step_mm: float = 1.0, mask_vol: Optional[Volume] = None) -> Tuple[np.ndarray, bool]:
    """Walk from the bony entry point outward along ``direction_out`` (unit
    vector, pointing away from the target, i.e. toward the skin) until the
    sample falls outside the body mask. Returns (point, found). Pass
    ``mask_vol`` (body_mask_volume) to reuse the body mask across calls."""
    if mask_vol is None:
        mask_vol = body_mask_volume(hu_vol)

    direction_out = np.asarray(direction_out, dtype=float)
    direction_out = direction_out / np.linalg.norm(direction_out)
    bone_entry_xyz = np.asarray(bone_entry_xyz, dtype=float)

    n_steps = int(max_search_mm / step_mm)
    dists = np.arange(1, n_steps + 1) * step_mm
    points = bone_entry_xyz.reshape(1, 3) + dists.reshape(-1, 1) * direction_out.reshape(1, 3)
    inside = mask_vol.sample_trilinear(points, order=0) > 0

    if inside.all():
        return points[-1], False
    first_outside = int(np.argmax(~inside))
    if first_outside == 0:
        return bone_entry_xyz, False
    return points[first_outside - 1], True


@dataclass
class SkinOffset:
    landmark: str
    dx_cm: float
    dy_cm: float
    dz_cm: float
    distance_cm: float


def landmark_offsets(skin_xyz, landmarks: Dict[str, np.ndarray], n_nearest: int = 3) -> List[SkinOffset]:
    """Offsets (in cm, world axes) from the skin point to the nearest
    ``n_nearest`` landmarks, sorted by distance."""
    skin_xyz = np.asarray(skin_xyz, dtype=float)
    scored = []
    for name, xyz in landmarks.items():
        xyz = np.asarray(xyz, dtype=float)
        delta_mm = skin_xyz - xyz
        dist_mm = float(np.linalg.norm(delta_mm))
        scored.append((dist_mm, name, delta_mm))
    scored.sort(key=lambda t: t[0])
    out = []
    for dist_mm, name, delta_mm in scored[:n_nearest]:
        out.append(
            SkinOffset(
                landmark=name,
                dx_cm=round(delta_mm[0] / 10.0, 2),
                dy_cm=round(delta_mm[1] / 10.0, 2),
                dz_cm=round(delta_mm[2] / 10.0, 2),
                distance_cm=round(dist_mm / 10.0, 2),
            )
        )
    return out
