"""Read a CTPelvic1K case into engine label ids, taking sides from geometry.

CTPelvic1K (Liu et al., IJCARS 2021) labels four bones: 1 = sacrum,
2 and 3 = the two hip bones, 4 = lumbar spine. Those ids clash with the
engine's (segmentation.py: HIP_L = 1, HIP_R = 2, SACRUM = 3, FEMUR_L = 4),
so a file read as-is would put the sacrum on the patient's left hip and the
lumbar spine on the left femur. Every id is therefore remapped explicitly.

**Which hip is which is never taken from the id.** Measured over the label
files on this workstation (displacement-finder DECISIONS 2.1a calibration):
id 2 is the patient's left hip in CLINIC, but the right in ABDOMEN (35 of
35) and most of CERVIX (36 of 41), according to each file's own affine.
Either those labels are swapped or the mapped-back images are mirrored, and
labels alone cannot tell which. So the hip whose centroid lies further
toward world +x (RAS: patient right) becomes HIP_R, file by file, and the
two must lie one on each side of the sacrum by segmentation's
HIP_SIDE_MARGIN_MM or the case is refused, as Corridor Finder stops
segmentation when a hip is on the wrong side. With the CT at hand the body
outline gives a second, independent midline (segmentation.check_hip_sides).

**Any scan with metal is refused** (displacement-finder DECISIONS 5.3):
streak artifact corrupts HU exactly along the fracture line, and no
post-operative case has been tested. The reason gives the metal's volume
and its distance to the pelvic bones. Its distance to the fracture itself
needs the fracture surfaces (slice 1b), which do not exist at load time.

nibabel is required (nifti.load_volume), as for any batch work off Slicer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
from scipy import ndimage as ndi

from . import segmentation as seg
from .nifti import load_volume
from .volume import Volume

CTPELVIC1K_SACRUM = 1
CTPELVIC1K_HIPS = (2, 3)  # one per side; which is which differs between subsets
CTPELVIC1K_LUMBAR = 4

# Cortical bone on the four CLINIC CTs peaks at 1608-1779 HU; stainless steel
# and titanium read far above this and usually saturate the scanner's range.
METAL_HU = 2500.0
# Less than this above METAL_HU is taken as noise, not an implant.
METAL_MIN_CM3 = 0.1


class CaseRefused(ValueError):
    """The case cannot be used, and the message says why."""


class MetalInScan(CaseRefused):
    """The CT contains metal (DECISIONS 5.3)."""


@dataclass
class Case:
    labels: Volume  # engine ids: HIP_L, HIP_R, SACRUM, LUMBAR
    ct: Optional[Volume]
    # The file's own id for each side, as found from geometry, so a reader
    # can see which convention the file used.
    source_hip_ids: Dict[str, int]
    note: str


def _centroid_x(mask: np.ndarray, spacing, origin) -> Optional[float]:
    counts = mask.sum(axis=(0, 1), dtype=np.int64)
    total = int(counts.sum())
    if total == 0:
        return None
    return float(origin[0]) + float(spacing[0]) * float(np.dot(np.arange(len(counts)), counts)) / total


def remap_labels(source: Volume, margin_mm: float = seg.HIP_SIDE_MARGIN_MM) -> Tuple[Volume, Dict[str, int], str]:
    """CTPelvic1K ids to engine ids, with each hip's side from world x.

    Returns (engine labels, the file's id for "right" and "left", a note).
    Raises CaseRefused when an id is unexpected, a bone is missing, or the
    hips are not one on each side of the sacrum."""
    array = source.array
    present = set(int(v) for v in np.unique(array)) - {0}
    unexpected = present - {CTPELVIC1K_SACRUM, CTPELVIC1K_LUMBAR, *CTPELVIC1K_HIPS}
    if unexpected:
        raise CaseRefused(f"label ids {sorted(unexpected)} are not CTPelvic1K's four (1 sacrum, 2 and 3 hips, 4 lumbar)")
    xs = {i: _centroid_x(array == i, source.spacing, source.origin) for i in (CTPELVIC1K_SACRUM, *CTPELVIC1K_HIPS)}
    missing = [name for i, name in ((1, "sacrum"), (2, "hip id 2"), (3, "hip id 3")) if xs[i] is None]
    if missing:
        raise CaseRefused(f"{' and '.join(missing)} missing from the labels")

    a, b = CTPELVIC1K_HIPS
    right_id, left_id = (a, b) if xs[a] > xs[b] else (b, a)
    x_mid, xr, xl = xs[CTPELVIC1K_SACRUM], xs[right_id], xs[left_id]
    where = (f"hip id {right_id} x = {xr:.0f} mm, hip id {left_id} x = {xl:.0f} mm, "
             f"sacrum x = {x_mid:.0f} mm (RAS, patient right is +x)")
    if not (xr > x_mid + margin_mm and xl < x_mid - margin_mm):
        raise CaseRefused(f"the hips are not one on each side of the sacrum ({where})")

    out = np.zeros(array.shape, dtype=np.uint8)
    out[array == CTPELVIC1K_SACRUM] = seg.SACRUM
    out[array == CTPELVIC1K_LUMBAR] = seg.LUMBAR
    out[array == right_id] = seg.HIP_R
    out[array == left_id] = seg.HIP_L
    note = f"patient right hip is id {right_id} in this file, left is id {left_id} ({where})"
    return Volume(out, source.spacing, source.origin), {"right": right_id, "left": left_id}, note


def metal(ct: Volume, labels: Volume) -> Tuple[float, float]:
    """The CT's metal volume (cm3) and its nearest distance to the pelvic
    bones (mm, 0 when inside them; inf when there is no metal or bone)."""
    found = ct.array >= METAL_HU
    voxel_cm3 = float(np.prod(ct.spacing)) / 1000.0
    volume_cm3 = float(found.sum()) * voxel_cm3
    bone = labels.array > 0
    if volume_cm3 == 0.0 or not bone.any():
        return volume_cm3, float("inf")
    sx, sy, sz = ct.spacing
    to_bone = ndi.distance_transform_edt(~bone, sampling=(sz, sy, sx))
    return volume_cm3, float(to_bone[found].min())


def _same_grid(a: Volume, b: Volume) -> bool:
    return (a.array.shape == b.array.shape
            and np.allclose(a.spacing, b.spacing, atol=1e-3)
            and np.allclose(a.origin, b.origin, atol=1e-2))


def load_case(label_path: str, image_path: Optional[str] = None) -> Case:
    """Read a CTPelvic1K label file (and its CT, if given) into a Case.

    Raises CaseRefused with the reason when the labels cannot be trusted,
    the CT is not on the label grid, or the CT contains metal."""
    labels, ids, note = remap_labels(load_volume(label_path))
    ct = None
    if image_path is not None:
        ct = load_volume(image_path)
        if not _same_grid(ct, labels):
            raise CaseRefused(f"the CT {ct.array.shape} is not on the label grid {labels.array.shape}")
        verdict, reason = seg.check_hip_sides(labels.array, ct.array, ct.spacing, ct.origin)
        if verdict != "ok":
            raise CaseRefused(f"against the body outline: {reason}")
        volume_cm3, distance_mm = metal(ct, labels)
        if volume_cm3 >= METAL_MIN_CM3:
            raise MetalInScan(
                f"the CT contains {volume_cm3:.1f} cm3 above {METAL_HU:.0f} HU, {distance_mm:.0f} mm from the "
                "pelvic bones; scans with metal are not measured (DECISIONS 5.3). Its distance to the fracture "
                "itself needs the fracture surfaces, which are not yet built")
    return Case(labels=labels, ct=ct, source_hip_ids=ids, note=note)
