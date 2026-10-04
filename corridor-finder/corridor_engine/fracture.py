"""The fracture as a surface, from the points the surgeon marks on it.

DECISIONS.md 7.12: an LC-2 / supra-acetabular screw that cannot reach the
far cortex within the chosen length must at least cross the fracture, with
32 mm of screw beyond it (a partially threaded screw's whole thread, or a
fully threaded screw's purchase). "Beyond it" needs the fracture as a
surface, not a point, so the surgeon marks three or more points along it and
a plane is fitted through them. When virtual reduction lands, the surface
between the fragments replaces the clicks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

MIN_POINTS = 3
# Three points almost on one line do not say which way the fracture runs:
# the plane's second extent (its second singular value, in mm) must be at
# least this.
MIN_SPREAD_MM = 3.0
# A screw crosses the fracture where it crosses the plane, but only near
# where the fracture was marked: the plane runs on for ever, the fracture
# does not.
NEAR_MARKS_MM = 20.0


@dataclass
class FracturePlane:
    point: np.ndarray  # a point on the plane (the marks' centroid), world mm
    normal: np.ndarray  # unit normal
    marks: np.ndarray  # (n, 3) the marked points it was fitted to
    rms_mm: float  # how far the marks sit off the plane, root mean square


def fit_plane(points: Sequence[Sequence[float]]) -> Optional[FracturePlane]:
    """The plane through three or more marked points, or None when there
    are too few or they lie nearly on one line."""
    marks = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(marks) < MIN_POINTS:
        return None
    centroid = marks.mean(axis=0)
    _, singular, vt = np.linalg.svd(marks - centroid)
    spread = singular / np.sqrt(len(marks))
    if spread[1] < MIN_SPREAD_MM:
        return None
    normal = vt[2] / np.linalg.norm(vt[2])
    rms = float(np.sqrt(np.mean(((marks - centroid) @ normal) ** 2)))
    return FracturePlane(point=centroid, normal=normal, marks=marks, rms_mm=rms)


# A fracture gap counts as bone (the surgeon, 2026-10-04: crossing a
# fracture is not a breach; any gap near his marks). The gap is the empty
# space within GAP_MARK_REACH_MM of a mark that has the same bone on both
# sides of it across the marked fracture (along the plane's normal, within
# GAP_ACROSS_MM): the space between fragments, not the outside of the bone
# next to the fracture.
GAP_MARK_REACH_MM = 25.0
GAP_ACROSS_MM = 40.0


def fracture_gap(labels: np.ndarray, spacing, origin, label: int, marks) -> Optional[np.ndarray]:
    """The empty voxels of the fracture gap in bone ``label`` near ``marks``
    (3 or more, spread out), as a boolean mask on the labels' grid; None
    when the marks give no plane."""
    plane = fit_plane(marks)
    if plane is None:
        return None
    marks = plane.marks
    sx, sy, sz = (float(v) for v in spacing)
    ox, oy, oz = (float(v) for v in origin)
    sampling = np.array([sz, sy, sx])
    reach = GAP_MARK_REACH_MM
    lo_xyz, hi_xyz = marks.min(axis=0) - reach, marks.max(axis=0) + reach
    lo = np.maximum(np.floor((np.array([lo_xyz[2] - oz, lo_xyz[1] - oy, lo_xyz[0] - ox])) / sampling).astype(int), 0)
    hi = np.minimum(np.ceil((np.array([hi_xyz[2] - oz, hi_xyz[1] - oy, hi_xyz[0] - ox])) / sampling).astype(int) + 1,
                    labels.shape)
    out = np.zeros(labels.shape, dtype=bool)
    if (hi <= lo).any():
        return out
    kk, jj, ii = np.meshgrid(*(np.arange(a, b) for a, b in zip(lo, hi)), indexing="ij")
    empty = labels[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] == 0
    idx = np.stack([kk[empty], jj[empty], ii[empty]], axis=1)
    if not len(idx):
        return out
    xyz = np.stack([ox + idx[:, 2] * sx, oy + idx[:, 1] * sy, oz + idx[:, 0] * sz], axis=1)
    d = np.full(len(xyz), np.inf)
    for m in marks:
        d = np.minimum(d, np.linalg.norm(xyz - m, axis=1))
    near = d <= reach
    idx, xyz = idx[near], xyz[near]
    step = float(min(spacing))
    plus = np.zeros(len(xyz), dtype=bool)
    minus = np.zeros(len(xyz), dtype=bool)
    for k in range(1, int(np.ceil(GAP_ACROSS_MM / step)) + 1):
        for sign, hit in ((1.0, plus), (-1.0, minus)):
            p = xyz + sign * k * step * plane.normal
            zyx = np.rint(np.stack([(p[:, 2] - oz) / sz, (p[:, 1] - oy) / sy, (p[:, 0] - ox) / sx], axis=1)).astype(int)
            ok = np.all((zyx >= 0) & (zyx < np.array(labels.shape)), axis=1)
            hit[ok] |= labels[zyx[ok, 0], zyx[ok, 1], zyx[ok, 2]] == label
    gap = idx[plus & minus]
    out[gap[:, 0], gap[:, 1], gap[:, 2]] = True
    return out


def marks_near(points, a, b, within_mm: float) -> np.ndarray:
    """The marks within ``within_mm`` of the segment a-b: the fracture this
    screw is about, not another one marked elsewhere on the same bone."""
    marks = np.asarray(points, dtype=float).reshape(-1, 3)
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    ab = b - a
    t = np.clip(((marks - a) @ ab) / max(float(ab @ ab), 1e-9), 0.0, 1.0)
    d = np.linalg.norm(marks - (a + t[:, None] * ab), axis=1)
    return marks[d <= within_mm]


def off_square_deg(plane: FracturePlane, direction) -> float:
    """How far a screw along ``direction`` is from square to the fracture:
    0 when it runs along the plane's normal, 90 when it lies in the plane."""
    u = np.asarray(direction, dtype=float)
    u = u / np.linalg.norm(u)
    return float(np.degrees(np.arccos(min(1.0, abs(float(u @ plane.normal))))))


def past_fracture_mm(plane: FracturePlane, start, tip) -> Optional[float]:
    """How much of the screw, from its entry cortex ``start`` to its ``tip``,
    lies beyond the fracture: the distance along the screw from where it
    crosses the plane to the tip. None when it does not cross the plane
    between start and tip, or crosses it far from every mark."""
    start, tip = np.asarray(start, dtype=float), np.asarray(tip, dtype=float)
    a = float((start - plane.point) @ plane.normal)
    b = float((tip - plane.point) @ plane.normal)
    if a == b or a * b > 0:
        return None
    t = a / (a - b)
    crossing = start + t * (tip - start)
    if np.min(np.linalg.norm(plane.marks - crossing, axis=1)) > NEAR_MARKS_MM:
        return None
    return float((1.0 - t) * np.linalg.norm(tip - start))
