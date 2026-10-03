"""Surfaces that carry their own margin (DECISIONS.md 7.9).

A screw keeps the full safety margin from every cortex, the sacral canal and
the nerve foramina, but may touch the acetabular articular surface as long
as it does not cross it. The breach rule itself stays one rule -- clearance
below the margin -- written identically in validate.py, the exported
viewer's clearance.js and the report. What changes is the distance field
that rule reads, built here:

    E = min(distance to the nearest surface other than the hip joint,
            distance to the hip joint's surface + margin)

inside bone, and 0 outside it. Then "E - radius >= margin" at every point
means exactly: at least the margin from every other surface, and at least
zero -- touching, not crossing -- from the joint surface. Outside bone
nothing changes, so where the bone ends, and every cortex crossing found
from it, stays where it was.

The joint surface is found as the space the hip bone and its femoral head
face each other across, the same "facing" test si_joint.py uses between the
ilium and the sacrum. Without a femur label (the public CTPelvic1K labels
have none) there is no joint space, the field is the plain one, and the
full margin applies everywhere: the safe direction.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from scipy import ndimage as ndi

from .edt import bone_edt_mm
from .si_joint import facing as _facing
from .volume import Volume

JOINT_MAX_MM = 6.0  # a hip joint space wider than this is not a joint space


def joint_space(labels: np.ndarray, spacing, bone_label: int, other_label: int,
                max_mm: float = JOINT_MAX_MM) -> np.ndarray:
    """The empty space between ``bone_label`` and ``other_label`` that the
    two face each other across (both within ``max_mm``, their nearest
    points on opposite sides). Boolean, on the labels' grid."""
    out = np.zeros(labels.shape, dtype=bool)
    other = labels == other_label
    bone = labels == bone_label
    if not other.any() or not bone.any():
        return out
    sx, sy, sz = spacing
    sampling = np.array([sz, sy, sx], dtype=float)
    # Work in a box around the other bone (the femoral head), padded by the
    # joint width: the joint space lies within it.
    idx = np.argwhere(other)
    pad = np.ceil((max_mm + max(spacing)) / sampling).astype(int) + 1
    lo = np.maximum(idx.min(axis=0) - pad, 0)
    hi = np.minimum(idx.max(axis=0) + pad + 1, labels.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    to_bone, at_bone = ndi.distance_transform_edt(~bone[box], sampling=sampling, return_indices=True)
    to_other, at_other = ndi.distance_transform_edt(~other[box], sampling=sampling, return_indices=True)
    here = np.indices(to_bone.shape)
    to_bone_vec = (at_bone - here) * sampling[:, None, None, None]
    to_other_vec = (at_other - here) * sampling[:, None, None, None]
    facing = _facing(to_bone_vec, to_other_vec, to_bone, to_other)
    near_both = (labels[box] == 0) & (to_bone <= max_mm) & (to_other <= max_mm)
    space = near_both & facing
    # The empty voxel right against a curved surface often has its nearest
    # bone voxel beside it rather than across the joint, and so fails the
    # facing test; without it the bone still borders a gap that is not
    # counted as joint, and the screw is held off the surface after all.
    # One step outward, still within the joint width of both bones, closes
    # that rim.
    space |= ndi.binary_dilation(space) & near_both
    out[box] = space
    return out


def articular_field(plain: Volume, bone_mask: np.ndarray, joint: np.ndarray, margin_mm: float) -> Volume:
    """The field a screw is checked against when it may touch ``joint`` but
    must keep ``margin_mm`` from every other surface (see the module
    docstring). ``plain`` is the ordinary distance field of ``bone_mask``;
    with no joint space it is returned unchanged."""
    if not joint.any():
        return plain
    filled = bone_edt_mm(bone_mask | joint, plain.spacing)  # the joint space no longer counts as a surface
    lifted = np.minimum(filled, plain.array + float(margin_mm))
    array = np.where(plain.array > 0, lifted, 0.0).astype(plain.array.dtype, copy=False)
    return Volume(array=array, spacing=plain.spacing, origin=plain.origin)


def articular_clearance(plain: Volume, points: np.ndarray, radius_mm: float) -> Optional[float]:
    """How close a screw sampled at ``points`` comes to crossing the joint
    surface: the smallest plain-field clearance, for the panel and report
    to state beside the margin-checked clearance."""
    if points is None or len(points) == 0:
        return None
    return float(np.min(plain.sample_trilinear(np.asarray(points, dtype=float), order=1)) - radius_mm)
