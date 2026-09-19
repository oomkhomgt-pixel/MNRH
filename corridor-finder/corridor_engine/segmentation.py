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


# How far (mm) each hip bone's centroid must lie on its own side of the
# body's midline. An adult hip bone's centroid is about 80-100 mm from it.
HIP_SIDE_MARGIN_MM = 20.0
_BODY_HU = -300.0  # tissue vs air, as for the skin outline


def check_hip_sides(labels: np.ndarray, volume_hu: np.ndarray, spacing, origin, margin_mm: float = HIP_SIDE_MARGIN_MM):
    """Check that hip_right and hip_left lie on the patient's right and left.

    Arrays are ZYX on the same grid; world x is RAS (patient right = +x,
    see volume.py). The midline is the x centroid of the body outline.
    Returns (verdict, reason):

    - "ok": each hip is clearly on its own side;
    - "mirrored": hip_right is clearly on the patient's LEFT and hip_left on
      the right. For a segmenter that labels sides by anatomy (such as
      TotalSegmentator) that means the scan's left-right orientation may be
      wrong, so planning must stop rather than fall back to a segmenter that
      trusts the orientation;
    - "implausible": a hip is missing, or the two are not one on each side
      (seen when TotalSegmentator was run on a synthetic phantom).
    """
    sx, ox = float(spacing[0]), float(origin[0])

    def centroid_x(mask):
        counts = mask.sum(axis=(0, 1), dtype=np.int64)
        total = int(counts.sum())
        if total == 0:
            return None
        return ox + sx * float(np.dot(np.arange(len(counts)), counts)) / total

    xr, xl = centroid_x(labels == HIP_R), centroid_x(labels == HIP_L)
    if xr is None or xl is None:
        return "implausible", "a hip bone is missing"
    x_mid = centroid_x(volume_hu > _BODY_HU)
    if x_mid is None:
        x_mid = (xr + xl) / 2.0
    where = f"hip_right x = {xr:.0f} mm, hip_left x = {xl:.0f} mm, body midline x = {x_mid:.0f} mm (RAS, patient right is +x)"
    if xr > x_mid + margin_mm and xl < x_mid - margin_mm:
        return "ok", where
    if xr < x_mid - margin_mm and xl > x_mid + margin_mm:
        return "mirrored", f"the right hip is on the patient's left and the left hip on the right ({where})"
    return "implausible", f"the hips are not one on each side of the body ({where})"


def sacroiliac_gap_fill(labels: np.ndarray, spacing, gap_mm: float, hips=(HIP_R, HIP_L)) -> np.ndarray:
    """The sacroiliac joint space: voxels that are not bone but lie within
    ``gap_mm`` of both the sacrum and one of ``hips``.

    Iliosacral and transiliac-transsacral screws cross the SI joint by
    design, and in a bone segmentation the joint is a thin gap between the
    hip and sacrum labels, where the distance to "non-bone" drops to zero.
    Counting this gap as bone makes the clearance there the distance to the
    bones' outer cortex instead. Only gaps up to ``gap_mm`` wide and only
    between a hip and the sacrum are bridged, so holes inside the sacrum
    (foramina, canal) and every outer cortex are unaffected. This is what
    corridors.json's ``sacral_gap_allowance_mm`` specifies.
    """
    fill = np.zeros(labels.shape, dtype=bool)
    sacrum = labels == SACRUM
    if gap_mm <= 0 or not sacrum.any():
        return fill
    sx, sy, sz = spacing
    zyx_spacing = (sz, sy, sx)
    # Work in a box around the sacrum; the joint lies within gap_mm of it.
    pad = np.array([int(np.ceil(gap_mm / s)) + 1 for s in zyx_spacing])
    idx = np.argwhere(sacrum)
    lo = np.maximum(idx.min(axis=0) - pad, 0)
    hi = np.minimum(idx.max(axis=0) + pad + 1, labels.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    sub = labels[box]
    to_sacrum = ndi.distance_transform_edt(sub != SACRUM, sampling=zyx_spacing)
    sub_fill = np.zeros(sub.shape, dtype=bool)
    for hip in hips:
        if (sub == hip).any():
            to_hip = ndi.distance_transform_edt(sub != hip, sampling=zyx_spacing)
            # Within the allowance of both bones AND between them (the two
            # distances add up to about the gap), so the bridge does not
            # bulge past the joint line at its rims.
            sub_fill |= (to_hip <= gap_mm) & (to_sacrum <= gap_mm) & (to_hip + to_sacrum <= gap_mm + max(spacing))
    fill[box] = sub_fill & (sub == 0)
    return fill


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
