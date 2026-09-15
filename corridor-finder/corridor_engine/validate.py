"""Live validation of a single candidate screw axis.

This is the function both the Slicer module (on every handle move) and the
exported JS viewer (in a re-implemented form, see viewer/app.js) call to
answer "is this screw still safe?". Keeping the algorithm here small and
literal makes the JS port easy to keep in sync.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

from .volume import Volume


@dataclass
class Validation:
    min_clearance_mm: float
    worst_point_xyz: Tuple[float, float, float]
    breach: bool
    length_mm: float
    length_in_bone_mm: float
    traversed_labels: List[int] = field(default_factory=list)
    sample_step_mm: float = 1.0


def _axis_samples(entry, target, step_mm: float) -> np.ndarray:
    entry = np.asarray(entry, dtype=float)
    target = np.asarray(target, dtype=float)
    length = float(np.linalg.norm(target - entry))
    n = max(2, int(round(length / step_mm)) + 1)
    t = np.linspace(0.0, 1.0, n).reshape(-1, 1)
    return entry + t * (target - entry)


def validate_screw(
    entry,
    target,
    diameter_mm: float,
    margin_mm: float,
    edt_volume: Volume,
    labels_volume: Volume,
    step_mm: float = 1.0,
) -> Validation:
    """Check a screw of given diameter/margin along entry->target.

    edt_volume: an EDT-in-mm Volume built with corridor_engine.edt.bone_edt_mm
                on the bone union relevant to this screw.
    labels_volume: the integer label Volume, same grid, for traversed-label
                   and gap reporting.
    """
    points = _axis_samples(entry, target, step_mm)
    edt_vals = edt_volume.sample_trilinear(points, order=1)
    label_vals = labels_volume.sample_trilinear(points, order=0)

    radius = diameter_mm / 2.0
    # clearance = distance from the screw surface to the nearest cortex.
    # breach if that clearance is less than the required safety margin.
    clearance = edt_vals - radius
    worst_idx = int(np.argmin(clearance))
    min_clearance = float(clearance[worst_idx])
    breach = min_clearance < margin_mm

    traversed = sorted({int(v) for v in np.unique(label_vals) if v != 0})
    in_bone = label_vals != 0
    # length_in_bone approximated as (fraction of samples inside any labelled
    # bone) * total length -- coarse but adequate for reporting.
    total_length = float(np.linalg.norm(np.asarray(target, dtype=float) - np.asarray(entry, dtype=float)))
    length_in_bone = total_length * (float(np.count_nonzero(in_bone)) / len(in_bone))

    return Validation(
        min_clearance_mm=min_clearance,
        worst_point_xyz=tuple(points[worst_idx]),
        breach=breach,
        length_mm=total_length,
        length_in_bone_mm=length_in_bone,
        traversed_labels=traversed,
        sample_step_mm=step_mm,
    )
