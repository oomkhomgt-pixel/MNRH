"""Auto-suggest search for the widest safe screw corridor between two
anatomical regions.

The search works in three stages:
  1. Sample candidate entry/exit points from the surface of each region.
  2. Coarse pass: evaluate the minimum EDT clearance along every candidate
     entry-exit ray, vectorized with scipy's trilinear sampling.
  3. Local refinement: nudge the best few axes on a small grid to settle
     into a nearby local optimum.

Everything here operates on plain numpy arrays and corridor_engine.volume.
Volume objects — no Slicer/VTK/Qt dependency, so this is fully unit
testable with synthetic phantoms (see corridor_engine.phantoms and
tests/python/test_corridor_*.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .volume import Volume

Vec3 = Tuple[float, float, float]


@dataclass
class ScrewChoice:
    diameter_mm: Optional[float]
    length_mm: Optional[float]
    fits: bool


@dataclass
class CorridorResult:
    entry_xyz: Vec3
    target_xyz: Vec3
    direction: Vec3
    length_mm: float
    r_safe_mm: float
    min_edt_mm: float
    screw: ScrewChoice
    traversed_labels: List[int] = field(default_factory=list)
    alignment_score: float = 0.0


def _surface_shell(mask: np.ndarray) -> np.ndarray:
    """Boolean mask of voxels on the boundary of ``mask`` (in it, but with
    at least one 6-connected neighbor outside it)."""
    from scipy.ndimage import binary_erosion

    eroded = binary_erosion(mask, iterations=1, border_value=0)
    return mask & ~eroded


def _sphere_region(volume_shape_mask: np.ndarray, edt_vol: Volume, center_xyz: np.ndarray, radius_mm: float) -> np.ndarray:
    """A boolean mask selecting voxels of ``volume_shape_mask`` within
    ``radius_mm`` of ``center_xyz`` (world coordinates)."""
    points = edt_vol.mask_voxel_centers_world(volume_shape_mask)
    if points.shape[0] == 0:
        return np.zeros_like(volume_shape_mask)
    d = np.linalg.norm(points - center_xyz.reshape(1, 3), axis=1)
    keep_flat = d <= radius_mm
    out = np.zeros_like(volume_shape_mask)
    idx = np.argwhere(volume_shape_mask)
    out[tuple(idx[keep_flat].T)] = True
    return out


def region_candidates(label_mask: np.ndarray, edt_vol: Volume, center_xyz: Sequence[float], radius_mm: float, max_points: int = 400, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """World-space candidate points: the surface of ``label_mask`` within a
    sphere around ``center_xyz``. Subsampled to at most ``max_points``.
    """
    rng = rng or np.random.default_rng(0)
    shell = _surface_shell(label_mask)
    region = _sphere_region(shell, edt_vol, np.asarray(center_xyz, dtype=float), radius_mm)
    points = edt_vol.mask_voxel_centers_world(region)
    if points.shape[0] == 0:
        return points
    if points.shape[0] > max_points:
        idx = rng.choice(points.shape[0], size=max_points, replace=False)
        points = points[idx]
    return points


def _axis_min_edt_batch(entry: np.ndarray, exits: np.ndarray, edt_vol: Volume, valid_vol: Optional[Volume], n_samples: int) -> Tuple[np.ndarray, np.ndarray]:
    """For one entry point vs many exit points, return (min_edt, all_valid)
    arrays of shape (n_exit,): the minimum EDT sampled along each ray, and
    whether every sample on that ray fell inside ``valid_vol`` (if given).
    """
    t = np.linspace(0.0, 1.0, n_samples).reshape(1, n_samples, 1)
    entry_b = entry.reshape(1, 1, 3)
    exits_b = exits.reshape(-1, 1, 3)
    rays = entry_b + t * (exits_b - entry_b)  # (n_exit, n_samples, 3)
    flat = rays.reshape(-1, 3)
    edt_vals = edt_vol.sample_trilinear(flat, order=1).reshape(exits.shape[0], n_samples)
    min_edt = edt_vals.min(axis=1)
    if valid_vol is not None:
        valid_vals = valid_vol.sample_trilinear(flat, order=0).reshape(exits.shape[0], n_samples)
        all_valid = (valid_vals > 0).all(axis=1)
    else:
        all_valid = np.ones(exits.shape[0], dtype=bool)
    return min_edt, all_valid


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
    n_entry: int = 150,
    n_exit: int = 150,
    n_samples_coarse: int = 24,
    n_samples_refine: int = 48,
    top_k: int = 3,
    refine_step_mm: float = 3.0,
    refine_iterations: int = 2,
    seed: int = 0,
) -> List[CorridorResult]:
    """Search for the widest safe corridor(s) between two anatomical regions.

    entry_mask/exit_mask: boolean arrays on the same grid as edt_vol.array,
        restricting candidates to the surface of a named bone (e.g. hip).
    valid_vol: optional boolean Volume (uint8) that a candidate axis must
        stay inside end-to-end (e.g. a dilated bone union tolerant of a
        small SI-joint cartilage gap). If omitted, any axis is geometrically
        allowed and only the EDT-based clearance decides safety.
    """
    rng = np.random.default_rng(seed)
    screw_diameters_mm = sorted(screw_diameters_mm or [3.5, 4.5, 6.5, 7.0, 7.3])

    entries = region_candidates(entry_mask, edt_vol, entry_center_xyz, entry_radius_mm, n_entry, rng)
    exits = region_candidates(exit_mask, edt_vol, exit_center_xyz, exit_radius_mm, n_exit, rng)
    if entries.shape[0] == 0 or exits.shape[0] == 0:
        return []

    # Coarse pass: for every entry point, evaluate all exit candidates.
    best: List[Tuple[float, np.ndarray, np.ndarray]] = []  # (min_edt, entry, exit)
    for e in entries:
        min_edt, all_valid = _axis_min_edt_batch(e, exits, edt_vol, valid_vol, n_samples_coarse)
        lengths = np.linalg.norm(exits - e.reshape(1, 3), axis=1)
        ok = all_valid.copy()
        if length_range_mm is not None:
            lo, hi = length_range_mm
            ok &= (lengths >= lo * 0.5) & (lengths <= hi * 1.5)  # generous at coarse stage
        if not np.any(ok):
            continue
        idx_local = np.argmax(np.where(ok, min_edt, -np.inf))
        best.append((float(min_edt[idx_local]), e.copy(), exits[idx_local].copy()))

    if not best:
        return []

    best.sort(key=lambda item: item[0], reverse=True)
    keep = best[: max(top_k * 20, 40)]

    # Local refinement: coordinate-descent perturbation of entry/exit points.
    refined: List[Tuple[float, np.ndarray, np.ndarray]] = []
    offsets = np.array(
        [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)],
        dtype=float,
    ) * refine_step_mm
    for score0, e0, x0 in keep:
        e, x, score = e0, x0, score0
        for _ in range(refine_iterations):
            e_candidates = e.reshape(1, 3) + offsets
            scores = np.full(offsets.shape[0], -np.inf)
            for oi, ec in enumerate(e_candidates):
                me, va = _axis_min_edt_batch(ec, x.reshape(1, 3), edt_vol, valid_vol, n_samples_refine)
                if va[0]:
                    scores[oi] = me[0]
            best_oi = int(np.argmax(scores))
            if scores[best_oi] > score:
                e = e_candidates[best_oi]
                score = float(scores[best_oi])

            x_candidates = x.reshape(1, 3) + offsets
            scores = np.full(offsets.shape[0], -np.inf)
            for oi, xc in enumerate(x_candidates):
                me, va = _axis_min_edt_batch(e, xc.reshape(1, 3), edt_vol, valid_vol, n_samples_refine)
                if va[0]:
                    scores[oi] = me[0]
            best_oi = int(np.argmax(scores))
            if scores[best_oi] > score:
                x = x_candidates[best_oi]
                score = float(scores[best_oi])
        refined.append((score, e, x))

    refined.sort(key=lambda item: item[0], reverse=True)

    textbook = np.asarray(textbook_direction, dtype=float) if textbook_direction is not None else None
    if textbook is not None and np.linalg.norm(textbook) > 0:
        textbook = textbook / np.linalg.norm(textbook)

    results: List[CorridorResult] = []
    seen_directions: List[np.ndarray] = []
    for score, e, x in refined:
        direction = x - e
        length = float(np.linalg.norm(direction))
        if length < 1e-6:
            continue
        unit = direction / length
        # de-duplicate near-identical axes among the top results
        if any(np.linalg.norm(unit - u) < 0.05 and np.linalg.norm(e - e2) < 5.0 for u, e2 in zip(seen_directions, [r.entry_xyz for r in results])):
            continue

        r_safe = score - margin_mm
        fitting = [d for d in screw_diameters_mm if d / 2.0 <= r_safe]
        chosen_d = max(fitting) if fitting else None
        chosen_len = None
        if chosen_d is not None:
            lo, hi = length_range_mm if length_range_mm else (0.0, length)
            usable = min(length, hi)
            chosen_len = max(lo, (usable // 5) * 5) if usable >= lo else None

        traversed: List[int] = []
        if labels_vol is not None:
            samples = e.reshape(1, 3) + np.linspace(0, 1, 20).reshape(-1, 1) * direction.reshape(1, 3)
            lab_vals = labels_vol.sample_trilinear(samples, order=0)
            traversed = sorted({int(v) for v in np.unique(lab_vals) if v != 0})

        alignment = float(np.dot(unit, textbook)) if textbook is not None else 0.0

        results.append(
            CorridorResult(
                entry_xyz=tuple(e),
                target_xyz=tuple(x),
                direction=tuple(unit),
                length_mm=length,
                r_safe_mm=float(r_safe),
                min_edt_mm=float(score),
                # A screw fits only if both a diameter and a catalog length do;
                # diameter_mm is kept when only the length fails so the UI can
                # say "too short" rather than "too narrow".
                screw=ScrewChoice(diameter_mm=chosen_d, length_mm=chosen_len, fits=chosen_d is not None and chosen_len is not None),
                traversed_labels=traversed,
                alignment_score=alignment,
            )
        )
        seen_directions.append(unit)
        if len(results) >= top_k * 3:
            break

    results.sort(key=lambda r: (r.r_safe_mm, r.length_mm, r.alignment_score), reverse=True)
    return results[:top_k]
