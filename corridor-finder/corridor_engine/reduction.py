"""Corridors on virtually reduced anatomy (DECISIONS.md 3.4 and 3.6).

The reduction itself -- where each moving unit goes -- comes from the
displacement engine (a mirror start pose refined by congruence of the
fracture and sacroiliac joint surfaces). This module only uses one:

* ``apply_moves`` moves the voxels of each unit by its rigid transform, so
  the corridor search, the breach rule and the DRRs all run on the reduced
  bones exactly as they would on scanned ones;
* ``reduction_warnings`` says where a screw's fit depends on the reduction:
  wherever the reduction's remaining error in a region is larger than the
  screw's spare clearance (clearance minus margin) near that region, the
  screw is still shown, with an amber warning (3.6).

A transform is a 4x4 matrix in world mm (RAS) taking a point of the unit as
scanned to where it lies once reduced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .volume import Volume

# A screw passes through a region when some point of it lies within this
# distance of the region's surface (the SI joint's surfaces, the symphysis,
# a fracture's surfaces). A single centre point is not enough: an
# iliosacral screw crosses the joint 30 mm from its centre on the harness
# phantom. It is a neighbourhood, not a measurement.
REGION_RADIUS_MM = 10.0
# Points per region kept in the plan: enough to say where it is.
RECORD_POINTS = 200


@dataclass
class Move:
    """One moving unit: its voxels as scanned, and where they go."""

    name: str
    mask: np.ndarray  # bool, on the labels' grid (z, y, x)
    transform: np.ndarray  # 4x4, scanned world -> reduced world

    def __post_init__(self):
        self.transform = np.asarray(self.transform, dtype=float).reshape(4, 4)
        if not np.allclose(self.transform[3], [0.0, 0.0, 0.0, 1.0]):
            raise ValueError(f"{self.name}: not an affine transform")
        rot = self.transform[:3, :3]
        if not (np.allclose(rot @ rot.T, np.eye(3), atol=1e-4) and np.linalg.det(rot) > 0):
            raise ValueError(f"{self.name}: not a rigid transform (a reduction moves bone, it does not reshape it)")


@dataclass
class Reduction:
    """A proposed reduction as the corridor tool uses it."""

    moves: List[Move]
    # Remaining error after the fit, mm, per region ("si_right", "si_left",
    # "symphysis", "fracture_<id>") -- in the reduced anatomy. The
    # displacement engine gives max(90th-percentile surface mismatch after
    # the fit, the error measured on phantoms for that kind of region), and
    # float("inf") for a region too little surface pins down
    # ("unconstrained"): that always warns, never reads as safe.
    residual_mm: Dict[str, float]
    # Where each region is: points on its surface (N x 3, or one point),
    # world mm, in the reduced anatomy.
    region_xyz: Dict[str, Sequence]
    source: str = "unspecified"  # who proposed it, for the plan and report
    notes: List[str] = field(default_factory=list)
    # Who accepted this case's reduction on the before/after sheet, and
    # when (DECISIONS.md 3.1; displacement-finder 7c.8). None: not accepted,
    # and nothing may be planned on it.
    accepted_by: Optional[str] = None

    def __post_init__(self):
        # A region with an error but no place, or a place but no error, would
        # silently drop out of the warnings and read as safe.
        missing = sorted(set(self.residual_mm) ^ set(self.region_xyz))
        if missing:
            raise ValueError(f"regions without both an error and a surface: {missing}")
        for k, v in self.residual_mm.items():
            if v is None or np.isnan(float(v)) or float(v) < 0:
                raise ValueError(f"{k}: the reduction's error must be a number >= 0, or inf when unconstrained")

    def record(self) -> dict:
        """What the plan keeps: enough to redo the reduction and to say how
        reliable it is, without the voxel masks. Region surfaces are thinned
        to RECORD_POINTS, so the record SAYS where each region is but is
        never used to recompute warnings: a screw on reduced anatomy is only
        checked while its live Reduction is applied, and a plan read back
        without it marks such screws as unable to pass."""
        return {
            "source": self.source,
            "accepted_by": self.accepted_by,
            "units": [{"name": m.name, "transform": m.transform.tolist(),
                       "voxels": int(m.mask.sum())} for m in self.moves],
            # JSON has no infinity: an unconstrained region is kept as null
            # and named, so a plan read back cannot mistake it for 0.
            "residual_mm": {k: (float(v) if np.isfinite(float(v)) else None) for k, v in self.residual_mm.items()},
            "unconstrained": sorted(k for k, v in self.residual_mm.items() if not np.isfinite(float(v))),
            "region_xyz": {k: _thinned(v).tolist() for k, v in self.region_xyz.items()},
            "region_points": {k: int(len(_points(v))) for k, v in self.region_xyz.items()},
            "notes": list(self.notes),
        }


def _points(v) -> np.ndarray:
    return np.asarray(v, dtype=float).reshape(-1, 3)


def _thinned(v) -> np.ndarray:
    pts = _points(v)
    if len(pts) <= RECORD_POINTS:
        return pts
    return pts[np.linspace(0, len(pts) - 1, RECORD_POINTS).astype(int)]


def _world_grid(vol: Volume, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """World xyz of every voxel centre in the index box [lo, hi) (z, y, x)."""
    kk, jj, ii = np.meshgrid(*(np.arange(a, b) for a, b in zip(lo, hi)), indexing="ij")
    sx, sy, sz = vol.spacing
    ox, oy, oz = vol.origin
    return np.stack([ox + ii * sx, oy + jj * sy, oz + kk * sz], axis=-1)


def _index_box_of(vol: Volume, xyz: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    zyx = vol.world_to_zyx_indices(xyz).T
    lo = np.maximum(np.floor(zyx.min(axis=0)).astype(int) - 1, 0)
    hi = np.minimum(np.ceil(zyx.max(axis=0)).astype(int) + 2, vol.array.shape)
    return lo, hi


def apply_moves(vol: Volume, moves: Sequence[Move], fill=0) -> Tuple[Volume, Dict[str, int]]:
    """``vol`` with each unit's voxels moved by its transform (nearest
    neighbour, pulled back from the destination so nothing is left with
    holes). Where a unit leaves, ``fill``. Returns the moved volume and,
    per unit, how many voxels of it landed on something that was not
    moving -- bone on bone, which a good reduction keeps near zero."""
    src = vol.array
    out = src.copy()
    moving = np.zeros(src.shape, dtype=bool)
    for m in moves:
        if m.mask.shape != src.shape:
            raise ValueError(f"{m.name}: mask is {m.mask.shape}, the volume is {src.shape}")
        moving |= m.mask
    out[moving] = fill
    overlaps: Dict[str, int] = {}
    for m in moves:
        if not m.mask.any():
            overlaps[m.name] = 0
            continue
        idx = np.argwhere(m.mask)
        lo, hi = idx.min(axis=0), idx.max(axis=0) + 1
        corners = np.array([[a, b, c] for a in (lo[0], hi[0]) for b in (lo[1], hi[1]) for c in (lo[2], hi[2])], float)
        corners_xyz = vol.zyx_indices_to_world(corners)
        moved = corners_xyz @ m.transform[:3, :3].T + m.transform[:3, 3]
        dlo, dhi = _index_box_of(vol, moved)
        if (dhi <= dlo).any():
            overlaps[m.name] = 0
            continue
        dest = _world_grid(vol, dlo, dhi).reshape(-1, 3)
        inv = np.linalg.inv(m.transform)
        back = dest @ inv[:3, :3].T + inv[:3, 3]
        zyx = np.rint(vol.world_to_zyx_indices(back).T).astype(int)
        inside = np.all((zyx >= 0) & (zyx < np.array(src.shape)), axis=1)
        hit = np.zeros(len(dest), dtype=bool)
        hit[inside] = m.mask[zyx[inside, 0], zyx[inside, 1], zyx[inside, 2]]
        values = np.zeros(len(dest), dtype=src.dtype)
        values[hit] = src[zyx[hit, 0], zyx[hit, 1], zyx[hit, 2]]
        box = tuple(slice(a, b) for a, b in zip(dlo, dhi))
        target = out[box].reshape(-1)
        static_bone = (src[box].reshape(-1) != fill) & ~moving[box].reshape(-1)
        overlaps[m.name] = int((hit & static_bone).sum())
        target[hit] = values[hit]
        out[box] = target.reshape(out[box].shape)
    return Volume(array=out, spacing=vol.spacing, origin=vol.origin), overlaps


def reduction_warnings(points_xyz: np.ndarray, spare_mm: np.ndarray, reduction: Reduction,
                       radius_mm: float = REGION_RADIUS_MM) -> List[dict]:
    """Where this screw's fit depends on the reduction: for each region the
    screw passes within ``radius_mm`` of, if the reduction's remaining error
    there is larger than the screw's smallest spare clearance (clearance
    minus margin, per point along it) in that neighbourhood. Each warning
    says the region, the error and the spare clearance."""
    points_xyz = np.asarray(points_xyz, dtype=float).reshape(-1, 3)
    spare_mm = np.asarray(spare_mm, dtype=float).reshape(-1)
    out = []
    for region, residual in sorted(reduction.residual_mm.items()):
        surface = _points(reduction.region_xyz[region])
        # Distance from each screw point to the nearest point of the region.
        d = np.full(len(points_xyz), np.inf)
        for chunk in np.array_split(surface, max(1, len(surface) // 2000 + 1)):
            if len(chunk):
                d = np.minimum(d, np.linalg.norm(points_xyz[:, None, :] - chunk[None, :, :], axis=2).min(axis=1))
        near = d <= radius_mm
        if not near.any():
            continue
        spare = float(spare_mm[near].min())
        if float(residual) > spare:
            out.append({"region": region, "residual_mm": float(residual), "spare_mm": spare})
    return out


def _region_words(key: str) -> str:
    """A region key in words. The displacement engine's keys: si_right,
    si_left, symphysis, fracture_<id>, fracture_mark_<k> (a fracture the
    surgeon marked where no surface was found), unit_<name>_unpinned (a
    whole moving unit no trustworthy surface pins)."""
    if key.startswith("unit_") and key.endswith("_unpinned"):
        return "the " + key[len("unit_"):-len("_unpinned")].replace("_", " ") + " (nothing pins where it goes)"
    if key.startswith("fracture_mark_"):
        return "marked fracture " + key[len("fracture_mark_"):] + " (no fracture surface found there)"
    return key.replace("si_", "sacroiliac joint, ").replace("_", " ")


def warning_text(w: dict) -> str:
    region = _region_words(w["region"])
    if not np.isfinite(w["residual_mm"]):
        return (f"fit depends on the reduction: at the {region} the reduction is not pinned down (too little "
                f"facing surface), so this screw's {max(w['spare_mm'], 0.0):.1f} mm to spare cannot be relied on")
    return (f"fit depends on the reduction: at the {region} the reduction is uncertain by "
            f"{w['residual_mm']:.1f} mm (90th-percentile surface mismatch after the fit, or the error measured on "
            f"phantoms, whichever is larger), more than this screw's {max(w['spare_mm'], 0.0):.1f} mm to spare")
