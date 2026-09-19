"""Euclidean distance transform helpers.

``bone_edt_mm`` gives, for every voxel *inside* a bone mask, the distance in
mm to the nearest voxel outside it — i.e. the radius of the largest sphere
centered there that still fits inside the bone. A screw axis's minimum EDT
value along its length is therefore the largest radius a cylindrical screw
could have without breaching either cortex.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
from scipy.ndimage import distance_transform_edt

_edt_cache: Dict[Tuple[int, int, ...], np.ndarray] = {}


def bone_edt_mm(mask: np.ndarray, spacing) -> np.ndarray:
    """EDT (mm) of a boolean bone mask, sampled at the given (sx, sy, sz).

    ``distance_transform_edt`` expects sampling in the same axis order as
    the array (z, y, x), so we reverse the (x, y, z) spacing tuple.
    """
    sx, sy, sz = spacing
    return distance_transform_edt(mask, sampling=(sz, sy, sx))


def cached_bone_edt_mm(mask: np.ndarray, spacing, cache_key) -> np.ndarray:
    """Same as bone_edt_mm but memoized by an arbitrary hashable key.

    Used by the corridor search to avoid recomputing the EDT once per
    candidate corridor that shares the same bone union (e.g. both anterior
    column corridors on the same side use the "hip" mask).
    """
    if cache_key in _edt_cache:
        return _edt_cache[cache_key]
    result = bone_edt_mm(mask, spacing)
    _edt_cache[cache_key] = result
    return result


def clear_cache() -> None:
    _edt_cache.clear()


# Resolution of the distance field embedded in the exported viewer.
VIEWER_EDT_SCALE_MM = 0.1


def quantize_edt_floor(edt_mm: np.ndarray, scale_mm: float = VIEWER_EDT_SCALE_MM) -> np.ndarray:
    """Quantize an EDT (mm) to uint8 steps of ``scale_mm`` for the viewer,
    rounding DOWN and clamping at 255 steps (25.5 mm at 0.1 mm).

    Both only ever lower a value, and trilinear interpolation of lower node
    values is lower everywhere, so the viewer's clearance at any point is at
    most the Slicer-side clearance and at least it minus ``scale_mm``: the
    viewer can be slightly stricter than validate.py but never more lenient.
    (Clamping only affects points more than 25.5 mm from any cortex.)
    """
    steps = np.floor(np.clip(edt_mm, 0.0, 255.0 * scale_mm) / scale_mm)
    return np.clip(steps, 0, 255).astype(np.uint8)
