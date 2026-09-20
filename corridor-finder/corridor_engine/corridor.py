"""Auto-suggest search for the widest safe screw corridor between two
anatomical regions.

The search works in four stages:
  1. Candidate entries on the bone surface of the entry region; candidate
     targets in the bone interior of the exit region (tips that stay
     inside bone) or on its surface (tips through the far cortex).
  2. Coarse pass: the minimum distance-field value along every candidate
     entry-target axis, leaving out the stretches next to a crossed cortex
     that the breach rule treats separately (vectorized trilinear sampling).
  3. Local refinement: nudge the best axes on a small grid, each time moving
     the entry back onto the cortex where the nudged axis crosses it.
  4. Every suggestion is checked with validate.validate_screw, exactly as
     the plan will check it: the largest diameter with no breach and a
     catalogue length in the corridor's range is the suggestion. So a
     suggested screw that "fits" is precisely one the plan validates as safe.

Everything here operates on plain numpy arrays and corridor_engine.volume.
Volume objects -- no Slicer/VTK/Qt dependency, so this is fully unit
testable with synthetic phantoms (see corridor_engine.phantoms and
tests/python/test_corridor_*.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import cortex
from .validate import Validation, validate_screw
from .volume import Volume

Vec3 = Tuple[float, float, float]

DEFAULT_DIAMETERS_MM = (3.5, 4.5, 6.5, 7.0, 7.3)
_CATALOG_STEP_MM = 5.0
# Warnings that make a suggestion unusable: the screw could not be placed
# the way the corridor intends.
_BLOCKING_WARNINGS = {"no_bone", "entry_cortex_not_found", "entry_not_outer", "exit_not_found", "exit_not_outer", "no_catalog_length"}


@dataclass
class ScrewChoice:
    diameter_mm: Optional[float]
    length_mm: Optional[float]
    fits: bool


@dataclass
class CorridorResult:
    entry_xyz: Vec3  # on the entry cortex
    target_xyz: Vec3  # "inside": the tip; "through": near the far cortex
    direction: Vec3
    length_mm: float  # entry cortex to the target (or to the far cortex)
    r_safe_mm: float  # largest screw radius clearing the margin on this axis
    min_edt_mm: float  # smallest (exemption-aware) distance-field value on the axis
    screw: ScrewChoice
    traversed_labels: List[int] = field(default_factory=list)
    alignment_score: float = 0.0
    tip_rule: str = "inside"
    # validate_screw's result for the suggested screw or, when none fits, for
    # the diameter that best shows why (checked_diameter_mm).
    validation: Optional[Validation] = None
    checked_diameter_mm: Optional[float] = None
    # When nothing fits: "too_narrow", "length" (no catalogue length suits
    # the axis), "too_short" (no axis of the corridor's length range was
    # found) or "blocked" (wide enough, but something about the entry or the
    # tip stops it -- validation.warnings says what).
    reason: Optional[str] = None
    # What this suggestion is, when it is not simply the widest one found:
    # "longest on this line".
    note: Optional[str] = None


def _surface_shell(mask: np.ndarray) -> np.ndarray:
    """Boolean mask of voxels on the boundary of ``mask`` (in it, but with
    at least one 6-connected neighbor outside it)."""
    from scipy.ndimage import binary_erosion

    eroded = binary_erosion(mask, iterations=1, border_value=0)
    return mask & ~eroded


def _points_in_sphere(mask: np.ndarray, vol: Volume, center_xyz, radius_mm: float, max_points: int, rng) -> np.ndarray:
    points = vol.mask_voxel_centers_world(mask)
    if points.shape[0]:
        points = points[np.linalg.norm(points - np.asarray(center_xyz, dtype=float), axis=1) <= radius_mm]
    if points.shape[0] > max_points:
        points = points[rng.choice(points.shape[0], size=max_points, replace=False)]
    return points


def region_candidates(label_mask: np.ndarray, edt_vol: Volume, center_xyz: Sequence[float], radius_mm: float, max_points: int = 400, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """World-space candidate points: the surface of ``label_mask`` within a
    sphere around ``center_xyz``. Subsampled to at most ``max_points``."""
    rng = rng or np.random.default_rng(0)
    return _points_in_sphere(_surface_shell(label_mask), edt_vol, center_xyz, radius_mm, max_points, rng)


def interior_candidates(label_mask: np.ndarray, edt_vol: Volume, center_xyz: Sequence[float], radius_mm: float, min_edt_mm: float, max_points: int = 400, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """World-space candidate tips: voxels of ``label_mask`` within the sphere
    that lie at least ``min_edt_mm`` inside the bone. When the region is too
    thin for that, its deepest part (at least half its greatest depth), so
    the search can still report why nothing fits."""
    rng = rng or np.random.default_rng(0)
    points = _points_in_sphere(label_mask & (edt_vol.array >= min_edt_mm), edt_vol, center_xyz, radius_mm, max_points, rng)
    if points.shape[0] == 0:
        region = _points_in_sphere(label_mask, edt_vol, center_xyz, radius_mm, np.iinfo(np.int64).max, rng)
        if region.shape[0]:
            depth = edt_vol.sample_trilinear(region, order=0)
            points = region[depth >= 0.5 * depth.max()]
            if points.shape[0] > max_points:
                points = points[rng.choice(points.shape[0], size=max_points, replace=False)]
    return points


def _catalog(diameters: Sequence[float], catalog_lengths_mm: Optional[Dict[float, Sequence[float]]], length_range_mm) -> Dict[float, List[float]]:
    """Per diameter, the catalogue lengths inside the corridor's range (a
    5 mm catalogue when none is given)."""
    lo, hi = length_range_mm if length_range_mm else (0.0, np.inf)
    out = {}
    for d in diameters:
        if catalog_lengths_mm is not None:
            lengths = [float(v) for v in catalog_lengths_mm.get(d, catalog_lengths_mm.get(float(d), []))]
        else:
            top = hi if np.isfinite(hi) else 500.0
            lengths = [float(v) for v in np.arange(_CATALOG_STEP_MM, top + 1e-9, _CATALOG_STEP_MM)]
        out[d] = [v for v in lengths if lo - 1e-9 <= v <= hi + 1e-9]
    return out


def search_corridor(
    entry_mask: np.ndarray,
    exit_mask: np.ndarray,
    entry_center_xyz: Sequence[float],
    entry_radius_mm: float,
    exit_center_xyz: Sequence[float],
    exit_radius_mm: float,
    edt_vol: Volume,
    valid_vol: Optional[Volume] = None,
    labels_vol: Optional[Volume] = None,
    margin_mm: float = 2.0,
    screw_diameters_mm: Optional[Sequence[float]] = None,
    length_range_mm: Optional[Tuple[float, float]] = None,
    textbook_direction: Optional[Sequence[float]] = None,
    *,
    tip_rule: str = "inside",
    catalog_lengths_mm: Optional[Dict[float, Sequence[float]]] = None,
    n_entry: int = 150,
    n_exit: int = 150,
    n_samples_coarse: int = 24,
    n_samples_refine: int = 48,
    top_k: int = 3,
    refine_step_mm: float = 3.0,
    refine_iterations: int = 2,
    n_validate: int = 20,
    seed: int = 0,
) -> List[CorridorResult]:
    """Search for the widest safe corridor(s) between two anatomical regions.

    entry_mask/exit_mask: boolean arrays on the same grid as edt_vol.array,
        restricting candidates to a named bone (e.g. hip).
    valid_vol: optional boolean Volume (uint8) that a candidate axis must
        stay inside end-to-end (e.g. a dilated bone union tolerant of a
        small SI-joint cartilage gap).
    tip_rule: "inside" or "through" (DECISIONS.md 1.5), as in corridors.json.
    catalog_lengths_mm: {diameter: lengths} of the screw library; a 5 mm
        catalogue when omitted. Only lengths inside ``length_range_mm`` are
        suggested.
    A result "fits" only when validate_screw finds no breach for its
    diameter and catalogue length.
    """
    rng = np.random.default_rng(seed)
    diameters = sorted(screw_diameters_mm or DEFAULT_DIAMETERS_MM)
    catalog = _catalog(diameters, catalog_lengths_mm, length_range_mm)
    r_min, r_max = diameters[0] / 2.0, diameters[-1] / 2.0
    # Stretch next to a crossed cortex that the coarse score leaves out: the
    # square-on exemption zone of the largest screw.
    zone = r_max + margin_mm + cortex.CORTEX_DEPTH_TOLERANCE_MM
    through = tip_rule == "through"
    # Axis lengths, entry cortex to target, that can give a screw in range:
    # an "inside" target at least the shortest length away (and not beyond
    # the longest by more than a catalogue step), a "through" far cortex
    # within reach of the longest length and within a step of the shortest.
    if length_range_mm is None:
        len_lo, len_hi = 0.0, np.inf
    elif through:
        len_lo, len_hi = length_range_mm[0] - _CATALOG_STEP_MM, length_range_mm[1]
    else:
        len_lo, len_hi = length_range_mm[0], length_range_mm[1] + _CATALOG_STEP_MM

    entries = region_candidates(entry_mask, edt_vol, entry_center_xyz, entry_radius_mm, n_entry, rng)
    if through:
        exits = region_candidates(exit_mask, edt_vol, exit_center_xyz, exit_radius_mm, n_exit, rng)
    else:
        exits = interior_candidates(exit_mask, edt_vol, exit_center_xyz, exit_radius_mm, r_min + margin_mm, n_exit, rng)
    if entries.shape[0] == 0 or exits.shape[0] == 0:
        return []

    def axis_scores(entry: np.ndarray, targets: np.ndarray, n_samples: int) -> np.ndarray:
        """Per target, the smallest field value along the axis outside the
        cortex zones; -inf if the axis leaves valid_vol or is too short to
        have any such stretch."""
        t = np.linspace(0.0, 1.0, n_samples)
        rays = entry[None, None, :] + t[None, :, None] * (targets - entry)[:, None, :]
        flat = rays.reshape(-1, 3)
        vals = edt_vol.sample_trilinear(flat, order=1).reshape(targets.shape[0], n_samples)
        length = np.linalg.norm(targets - entry, axis=1)
        s = t[None, :] * length[:, None]
        keep = s >= zone
        if through:
            keep &= s <= (length - zone)[:, None]
        score = np.where(keep, vals, np.inf).min(axis=1)
        score[~keep.any(axis=1)] = -np.inf
        if valid_vol is not None:
            ok = (valid_vol.sample_trilinear(flat, order=0).reshape(targets.shape[0], n_samples) > 0).all(axis=1)
            score[~ok] = -np.inf
        return score

    def coarse() -> List[Tuple[float, np.ndarray, np.ndarray]]:
        """For every entry point (a surface voxel, within about a voxel of
        where its axis crosses the cortex), the best target."""
        found = []
        for e in entries:
            scores = axis_scores(e, exits, n_samples_coarse)
            lengths = np.linalg.norm(exits - e, axis=1)
            scores[(lengths < len_lo - 2.0) | (lengths > len_hi + 2.0)] = -np.inf
            i = int(np.argmax(scores))
            if np.isfinite(scores[i]):
                found.append((float(scores[i]), e.copy(), exits[i].copy()))
        return found

    best = coarse()
    relaxed = False
    if not best and len_lo > 0:
        # No axis long enough: search again without the minimum, so the
        # results can show the corridor and say it is too short.
        len_lo, relaxed = 0.0, True
        best = coarse()
    if not best:
        return []
    best.sort(key=lambda item: item[0], reverse=True)
    keep = best[: max(top_k * 20, 40)]

    def refined(e: np.ndarray, x: np.ndarray) -> Tuple[float, Optional[np.ndarray]]:
        """Score of the axis through e and x, and that axis's crossing of the
        entry cortex (None when it has none)."""
        start, _offset, problem = cortex.entry_crossing(edt_vol, e, x)
        if problem is not None:
            return -np.inf, None
        length = float(np.sqrt(cortex.dot3(x - start, x - start)))
        if not (max(len_lo, 1.0) <= length <= len_hi):
            return -np.inf, None
        return float(axis_scores(start, x[None, :], n_samples_refine)[0]), start

    # Local refinement: coordinate descent over entry and target nudges,
    # the entry always put back on the cortex.
    offsets = np.array([(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)], dtype=float) * refine_step_mm
    axes: List[Tuple[float, np.ndarray, np.ndarray]] = []
    for _score0, e0, x0 in keep:
        score, e = refined(e0, x0)
        if e is None:
            continue
        x = x0
        for _ in range(refine_iterations):
            for move_entry in (True, False):
                for o in offsets:
                    e_try, x_try = (e + o, x) if move_entry else (e, x + o)
                    s_try, start = refined(e_try, x_try)
                    if s_try > score:
                        score, e, x = s_try, start, x_try
        axes.append((score, e, x))
    axes.sort(key=lambda item: item[0], reverse=True)

    textbook = np.asarray(textbook_direction, dtype=float) if textbook_direction is not None else None
    if textbook is not None and np.linalg.norm(textbook) > 0:
        textbook = textbook / np.linalg.norm(textbook)

    # Exact check of the best distinct axes, as the plan will check them.
    results: List[CorridorResult] = []
    for _score, e, x in axes:
        if len(results) >= n_validate:
            break
        unit = cortex.unit3(x - e)
        if any(np.linalg.norm(unit - np.asarray(r.direction)) < 0.05 and np.linalg.norm(e - np.asarray(r.entry_xyz)) < 5.0 for r in results):
            continue
        results.append(_check_axis(e, x, unit, diameters, catalog, margin_mm, edt_vol, labels_vol, tip_rule, textbook))

    if relaxed:
        for r in results:
            if not r.screw.fits:
                r.reason = "too_short"
    results.sort(key=lambda r: (r.screw.fits, r.screw.diameter_mm or 0.0, r.r_safe_mm, r.length_mm, r.alignment_score), reverse=True)
    return results[:top_k]


def _check_axis(e, x, unit, diameters, catalog, margin_mm, edt_vol, labels_vol, tip_rule, textbook) -> CorridorResult:
    """The largest diameter validate_screw passes on this axis with a
    catalogue length in range; otherwise why none does."""
    chosen = None
    tried = []
    for d in sorted(diameters, reverse=True):
        v = validate_screw(e, x, d, margin_mm, edt_vol, labels_vol, tip_rule=tip_rule, catalog_lengths_mm=catalog[d])
        if not v.breach and not (_BLOCKING_WARNINGS & set(v.warning_codes)):
            chosen = (d, v)
            break
        tried.append((d, v))
    if chosen is not None:
        d, v = chosen
        # An "inside" screw's target handle goes to its tip, so validating
        # the plan's handles gives exactly this screw again.
        target = np.asarray(v.tip_xyz) if v.exit_xyz is None else np.asarray(x)
        screw = ScrewChoice(diameter_mm=d, length_mm=v.length_mm, fits=True)
        reason = None
    else:
        # Why nothing fits. Among the diameters made in a length that suits
        # this axis, the thinnest (best clearance) says how narrow it is; if
        # no diameter comes in a suitable length, the length is the reason.
        made = [
            (dd, vv)
            for dd, vv in tried
            if "no_catalog_length" not in vv.warning_codes
            and not (vv.protrusion_mm is not None and vv.protrusion_mm > cortex.MAX_PROTRUSION_MM)
        ]
        target = np.asarray(x)
        if made:
            d, v = made[-1]
            # The thinnest diameter that is made in a suitable length says
            # what is wrong: too little room, or room enough but an entry or
            # a tip the rules refuse. Calling the second one "too narrow"
            # sent the surgeon looking for a narrower screw that does not
            # exist, on a corridor wide enough for a 7 mm one.
            blocked = _BLOCKING_WARNINGS & set(v.warning_codes)
            reason = "blocked" if (not v.breach and blocked) else "too_narrow"
            screw = ScrewChoice(diameter_mm=None, length_mm=None, fits=False)
        else:
            d, v = tried[0]
            reason = "length"
            # A diameter alone is not a fit: it is kept (so the UI can say
            # "too short") but never paired with a non-catalogue length.
            screw = ScrewChoice(diameter_mm=d, length_mm=None, fits=False)
    reach = np.asarray(v.exit_xyz) if v.exit_xyz is not None else np.asarray(x)
    return CorridorResult(
        entry_xyz=tuple(float(c) for c in e),
        target_xyz=tuple(float(c) for c in target),
        direction=tuple(float(c) for c in unit),
        length_mm=float(np.linalg.norm(reach - np.asarray(e))),
        r_safe_mm=float(v.min_clearance_mm + d / 2.0 - margin_mm),
        min_edt_mm=float(v.min_clearance_mm + d / 2.0),
        screw=screw,
        traversed_labels=list(v.traversed_labels),
        alignment_score=float(np.dot(unit, textbook)) if textbook is not None else 0.0,
        tip_rule=tip_rule,
        validation=v,
        checked_diameter_mm=d,
        reason=reason,
    )
