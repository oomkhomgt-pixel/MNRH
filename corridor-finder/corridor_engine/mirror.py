"""The mirror plane: what "anatomical position" means for a displaced pelvis.

displacement-finder DECISIONS 2.1 and 2.1a, and corridor-finder DECISIONS
3.3: the reference for a displaced hemipelvis is the intact one, mirrored
across a plane fitted to what the injury has not displaced. That is **L5
and the central sacrum** (S1 body and canal) when the sacrum is intact, and
**L5 alone** when it is fractured, because a fractured sacrum is part of the
injury and cannot be asked what "unfractured" is.

**Which one is used is measured, pre-selected and confirmed**, the same
pattern as the SI joint in corridor-finder DECISIONS 2.4. The plane is
fitted both ways every time. Adding the central sacrum costs fit on a
normal pelvis too (about 0.6 mm on 274 normal CTPelvic1K pelvises), and
more on the four surgeon-read sacral fractures (0.73-0.99 mm), so "sacrum
fractured" is pre-selected when the penalty reaches
SACRUM_FRACTURE_PENALTY_MM. Nothing is reported off a reference until the
surgeon has confirmed or overridden that, and every result records which
reference was used and whether it was the pre-selection.

**The fit.** The plane minimises the mean closest-point distance between
the reference structure's voxels and their own reflection, started from the
scanner's x axis and from the structure's three inertia axes, since a
single start can settle on a plane through the vertebra's long axis
instead. The reference sets, the point sampling and the cost are exactly
those the 2.1a calibration was measured with (L5 = the lowest 35 mm of the
lumbar label; central sacrum = the sacrum within 20 mm of its median x,
over its whole height; 4000 voxel centres; mean uncapped distance): the
penalty threshold is a number in that measurement, and would mean nothing
under another. That measurement has a floor of its own: on an exactly
symmetric phantom its self-symmetry median is about 1.2 mm (L5) and 1.8 mm
(L5 + central sacrum), the spacing of 4000 points drawn from the larger
set. And its central sacrum is a strip along the scanner's x axis, not the
patient's: on the phantom turned 6 degrees that strip alone pulls the
plane 1 degree toward the scanner, and on a patient lying turned it adds
to the penalty. So the cost and the self-symmetry are kept from it, for the
pre-selection and the guard, and the plane that is used is then refined on
REFINE_POINTS points with the strip taken about the plane itself.

**The gate.** Measured sane fits come out 1.9-7.4 degrees off the patient's
inter-hip axis (the line between the two hip centroids). Across 278
pelvises, 3 L5-alone fits came out 71-77 degrees off (0 of 278 with the
central sacrum added). A plane more than MAX_MIRROR_TILT_DEG off is
refused; when that is the pre-selected one, the other is pre-selected with
a warning, and the surgeon confirms as always.

**Uncertainty** (DECISIONS 2.3). How far the mirrored hemipelvis moves when
the reference changes from one set to the other is the error the choice of
reference alone can put into every number, so it travels with every number
derived from the plane.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import minimize
from scipy.spatial import cKDTree

from . import segmentation as seg
from .volume import Volume

REFERENCES = ("l5", "l5_and_central_sacrum", "central_sacrum")
# What the surgeon's rule chooses between (DECISIONS 2.1): fractured -> L5 alone.
REFERENCE_FOR_SACRUM = {True: "l5", False: "l5_and_central_sacrum"}

# PROPOSED, NOT SETTLED (displacement-finder DECISIONS 2.1a): calibrated on
# 274 normal CTPelvic1K pelvises and the 4 surgeon-read sacral fractures, it
# pre-selects all 4 fractures and 14% of normals. Four fractures are not a
# calibration; it works as a pre-selection only because every case is
# confirmed. Do not tune it on the four CLINIC cases.
SACRUM_FRACTURE_PENALTY_MM = 0.70

MAX_MIRROR_TILT_DEG = 15.0  # measured sane fits 1.9-7.4; failures 71-77
# Good L5 fits read 1.6-3.0 mm at the 90th percentile (5th-95th percentile
# over 278 pelvises), the three failed ones 4.8-6.4 mm. A second guard that
# warns rather than refuses: 4 good L5 fits and 12 good L5 + central sacrum
# fits of those 278 read over it too.
SELF_SYMMETRY_WARN_P90_MM = 4.0

# The reference sets and sampling of the 2.1a calibration; change them and
# SACRUM_FRACTURE_PENALTY_MM and the gate's figures have to be re-measured.
L5_HEIGHT_MM = 35.0  # the lumbar label within this of its lowest point is L5
CENTRAL_SACRUM_HALF_WIDTH_MM = 20.0  # body and canal, either side of the sacrum's median x
FIT_POINTS = 4000  # voxel centres drawn for the fit (seeded, so a case always fits the same)
REFINE_POINTS = 30000  # voxel centres the used plane is refined on
REFINE_ROUNDS = 3  # the strip about the plane, and the plane from the strip, this many times
SAMPLE_MM = 2.0  # surface points are thinned to one per cube of this size
SURFACE_PERCENTILE = 90.0  # the spread across references, over the hemipelvis surface


class MirrorRefused(ValueError):
    """No plane can be fitted, or the one asked for was refused."""


class ReferenceNotConfirmed(MirrorRefused):
    """The surgeon has not confirmed whether the sacrum is fractured."""


def surface_points(vol: Volume, mask: np.ndarray, sample_mm: float = SAMPLE_MM) -> np.ndarray:
    """World (x, y, z) of the mask's surface voxels, thinned to one per cube
    of ``sample_mm``, so point density does not depend on the scan."""
    surface = mask & ~ndi.binary_erosion(mask)
    points = vol.mask_voxel_centers_world(surface)
    if points.shape[0] == 0:
        return points
    _, keep = np.unique(np.floor(points / sample_mm).astype(np.int64), axis=0, return_index=True)
    return points[np.sort(keep)]


def _centroid(vol: Volume, mask: np.ndarray) -> Optional[np.ndarray]:
    idx = np.argwhere(mask)
    if idx.shape[0] == 0:
        return None
    return vol.zyx_indices_to_world(idx.mean(axis=0)[None, :])[0]


def reference_mask(labels_vol: Volume, reference: str, about: Optional[tuple] = None) -> np.ndarray:
    """The voxels a reference set is made of (REFERENCES). The central
    sacrum is the strip within CENTRAL_SACRUM_HALF_WIDTH_MM of the sacrum's
    median x, as calibrated, or of the plane ``about`` = (normal, offset)."""
    if reference not in REFERENCES:
        raise ValueError(f"reference must be one of {REFERENCES}, got {reference!r}")
    labels = labels_vol.array
    lumbar = labels == seg.LUMBAR
    if not lumbar.any():
        raise MirrorRefused("there is no lumbar spine in the labels, and every reference is placed from L5")
    z = labels_vol.origin[2] + np.arange(labels.shape[0]) * labels_vol.spacing[2]
    lumbar_z = z[lumbar.any(axis=(1, 2))]
    l5 = lumbar & (z <= lumbar_z.min() + L5_HEIGHT_MM)[:, None, None]
    if reference == "l5":
        return l5
    sacrum = labels == seg.SACRUM
    if not sacrum.any():
        raise MirrorRefused("there is no sacrum in the labels")
    x = labels_vol.origin[0] + np.arange(labels.shape[2]) * labels_vol.spacing[0]
    if about is None:
        median_x = float(np.median(x[np.nonzero(sacrum)[2]]))
        central = sacrum & (np.abs(x - median_x) <= CENTRAL_SACRUM_HALF_WIDTH_MM)[None, None, :]
    else:
        idx = np.argwhere(sacrum)
        side = labels_vol.zyx_indices_to_world(idx) @ about[0] - about[1]
        keep = idx[np.abs(side) <= CENTRAL_SACRUM_HALF_WIDTH_MM]
        central = np.zeros(labels.shape, dtype=bool)
        central[tuple(keep.T)] = True
    return central if reference == "central_sacrum" else (central | l5)


def reflection_matrix(normal: np.ndarray, offset_mm: float) -> np.ndarray:
    """The 4x4 reflection across the plane {x : normal . x = offset_mm}."""
    n = np.asarray(normal, dtype=float)
    n = n / np.linalg.norm(n)
    out = np.eye(4)
    out[:3, :3] -= 2.0 * np.outer(n, n)
    out[:3, 3] = 2.0 * offset_mm * n
    return out


@dataclass
class MirrorPlane:
    reference: str
    normal: np.ndarray  # unit, pointing toward the patient's right
    offset_mm: float  # the plane is {x : normal . x = offset_mm}
    cost_mm: float  # the calibrated fit's mean closest-point cost (what the penalty compares)
    self_symmetry_p50_mm: float  # in the calibrated measurement, as the guard's figures are
    self_symmetry_p90_mm: float
    tilt_deg: float  # off the patient's inter-hip axis
    n_points: int
    refused: str = ""  # why the gate refused it; empty when it passed
    warning: str = ""

    def matrix(self) -> np.ndarray:
        return reflection_matrix(self.normal, self.offset_mm)

    def reflect(self, points: np.ndarray) -> np.ndarray:
        m = self.matrix()
        return np.asarray(points, dtype=float) @ m[:3, :3].T + m[:3, 3]


def _hip_axis(labels_vol: Volume) -> np.ndarray:
    right = _centroid(labels_vol, labels_vol.array == seg.HIP_R)
    left = _centroid(labels_vol, labels_vol.array == seg.HIP_L)
    if right is None or left is None:
        raise MirrorRefused("both hip bones are needed to check the plane against the patient")
    axis = right - left
    return axis / np.linalg.norm(axis)


def _normal(azimuth: float, elevation: float) -> np.ndarray:
    return np.array([np.cos(elevation) * np.cos(azimuth), np.cos(elevation) * np.sin(azimuth), np.sin(elevation)])


def _fit(points: np.ndarray) -> tuple:
    """Plane (normal, offset, cost) minimising the mean closest-point
    distance between the points and their reflection, multi-start."""
    if points.shape[0] > FIT_POINTS:
        points = points[np.random.default_rng(0).choice(points.shape[0], FIT_POINTS, replace=False)]
    tree = cKDTree(points)

    def cost(p):
        n = _normal(p[0], p[1])
        reflected = points - 2.0 * ((points @ n) - p[2])[:, None] * n[None, :]
        return float(np.mean(tree.query(reflected)[0]))

    axes = np.linalg.svd(points - points.mean(axis=0), full_matrices=False)[2]
    best = None
    for n0 in [np.array([1.0, 0.0, 0.0]), axes[0], axes[1], axes[2]]:
        n0 = n0 / np.linalg.norm(n0)
        start = [np.arctan2(n0[1], n0[0]), np.arcsin(np.clip(n0[2], -1, 1)), float(points.mean(axis=0) @ n0)]
        result = minimize(cost, start, method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-5, "maxiter": 2000})
        if best is None or result.fun < best[2]:
            best = (_normal(result.x[0], result.x[1]), float(result.x[2]), float(result.fun))
    n, d, c = best
    if n[0] < 0:  # point it toward the patient's right, for a readable record
        n, d = -n, -d
    return n, d, c


def _refine(points: np.ndarray, normal: np.ndarray, offset: float) -> tuple:
    """The plane refitted on denser points, from where the calibrated fit
    left it: a sparse random draw is not itself symmetric, and on the
    phantom that alone tilts the plane by up to 0.6 degrees."""
    if points.shape[0] > REFINE_POINTS:
        points = points[np.random.default_rng(2).choice(points.shape[0], REFINE_POINTS, replace=False)]
    tree = cKDTree(points)

    def cost(p):
        n = _normal(p[0], p[1])
        reflected = points - 2.0 * ((points @ n) - p[2])[:, None] * n[None, :]
        return float(np.mean(tree.query(reflected)[0]))

    start = [np.arctan2(normal[1], normal[0]), np.arcsin(np.clip(normal[2], -1, 1)), offset]
    result = minimize(cost, start, method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-6, "maxiter": 2000,
                      "initial_simplex": np.array(start) + np.array([[0, 0, 0], [0.01, 0, 0], [0, 0.01, 0], [0, 0, 0.5]])})
    n, d = _normal(result.x[0], result.x[1]), float(result.x[2])
    if n[0] < 0:
        n, d = -n, -d
    return n, d


def _self_symmetry(points: np.ndarray, normal: np.ndarray, offset: float) -> np.ndarray:
    """Each point's distance from the reference's own reflection."""
    if points.shape[0] > FIT_POINTS:
        points = points[np.random.default_rng(1).choice(points.shape[0], FIT_POINTS, replace=False)]
    return cKDTree(points).query(points - 2.0 * ((points @ normal) - offset)[:, None] * normal[None, :])[0]


def fit_plane(labels_vol: Volume, reference: str) -> MirrorPlane:
    """Fit the mirror plane to one reference set, and gate it on its tilt
    off the patient's inter-hip axis. A refused plane is returned with the
    reason, so both fits can always be shown side by side."""
    def points_of(about=None):
        if reference == "l5_and_central_sacrum":
            # L5's points then the sacrum's, the order the calibration drew
            # its 4000 from: the penalty moves by about 0.04 mm with the draw.
            return np.vstack([labels_vol.mask_voxel_centers_world(reference_mask(labels_vol, part, about))
                              for part in ("l5", "central_sacrum")])
        return labels_vol.mask_voxel_centers_world(reference_mask(labels_vol, reference, about))

    points = points_of()
    if points.shape[0] < 300:
        raise MirrorRefused(f"the {reference} reference has only {points.shape[0]} voxels")
    normal, offset, cost = _fit(points)
    dist = _self_symmetry(points, normal, offset)
    p50, p90 = (float(v) for v in np.percentile(dist, [50, 90]))
    for _ in range(REFINE_ROUNDS if reference != "l5" else 1):
        normal, offset = _refine(points_of((normal, offset)), normal, offset)
    tilt = float(np.degrees(np.arccos(min(1.0, abs(float(np.dot(normal, _hip_axis(labels_vol))))))))
    refused = ""
    if tilt > MAX_MIRROR_TILT_DEG:
        refused = (f"the {reference} plane is {tilt:.1f} degrees off the line between the hips, over the "
                   f"{MAX_MIRROR_TILT_DEG:.0f} degree gate (sane fits are 1.9-7.4)")
    warning = ""
    if p90 > SELF_SYMMETRY_WARN_P90_MM:
        warning = (f"the {reference} reference is not symmetric about its own plane: 90th percentile "
                   f"{p90:.1f} mm, where good fits read 1.6-3.0 mm")
    return MirrorPlane(reference, normal, float(offset), cost, p50, p90, tilt, int(points.shape[0]), refused, warning)


def _disagreement_mm(a: MirrorPlane, b: MirrorPlane, points: np.ndarray) -> float:
    """How far apart the two planes put the mirrored hemipelvis."""
    return float(np.percentile(np.linalg.norm(a.reflect(points) - b.reflect(points), axis=1), SURFACE_PERCENTILE))


@dataclass
class MirrorReference:
    """Both fits and the pre-selection, before the surgeon has confirmed."""

    fits: Dict[str, MirrorPlane]
    penalty_mm: float  # cost(L5 + central sacrum) - cost(L5 alone)
    sacrum_fractured_preselected: bool
    reference_preselected: Optional[str]  # None when the gate refused both
    disagreement_mm: float  # the two planes, over the hemipelvis surface
    warnings: List[str] = field(default_factory=list)

    def preselection_sentence(self) -> str:
        verdict = "fractured" if self.sacrum_fractured_preselected else "intact"
        return (f"sacrum pre-selected as {verdict}: adding the central sacrum costs {self.penalty_mm:.2f} mm of fit "
                f"(pre-selects fractured from {SACRUM_FRACTURE_PENALTY_MM:.2f} mm, a proposed threshold); "
                f"reference pre-selected: {self.reference_preselected or 'none, the gate refused both'}")


def fit_reference(labels_vol: Volume) -> MirrorReference:
    """Fit the plane both ways and pre-select (DECISIONS 2.1a). Nothing is
    used until confirm()."""
    fits = {name: fit_plane(labels_vol, name) for name in ("l5", "l5_and_central_sacrum")}
    hips = surface_points(labels_vol, np.isin(labels_vol.array, (seg.HIP_L, seg.HIP_R)))
    return preselect(fits, _disagreement_mm(fits["l5"], fits["l5_and_central_sacrum"], hips))


def preselect(fits: Dict[str, MirrorPlane], disagreement_mm: float) -> MirrorReference:
    """The pre-selection from the two fits: the rule's reference, or the
    other one with a warning when the gate refused the rule's."""
    penalty = fits["l5_and_central_sacrum"].cost_mm - fits["l5"].cost_mm
    fractured = bool(penalty >= SACRUM_FRACTURE_PENALTY_MM)
    preferred = REFERENCE_FOR_SACRUM[fractured]
    other = REFERENCE_FOR_SACRUM[not fractured]
    warnings = [f.warning for f in fits.values() if f.warning]
    if not fits[preferred].refused:
        chosen = preferred
    elif not fits[other].refused:
        chosen = other
        warnings.append(f"{fits[preferred].refused}; {other} pre-selected instead")
    else:
        chosen = None
        warnings.append(f"{fits['l5'].refused}; {fits['l5_and_central_sacrum'].refused}")
    return MirrorReference(fits, float(penalty), fractured, chosen, float(disagreement_mm), warnings)


