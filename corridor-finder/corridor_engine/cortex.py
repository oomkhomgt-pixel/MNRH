"""Where a screw crosses the cortex, and the breach-rule exemption there.

DECISIONS.md section 1. A screw's entry is where its axis crosses the outer
cortex, and it necessarily passes through that cortex (and, for corridors
whose tip goes through the far cortex, through that one too). Near such a
crossing the breach rule ignores only the non-bone that lies outside that
cortex: beyond its tangent plane at the crossing, moved inward by
CORTEX_DEPTH_TOLERANCE_MM. Non-bone deeper than that still counts, so a
side-wall breach next to the entry is still caught. The stretch of screw
this applies to is (r + m + tolerance) / cos(angle between the axis and the
cortex normal), capped at its 60 degree value; steeper crossings get a
warning.

The tolerance is PROVISIONAL (DECISIONS.md 1.2a): with the tangent plane
alone (tolerance 0) the rule flagged about 95% of the entries on the sample
CT that had clear bone right after them, because a segmented cortex is
neither flat nor smooth (TotalSegmentator works at 1.5 mm and bone curves),
so its own surface dips below the plane within the screw's envelope.

Everything here is derived from a screw's distance field (bone = field > 0),
the same data the exported viewer receives, with deterministic steps
(nearest-voxel lookups, integer voxel sums, an exact distance transform)
whose floating-point arithmetic viewer/clearance.js repeats operation for
operation. Keep the two in sync; tests/python/test_viewer_clearance_golden.py
compares them.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from scipy.ndimage import distance_transform_edt

from .volume import Volume

CROSSING_STEP_MM = 0.1  # resolution of the search for a cortex crossing
MAX_SEARCH_MM = 20.0  # how far behind the entry handle / past the target a cortex is searched for
NORMAL_RADIUS_MM = 4.0  # bone within this radius defines the cortex normal
OBLIQUE_WARN_DEG = 60.0  # steeper crossings are flagged (warning only)
COS_OBLIQUE = 0.5  # cos(OBLIQUE_WARN_DEG), written out so clearance.js matches bit for bit
# PROVISIONAL (DECISIONS.md 1.2a): non-bone less than this far inside the
# tangent plane of a crossed cortex counts as that cortex's own shape.
CORTEX_DEPTH_TOLERANCE_MM = 1.5
# A far-cortex tip is exempted at most this far past the cortex: the 5 mm
# catalogue step that rounding up can add (DECISIONS.md 1.6).
MAX_PROTRUSION_MM = 5.0


# 3-vector helpers written out term by term, in the same order as
# viewer/clearance.js, so both sides round identically.
def dot3(a, b) -> float:
    return float(a[0]) * float(b[0]) + float(a[1]) * float(b[1]) + float(a[2]) * float(b[2])


def unit3(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = float(np.sqrt(dot3(v, v)))
    return v / n if n > 0 else v


def _nearest_voxel(field: Volume, points: np.ndarray) -> np.ndarray:
    ijk = (points - np.asarray(field.origin, dtype=float)) / np.asarray(field.spacing, dtype=float)
    return np.floor(ijk + 0.5).astype(np.int64)


def _inside(field: Volume, points) -> np.ndarray:
    """Nearest-voxel test of whether each world point is bone (field > 0).
    Outside the grid counts as not bone."""
    pts = np.atleast_2d(np.asarray(points, dtype=float))
    idx = _nearest_voxel(field, pts)
    nz, ny, nx = field.array.shape
    ok = (idx[:, 0] >= 0) & (idx[:, 0] < nx) & (idx[:, 1] >= 0) & (idx[:, 1] < ny) & (idx[:, 2] >= 0) & (idx[:, 2] < nz)
    out = np.zeros(len(pts), dtype=bool)
    out[ok] = field.array[idx[ok, 2], idx[ok, 1], idx[ok, 0]] > 0
    return out


def _march(field: Volume, start, direction, length_mm: float):
    """Points every CROSSING_STEP_MM from ``start`` along ``direction`` for
    ``length_mm`` (both ends included when it divides evenly)."""
    n = int(np.floor(length_mm / CROSSING_STEP_MM + 1e-9)) + 1
    t = np.arange(n) * CROSSING_STEP_MM
    pts = np.asarray(start, dtype=float) + t[:, None] * np.asarray(direction, dtype=float)
    return t, pts, _inside(field, pts)


def _outer_surface(field: Volume, crossing, outward) -> bool:
    """Whether a crossing (a bone point) is the bone's outer surface along
    the axis: no bone within MAX_SEARCH_MM beyond it in ``outward``. If bone
    resumes, the crossing is a gap inside the bone (a joint wider than it is
    bridged, the sacral canal, a foramen), which is not exempted."""
    _t, _pts, inside = _march(field, crossing, outward, MAX_SEARCH_MM)
    return not np.any(inside[1:])


def entry_crossing(field: Volume, entry, target) -> Tuple[Optional[np.ndarray], float, Optional[str]]:
    """Where the axis from ``entry`` toward ``target`` enters the bone.

    Returns (point, offset_mm, problem). offset > 0: the entry handle lies
    that far outside the cortex; < 0: that far inside it. problem is None
    for a crossing of the outer cortex; "entry_not_outer" when the crossing
    found is a gap inside the bone (point is that crossing); "no_bone" when
    the axis never enters bone before the target, and "cortex_not_found"
    when the handle is in bone with no crossing within MAX_SEARCH_MM behind
    it (point is None for these two).
    """
    entry = np.asarray(entry, dtype=float)
    target = np.asarray(target, dtype=float)
    u = unit3(target - entry)
    if not _inside(field, entry)[0]:
        t, pts, inside = _march(field, entry, u, float(np.sqrt(dot3(target - entry, target - entry))))
        hits = np.nonzero(inside)[0]
        if len(hits) == 0:
            return None, 0.0, "no_bone"
        point, offset = pts[hits[0]], float(t[hits[0]])
    else:
        t, pts, inside = _march(field, entry, -u, MAX_SEARCH_MM)
        out = np.nonzero(~inside)[0]
        if len(out) == 0:
            return None, -MAX_SEARCH_MM, "cortex_not_found"
        point, offset = pts[out[0] - 1], -float(t[out[0] - 1])
    return point, offset, (None if _outer_surface(field, point, -u) else "entry_not_outer")


def exit_crossing(field: Volume, start, target) -> Tuple[Optional[np.ndarray], Optional[str]]:
    """Where the axis from ``start`` through ``target`` leaves the bone at
    the far cortex near ``target``: the last bone point before the axis
    exits, searched from the target (forward up to MAX_SEARCH_MM if the
    target is in bone, back toward ``start`` otherwise), so gaps earlier
    along the axis (a joint) are not mistaken for the far cortex.

    Returns (point, problem): (None, None) if not found; problem
    "exit_not_outer" when bone resumes within MAX_SEARCH_MM beyond it (a
    gap inside the bone, not its far surface)."""
    start = np.asarray(start, dtype=float)
    target = np.asarray(target, dtype=float)
    u = unit3(target - start)
    if _inside(field, target)[0]:
        t, pts, inside = _march(field, target, u, MAX_SEARCH_MM)
        out = np.nonzero(~inside)[0]
        if len(out) == 0:
            return None, None
        point = pts[out[0] - 1]
    else:
        t, pts, inside = _march(field, target, -u, float(np.sqrt(dot3(target - start, target - start))))
        hits = np.nonzero(inside)[0]
        if len(hits) == 0:
            return None, None
        point = pts[hits[0]]
    return point, (None if _outer_surface(field, point, u) else "exit_not_outer")


def inward_normal(field: Volume, point) -> Optional[np.ndarray]:
    """Unit vector from a cortex point toward the centroid of the bone voxel
    centres within NORMAL_RADIUS_MM of it: the cortex's inward normal there.
    The centroid is taken from exact integer index sums, so it does not
    depend on summation order."""
    point = np.asarray(point, dtype=float)
    sp = np.asarray(field.spacing, dtype=float)
    org = np.asarray(field.origin, dtype=float)
    c = _nearest_voxel(field, point[None])[0]
    h = np.ceil(NORMAL_RADIUS_MM / sp).astype(np.int64)
    nz, ny, nx = field.array.shape
    lo = np.maximum(c - h, 0)
    hi = np.minimum(c + h, np.array([nx, ny, nz]) - 1)
    if np.any(hi < lo):
        return None
    kk, jj, ii = np.nonzero(field.array[lo[2]:hi[2] + 1, lo[1]:hi[1] + 1, lo[0]:hi[0] + 1] > 0)
    i, j, k = ii + lo[0], jj + lo[1], kk + lo[2]
    dx = (org[0] + i * sp[0]) - point[0]
    dy = (org[1] + j * sp[1]) - point[1]
    dz = (org[2] + k * sp[2]) - point[2]
    near = dx * dx + dy * dy + dz * dz <= NORMAL_RADIUS_MM * NORMAL_RADIUS_MM
    count = int(np.count_nonzero(near))
    if count == 0:
        return None
    mean = [float(int(idx[near].sum())) / count for idx in (i, j, k)]
    d = np.array([org[a] + mean[a] * sp[a] - point[a] for a in range(3)])
    n = float(np.sqrt(dot3(d, d)))
    return d / n if n > 1e-9 else None


def zone_length_mm(radius_mm: float, margin_mm: float, cos_angle: float) -> float:
    """Stretch of screw, from a crossing, checked against the exemption field:
    (r + m + tolerance) / cos(angle), capped at the 60 degree value."""
    return (radius_mm + margin_mm + CORTEX_DEPTH_TOLERANCE_MM) / max(cos_angle, COS_OBLIQUE)


def angle_deg(cos_angle: float) -> float:
    return float(np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0))))


def box_half_mm(radius_mm: float, margin_mm: float, spacing) -> float:
    """Half-size of the box an exemption field is computed in. Every sample
    it serves lies within max(2 (r + m + tolerance), MAX_PROTRUSION_MM) of
    the box centre, so the box edge is always at least r + m plus two voxel
    diagonals beyond any of them: values below r + m (the only ones that
    decide a breach) are exact, and larger ones are never reported below
    r + m."""
    diag = float(np.sqrt(dot3(spacing, spacing)))
    return 3.0 * (radius_mm + margin_mm) + 2.0 * CORTEX_DEPTH_TOLERANCE_MM + MAX_PROTRUSION_MM + 2.0 * diag


def exempt_field(field: Volume, planes, half_mm: float) -> Volume:
    """Distance (mm) to the nearest non-bone voxel that is NOT exempt, where a
    voxel is exempt when it lies outside any of ``planes`` (a list of
    (point, outward normal)) or less than CORTEX_DEPTH_TOLERANCE_MM inside
    one. Computed exactly in a box of ``half_mm`` around the first plane's
    point, clipped to the image, plus a one-voxel border that counts as
    non-bone (like everything beyond the image) unless exempt. The returned
    grid includes the border."""
    point0 = np.asarray(planes[0][0], dtype=float)
    sp = np.asarray(field.spacing, dtype=float)
    org = np.asarray(field.origin, dtype=float)
    c = _nearest_voxel(field, point0[None])[0]
    h = np.ceil(half_mm / sp).astype(np.int64)
    nz, ny, nx = field.array.shape
    lo = np.maximum(c - h, 0)
    hi = np.minimum(c + h, np.array([nx, ny, nz]) - 1)
    solid = np.zeros((hi[2] - lo[2] + 3, hi[1] - lo[1] + 3, hi[0] - lo[0] + 3), dtype=bool)
    solid[1:-1, 1:-1, 1:-1] = field.array[lo[2]:hi[2] + 1, lo[1]:hi[1] + 1, lo[0]:hi[0] + 1] > 0
    x = org[0] + np.arange(lo[0] - 1, hi[0] + 2) * sp[0]
    y = org[1] + np.arange(lo[1] - 1, hi[1] + 2) * sp[1]
    z = org[2] + np.arange(lo[2] - 1, hi[2] + 2) * sp[2]
    for p, n in planes:
        hx = (x - float(p[0])) * float(n[0])
        hy = (y - float(p[1])) * float(n[1])
        hz = (z - float(p[2])) * float(n[2])
        height = (hx[None, None, :] + hy[None, :, None]) + hz[:, None, None]
        solid |= height > -CORTEX_DEPTH_TOLERANCE_MM
    dist = distance_transform_edt(solid, sampling=(sp[2], sp[1], sp[0]))
    return Volume(dist, field.spacing, tuple(org + (lo - 1) * sp))
