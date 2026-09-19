"""Bone label ids and the HU-threshold fallback segmenter.

TotalSegmentator (run from the Slicer adapter) is the primary path and
should populate a label array using these same ids directly. The fallback
here is a coarse threshold + connected-components heuristic for use when
TotalSegmentator is unavailable; results from it must be flagged
"unverified" by the caller (the Slicer UI does this).
"""
from __future__ import annotations

from typing import Dict

import numpy as np
from scipy import ndimage as ndi

HIP_L = 1
HIP_R = 2
SACRUM = 3
FEMUR_L = 4
FEMUR_R = 5

LABEL_NAMES: Dict[int, str] = {
    HIP_L: "hip_left",
    HIP_R: "hip_right",
    SACRUM: "sacrum",
    FEMUR_L: "femur_left",
    FEMUR_R: "femur_right",
}

BONE_GROUPS: Dict[str, tuple] = {
    "hip": (HIP_L, HIP_R),
    "sacrum": (SACRUM,),
    "femur": (FEMUR_L, FEMUR_R),
}


def labels_for_side(group: str, side: str) -> tuple:
    """Resolve a corridors.json 'bones' group name + side to label ids.

    side is "left" or "right"; groups without a side (sacrum) ignore it.
    """
    if group == "hip":
        return (HIP_L,) if side == "left" else (HIP_R,)
    if group == "femur":
        return (FEMUR_L,) if side == "left" else (FEMUR_R,)
    if group == "sacrum":
        return (SACRUM,)
    raise ValueError(f"unknown bone group: {group}")


def threshold_bone(volume_hu: np.ndarray, hu_threshold: float = 250.0) -> np.ndarray:
    """Binary bone mask by simple HU thresholding + morphological closing."""
    mask = volume_hu >= hu_threshold
    mask = ndi.binary_closing(mask, structure=np.ones((3, 3, 3)), iterations=1)
    mask = ndi.binary_fill_holes(mask)
    return mask


def largest_components(mask: np.ndarray, n: int = 8):
    """Return up to n largest connected components as (label_array, sizes)."""
    labeled, num = ndi.label(mask)
    if num == 0:
        return labeled, []
    sizes = ndi.sum(mask, labeled, index=np.arange(1, num + 1))
    order = np.argsort(sizes)[::-1]
    keep = order[:n] + 1
    return labeled, [(int(cid), int(sizes[cid - 1])) for cid in keep]


def split_pelvis_labels(volume_hu: np.ndarray, spacing) -> np.ndarray:
    """Fallback segmentation: threshold + heuristic component assignment.

    This is intentionally simple and will not separate bones that touch at
    a joint (SI joint, hip joint). Callers must present its output as
    "unverified — confirm with TotalSegmentator or manual painting".
    """
    mask = threshold_bone(volume_hu)
    labeled, components = largest_components(mask, n=6)
    out = np.zeros(mask.shape, dtype=np.uint8)
    if not components:
        return out

    nz, ny, nx = mask.shape
    # Higher x index is the patient's RIGHT: world coordinates are RAS with
    # positive spacing (see volume.py), so side assignment below relies on it.
    mid_x = nx / 2.0

    # Largest component is assumed to be the fused pelvic ring (both hips +
    # sacrum, since they usually touch); split it by x relative to midline
    # and by an EDT-based cut for the sacrum in the middle third.
    main_id = components[0][0]
    main_mask = labeled == main_id
    xs = np.arange(nx).reshape(1, 1, nx)
    xs = np.broadcast_to(xs, mask.shape)

    sacrum_band = (np.abs(xs - mid_x) < nx * 0.12) & main_mask
    hip_r_band = (xs >= mid_x) & main_mask & ~sacrum_band
    hip_l_band = (xs < mid_x) & main_mask & ~sacrum_band

    out[hip_r_band] = HIP_R
    out[hip_l_band] = HIP_L
    out[sacrum_band] = SACRUM

    # Remaining components (if the pelvis fragmented, e.g. femurs separated
    # by the joint space) are assigned to femur by side using their centroid.
    for cid, _size in components[1:]:
        comp_mask = labeled == cid
        centroid = ndi.center_of_mass(comp_mask)
        cx = centroid[2]
        out[comp_mask] = FEMUR_R if cx >= mid_x else FEMUR_L

    return out
