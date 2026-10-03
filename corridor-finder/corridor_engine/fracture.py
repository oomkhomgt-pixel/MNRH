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