@dataclass
class ConfirmedMirror:
    """The plane that numbers are reported off, and how it was chosen."""

    plane: MirrorPlane
    reference: str
    sacrum_fractured: bool  # as confirmed by the surgeon
    choice: str  # "pre-selection" or "override"
    uncertainty_mm: float  # carried on every number derived from the plane
    penalty_mm: float
    warnings: List[str] = field(default_factory=list)

    def sentence(self) -> str:
        return (f"mirrored across the {self.reference.replace('_', ' ')} plane ({self.choice}; sacrum confirmed "
                f"{'fractured' if self.sacrum_fractured else 'intact'}), {self.plane.tilt_deg:.1f} degrees off the "
                f"inter-hip axis, reference uncertainty {self.uncertainty_mm:.1f} mm")


def confirm(ref: MirrorReference, sacrum_fractured: Optional[bool], reference: Optional[str] = None) -> ConfirmedMirror:
    """The surgeon's confirmation. ``sacrum_fractured`` must be declared
    (None refuses, with the pre-selection in the reason: never a silent
    default). ``reference`` follows the rule from it unless given, which is
    how the other plane is chosen when the gate refused the rule's one."""
    if sacrum_fractured is None:
        raise ReferenceNotConfirmed(
            "whether the sacrum is fractured has not been confirmed, so no reference is used; "
            + ref.preselection_sentence())
    if reference is None:
        reference = REFERENCE_FOR_SACRUM[bool(sacrum_fractured)]
    if reference not in ref.fits:
        raise MirrorRefused(f"reference must be one of {tuple(ref.fits)}, got {reference!r}")
    plane = ref.fits[reference]
    if plane.refused:
        others = [name for name, f in ref.fits.items() if name != reference and not f.refused]
        hint = f"; {others[0]} passed the gate and can be chosen explicitly" if others else ""
        raise MirrorRefused(plane.refused + hint)
    agrees = bool(sacrum_fractured) == ref.sacrum_fractured_preselected and reference == ref.reference_preselected
    warnings = list(ref.warnings)
    other = [f for name, f in ref.fits.items() if name != reference]
    if other and not other[0].refused:
        uncertainty = ref.disagreement_mm
    else:
        # With the other plane refused there is no spread to measure; the
        # plane's own asymmetry is the best available stand-in.
        uncertainty = plane.self_symmetry_p90_mm
        warnings.append("the other reference was refused, so the uncertainty is this plane's own "
                        "self-symmetry (90th percentile), not the spread between references")
    return ConfirmedMirror(plane, reference, bool(sacrum_fractured), "pre-selection" if agrees else "override",
                           float(uncertainty), ref.penalty_mm, warnings)
