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


def coarse_edt_uint8(edt_mm: np.ndarray, clamp_mm: float = 255.0) -> np.ndarray:
    """Quantize an EDT volume to uint8 mm for compact export to the viewer."""
    clamped = np.clip(edt_mm, 0.0, clamp_mm)
    return np.round(clamped).astype(np.uint8)
