"""Live validation of a single screw.

This is what the Slicer module calls on every handle move, and what the
exported viewer re-implements in viewer/clearance.js; report.py reads its
result. The three must stay identical.

The rule (DECISIONS.md section 1):
- The screw starts where its axis crosses the outer cortex (the entry
  handle need not sit exactly on it) and runs a catalogue length from there:
  the longest that ends before the target handle ("inside" corridors), or
  the shortest that reaches past the far cortex near the target handle
  ("through" corridors, which then protrude up to one catalogue step).
- Clearance = distance from the screw's surface to the outer surface of the
  bone. Breach = clearance below the screw's OWN margin, not merely below 0.
- Near the entry crossing, and for "through" corridors near the far-cortex
  crossing and at most MAX_PROTRUSION_MM past it, the non-bone outside that
  cortex is ignored (cortex.py). Everywhere else the plain distance field is
  used, so an "inside" tip keeps its full margin.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from . import cortex
from .volume import Volume

TIP_RULES = ("inside", "through")
# An entry handle this far off the cortex is reported (the screw still starts
# at the cortex crossing).
HANDLE_OFF_CORTEX_WARN_MM = 2.0
# A screw whose start on the outer cortex cannot be found is never reported
# safe: part of its path is unchecked (report.py and clearance.js agree).
UNCHECKED_ENTRY_CODES = ("entry_cortex_not_found", "entry_not_outer")
_LENGTH_EPS_MM = 1e-9


@dataclass
class Validation:
    min_clearance_mm: float
    worst_point_xyz: Tuple[float, float, float]
    breach: bool
    length_mm: float  # implant length, from the entry cortex to the tip
    length_in_bone_mm: float
    traversed_labels: List[int] = field(default_factory=list)
    sample_step_mm: float = 1.0
    tip_rule: str = "inside"
    start_xyz: Optional[Tuple[float, float, float]] = None  # entry cortex crossing
    tip_xyz: Optional[Tuple[float, float, float]] = None
    entry_handle_offset_mm: float = 0.0  # > 0: handle outside the cortex; < 0: inside it
    entry_angle_deg: Optional[float] = None  # axis vs the entry cortex normal
    entry_zone_mm: float = 0.0  # stretch checked against the entry exemption field
    exit_xyz: Optional[Tuple[float, float, float]] = None  # far-cortex crossing ("through")
    exit_angle_deg: Optional[float] = None
    exit_zone_mm: float = 0.0
    protrusion_mm: Optional[float] = None  # tip past the far cortex ("through")
    warnings: List[str] = field(default_factory=list)
    # Stable identifiers of the warnings, also produced by viewer/clearance.js.
    warning_codes: List[str] = field(default_factory=list)


def choose_implant_length(distance_mm: float, tip_rule: str, lengths_mm: Sequence[float]) -> Optional[float]:
    """The catalogue length for a screw whose cortex-to-target distance is
    ``distance_mm``: the longest not beyond it for tips that stay inside
    bone, the shortest reaching it for tips through the far cortex
    (DECISIONS.md 1.6). None when the catalogue has no such length."""
    if tip_rule == "through":
        fitting = [float(v) for v in lengths_mm if float(v) >= distance_mm - _LENGTH_EPS_MM]
        return min(fitting) if fitting else None
    fitting = [float(v) for v in lengths_mm if float(v) <= distance_mm + _LENGTH_EPS_MM]
    return max(fitting) if fitting else None


def validate_screw(
    entry,
    target,
    diameter_mm: float,
    margin_mm: float,
    edt_volume: Volume,
    labels_volume: Optional[Volume],
    step_mm: float = 1.0,
    *,
    tip_rule: str = "inside",
    catalog_lengths_mm: Optional[Sequence[float]] = None,
) -> Validation:
    """Validate a screw of the given diameter and margin whose axis runs from
    the entry handle toward the target handle.

    edt_volume: distance field (mm) of the bone this screw's corridor may
        use (corridor_engine.edt.bone_edt_mm; bone = field > 0).
    labels_volume: integer labels on the same grid, for reporting (optional).
    tip_rule: "inside" (the tip stays in bone with the full margin) or
        "through" (the tip passes the far cortex near the target handle).
    catalog_lengths_mm: the lengths this diameter comes in. Without it (or
        when none suits) the screw runs exactly to the target handle, or to
        the far cortex, and the latter case is reported as a warning.
    """
    if tip_rule not in TIP_RULES:
        raise ValueError(f"unknown tip_rule {tip_rule!r}")
    entry = np.asarray(entry, dtype=float)
    target = np.asarray(target, dtype=float)
    if not (np.all(np.isfinite(entry)) and np.all(np.isfinite(target))) or cortex.dot3(target - entry, target - entry) <= 0.0:
        raise ValueError("the entry and target handles must be distinct points")
    radius = diameter_mm / 2.0
    warnings: List[str] = []
    codes: List[str] = []

    def warn(code: str, text: str) -> None:
        codes.append(code)
        warnings.append(text)

    u = cortex.unit3(target - entry)
    start, offset, problem = cortex.entry_crossing(edt_volume, entry, target)
    if problem == "no_bone":
        warn("no_bone", "the screw axis does not enter bone before the target handle")
        start, offset = entry, 0.0
    elif problem == "cortex_not_found":
        warn(
            "entry_cortex_not_found",
            f"the entry handle is inside bone with no cortex within {cortex.MAX_SEARCH_MM:.0f} mm behind it; "
            "the screw cannot be checked from its entry (move the entry handle to the bone surface)",
        )
        start, offset = entry, 0.0
    elif problem == "entry_not_outer":
        warn(
            "entry_not_outer",
            "the axis enters this bone from a gap inside it (a joint, canal or foramen), not through its outer "
            "cortex; the gap is not exempted (move the entry handle to the outer cortex)",
        )
    elif abs(offset) > HANDLE_OFF_CORTEX_WARN_MM:
        side = "outside" if offset > 0 else "inside"
        warn("handle_off_cortex", f"entry handle is {abs(offset):.1f} mm {side} the cortex; the screw starts where its axis crosses it")

    planes = {}  # zone name -> (point, outward normal)
    entry_angle = exit_angle = exit_xyz = protrusion = s_exit = None
    entry_zone = exit_zone = 0.0
    if problem is None:
        n_in = cortex.inward_normal(edt_volume, start)
        if n_in is None:
            n_in = u
        cos_e = cortex.dot3(u, n_in)
        entry_angle = cortex.angle_deg(cos_e)
        entry_zone = cortex.zone_length_mm(radius, margin_mm, cos_e)
        planes["entry"] = (start, -n_in)
        if cos_e < cortex.COS_OBLIQUE:
            warn("entry_oblique", f"entry too oblique: {entry_angle:.0f} degrees to the cortex normal")
        if tip_rule == "through":
            x, x_problem = cortex.exit_crossing(edt_volume, start, target)
            if x is None:
                warn("exit_not_found", "far cortex not found near the target handle; the tip is kept inside bone")
            elif x_problem == "exit_not_outer":
                warn(
                    "exit_not_outer",
                    "the far cortex near the target handle is a gap inside the bone (a joint, canal or foramen), "
                    "not its outer surface; the tip is kept inside bone",
                )
            else:
                n_x = cortex.inward_normal(edt_volume, x)
                n_out = -u if n_x is None else -n_x
                cos_x = cortex.dot3(u, n_out)
                exit_angle = cortex.angle_deg(cos_x)
                exit_zone = cortex.zone_length_mm(radius, margin_mm, cos_x)
                planes["exit"] = (x, n_out)
                exit_xyz = tuple(float(v) for v in x)
                s_exit = cortex.dot3(x - start, u)
                if cos_x < cortex.COS_OBLIQUE:
                    warn("exit_oblique", f"far-cortex crossing too oblique: {exit_angle:.0f} degrees to the cortex normal")

    length_rule = "through" if s_exit is not None else "inside"
    distance = s_exit if s_exit is not None else float(np.sqrt(cortex.dot3(target - start, target - start)))
    length = distance
    if catalog_lengths_mm is not None:
        chosen = choose_implant_length(distance, length_rule, catalog_lengths_mm)
        if chosen is None:
            warn("no_catalog_length", f"no catalogue length for {diameter_mm} mm fits {distance:.1f} mm")
        else:
            length = chosen
    tip = start + length * u
    if s_exit is not None:
        protrusion = length - s_exit

    n = max(2, int(round(length / step_mm)) + 1)
    s = length * np.arange(n) / (n - 1)
    points = start + s[:, None] * u
    in_entry = s < entry_zone if "entry" in planes else np.zeros(n, dtype=bool)
    if "exit" in planes:
        in_exit = (s > s_exit - exit_zone) & (s <= s_exit + cortex.MAX_PROTRUSION_MM)
    else:
        in_exit = np.zeros(n, dtype=bool)

    values = edt_volume.sample_trilinear(points, order=1)
    half = cortex.box_half_mm(radius, margin_mm, edt_volume.spacing)
    for sel, names in ((in_entry & ~in_exit, ["entry"]), (~in_entry & in_exit, ["exit"]), (in_entry & in_exit, ["entry", "exit"])):
        if np.any(sel):
            exempt = cortex.exempt_field(edt_volume, [planes[k] for k in names], half)
            values[sel] = exempt.sample_trilinear(points[sel], order=1)

    clearance = values - radius
    worst_idx = int(np.argmin(clearance))
    min_clearance = float(clearance[worst_idx])
    breach = min_clearance < margin_mm or any(c in UNCHECKED_ENTRY_CODES for c in codes)

    traversed: List[int] = []
    length_in_bone = 0.0
    if labels_volume is not None:
        label_vals = labels_volume.sample_trilinear(points, order=0)
        traversed = sorted({int(v) for v in np.unique(label_vals) if v != 0})
        length_in_bone = length * float(np.count_nonzero(label_vals != 0)) / len(label_vals)

    return Validation(
        min_clearance_mm=min_clearance,
        worst_point_xyz=tuple(float(v) for v in points[worst_idx]),
        breach=breach,
        length_mm=float(length),
        length_in_bone_mm=length_in_bone,
        traversed_labels=traversed,
        sample_step_mm=step_mm,
        tip_rule=tip_rule,
        start_xyz=tuple(float(v) for v in start),
        tip_xyz=tuple(float(v) for v in tip),
        entry_handle_offset_mm=float(offset),
        entry_angle_deg=entry_angle,
        entry_zone_mm=float(entry_zone),
        exit_xyz=exit_xyz,
        exit_angle_deg=exit_angle,
        exit_zone_mm=float(exit_zone),
        protrusion_mm=None if protrusion is None else float(protrusion),
        warnings=warnings,
        warning_codes=codes,
    )
