"""Fragments of a displaced hemipelvis, and each one's transform home.

displacement-finder DECISIONS 1.1, 2.4, 3.1-3.3, and the API Corridor
Finder's virtual reduction is built on (corridor-finder DECISIONS 8.4).

**What it cannot be built on** (measured on the four CLINIC cases): each
expert bone label is one connected body plus dust, so connected components
do not find fragments; and a freely fitted surface patch always "fits",
dropping to 1.0-1.8 mm residual under a fabricated 5-14 mm transform, so a
fragment is never accepted because a transform reduced its residual.

**How fragments are found.** The mirrored intact hemipelvis is placed by
the confirmed mirror plane alone (mirror.py). It is never fitted onto the
injured side as a whole first: that would absorb the very displacement
being measured. Surface points of the injured hemipelvis are paired with
the mirrored side's by mutual nearest neighbour, keeping pairs whose
surface normals agree, and register.ransac_rigid finds the largest set of
pairs that one rigid transform explains; pairs are re-made under that
transform until it settles. That body is fragment 0, the main body. Its
points are removed and the search repeats from its transform on what is
left, so fragments 1..k are what one transform cannot explain.

**When a candidate is a fragment.** All of (DECISIONS 3.2):

- at least MIN_FRAGMENT_ACETABULAR_CM3 if it reaches the acetabular
  articular surface, MIN_FRAGMENT_RING_CM3 anywhere else;
- spatially one piece (connectivity as a check, never as the finder);
- its transform differs from its parent's by more than
  max(DISTINCT_TRANSFORM_FACTOR x this case's residual floor, the mirror
  plane's uncertainty), measured as the furthest any of its own surface
  points is moved by the difference. The floor is per case, the 90th
  percentile of the best-fitting 70% of this patient's injured surface
  under the main body's transform, the per-case pattern si_joint.py uses
  instead of a constant.

Before any of that, a piece of a body smaller than the minimum for where
it lies is carried with the neighbour it touches most (3.2): on the phantom
turned 6 degrees, the 5 mm fragment's own piece was exactly the fragment,
but voxel asymmetry left 28 islands of 0.4-1.8 cm3 over the main body that
its transform explained marginally better, and counted as part of it they
failed the one-piece check (85%). A candidate that fails is recorded with
its numbers and carried with the main body, never reported on its own. Fragments of a fragment are not
searched in this slice: every fragment's parent is the main body.

**Every transform is reported twice.** ``to_reference`` carries the
fragment from where it is to where the mirrored intact side says it
belongs: the reduction manoeuvre, with the plane's uncertainty on it.
``to_parent`` carries it to where it belongs relative to its parent as the
parent lies now; any error common to both, the mirror plane's included,
cancels, so this is what a gap and step can be built on. With no intact
side (a bilateral injury, DECISIONS 2.4) there is no reference: the finder
needs one, so nothing is found, and fitting the fractures together is
slice 1b.

**Below the floor** a number is still a number (DECISIONS 1.4): it is
flagged with the floor, never zeroed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from . import segmentation as seg
from .mirror import ConfirmedMirror, MirrorReference, ReferenceNotConfirmed
from .register import invert, point_to_plane, ransac_rigid, transform_points, travel_mm
from .volume import Volume

# DECISIONS 3.2, decided 2026-09-27; to be revised once seen on real cases.
MIN_FRAGMENT_ACETABULAR_CM3 = 0.5  # reaching the acetabular articular surface
MIN_FRAGMENT_RING_CM3 = 2.0  # anywhere else in the ring

DISTINCT_TRANSFORM_FACTOR = 2.0  # x the case's residual floor
FLOOR_BEST_FRACTION = 0.70  # the floor is taken over this best-fitting share of the surface
FLOOR_PERCENTILE = 90.0
INLIER_FACTOR = 2.0  # a pair agrees with a transform within this x the floor
NORMAL_AGREEMENT_DEG = 45.0  # paired surfaces must face within this of each other
MAX_PAIR_MM = 20.0  # no pair is made across more than this
CONNECTED_SHARE = 0.9  # of a candidate's volume in its largest piece
SAMPLE_MM = 2.0  # surface points, one per cube of this size
NORMAL_SMOOTHING_MM = 1.5
MAX_ROUNDS = 30  # re-pairing rounds per body
SETTLED_MM = 0.05  # a body's transform has settled when no point moves more than this
MIN_PAIRS = 30
MAX_FRAGMENTS = 6
ARTICULAR_GAP_MM = 6.0  # hip bone this close to the femoral head is at the joint
FEMUR_BONE_HU = 200.0  # unlabelled bone in the CT, for the femoral head
MIN_FEMUR_CM3 = 20.0  # a femoral head is far larger; smaller is not it
SIDES = ("right", "left", "both")


@dataclass
class Fragment:
    index: int  # 0 is the main body
    parent: Optional[int]  # None for the main body
    mask: np.ndarray  # bool, on the labels grid, where the fragment is now
    volume_cm3: float
    to_reference: Optional[np.ndarray]  # 4x4, current position -> home; None when refused
    to_parent: np.ndarray  # 4x4, current position -> where it belongs on its parent as it lies
    residual_mm: float  # 90th percentile closest-point distance once home
    travel_mm: float  # furthest any of its surface points travels home
    relative_travel_mm: float  # furthest any of its surface points travels under to_parent
    plane_uncertainty_mm: float  # carried by to_reference and travel_mm (DECISIONS 2.3)
    below_floor: bool  # travel_mm under the case's residual floor (DECISIONS 1.4)
    articular: bool  # reaches the acetabular articular surface
    n_points: int


@dataclass
class Candidate:
    """A body the search found and did not promote, with why."""

    volume_cm3: float
    articular: bool
    connected_share: float
    relative_travel_mm: float
    distinct_threshold_mm: float
    reasons: List[str]


@dataclass
class FragmentSet:
    side: str
    reference: str  # which mirror reference set the transforms are measured against
    reference_choice: str  # "pre-selection" or "override"
    fragments: List[Fragment]
    residual_floor_mm: float
    inlier_mm: float
    plane_uncertainty_mm: float
    rejected: List[Candidate] = field(default_factory=list)
    refused: str = ""  # why there is no to_reference, when there is none
    warnings: List[str] = field(default_factory=list)

    def sentence(self) -> str:
        if self.refused:
            return f"{self.side} hemipelvis: {self.refused}"
        moved = [f for f in self.fragments if f.index > 0]
        text = (f"{self.side} hemipelvis: main body travels {self.fragments[0].travel_mm:.1f} mm home"
                f" ({'below' if self.fragments[0].below_floor else 'above'} this case's floor of "
                f"{self.residual_floor_mm:.1f} mm; reference uncertainty {self.plane_uncertainty_mm:.1f} mm)")
        for f in moved:
            text += (f"; fragment {f.index}, {f.volume_cm3:.1f} cm3, {f.relative_travel_mm:.1f} mm off its parent, "
                     f"{f.travel_mm:.1f} mm from home")
        if not moved:
            text += "; one body"
        return text


def _hip_ids(side: str) -> Tuple[int, int]:
    return (seg.HIP_R, seg.HIP_L) if side == "right" else (seg.HIP_L, seg.HIP_R)


def _without_dust(mask: np.ndarray, spacing) -> np.ndarray:
    """Pieces smaller than the smallest fragment there can be are carried
    with their neighbour (DECISIONS 3.2); here they are simply left out."""
    labelled, n = ndi.label(mask)
    if n <= 1:
        return mask
    sizes_cm3 = np.bincount(labelled.ravel())[1:] * float(np.prod(spacing)) / 1000.0
    keep = np.flatnonzero(sizes_cm3 >= MIN_FRAGMENT_ACETABULAR_CM3) + 1
    return np.isin(labelled, keep)


def _surface(vol: Volume, mask: np.ndarray, thin: bool = True) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Surface points (one per SAMPLE_MM cube, or every surface voxel when
    not ``thin``), their outward normals, and their zyx voxel indices."""
    idx = np.argwhere(mask)
    lo = np.maximum(idx.min(axis=0) - 4, 0)
    hi = np.minimum(idx.max(axis=0) + 5, mask.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    sub = mask[box]
    surface = np.argwhere(sub & ~ndi.binary_erosion(sub))
    points = vol.zyx_indices_to_world(surface + lo)
    if thin:
        _, keep = np.unique(np.floor(points / SAMPLE_MM).astype(np.int64), axis=0, return_index=True)
        keep = np.sort(keep)
        surface, points = surface[keep], points[keep]
    sx, sy, sz = vol.spacing
    sigma = [NORMAL_SMOOTHING_MM / s for s in (sz, sy, sx)]
    smooth = ndi.gaussian_filter(sub.astype(np.float32), sigma)
    grads = [ndi.sobel(smooth, axis=a) / s for a, s in zip((2, 1, 0), (sx, sy, sz))]  # d/dx, d/dy, d/dz
    normals = -np.stack([g[tuple(surface.T)] for g in grads], axis=1)
    length = np.linalg.norm(normals, axis=1)
    normals = normals / np.maximum(length, 1e-9)[:, None]
    return points, normals, surface + lo


class _Matcher:
    """Pairs injured-side points with the mirrored intact side's."""

    def __init__(self, target: np.ndarray, target_normals: np.ndarray):
        self.target = target
        self.normals = target_normals
        self.tree = cKDTree(target)
        self.cos = np.cos(np.radians(NORMAL_AGREEMENT_DEG))

    def residual(self, transform, points, normals) -> np.ndarray:
        """Each point's closest-point distance under the transform; inf
        where the closest surface faces the other way."""
        moved = transform_points(transform, points)
        dist, j = self.tree.query(moved)
        facing = np.einsum("ij,ij->i", normals @ transform[:3, :3].T, self.normals[j]) >= self.cos
        return np.where(facing, dist, np.inf)

    def pairs(self, transform, points, normals) -> Tuple[np.ndarray, np.ndarray]:
        """Mutual nearest neighbours under the transform whose normals agree."""
        moved = transform_points(transform, points)
        dist, j = self.tree.query(moved)
        _, back = cKDTree(moved).query(self.target[j])
        rotated = normals @ transform[:3, :3].T
        keep = ((back == np.arange(len(points))) & (dist <= MAX_PAIR_MM)
                & (np.einsum("ij,ij->i", rotated, self.normals[j]) >= self.cos))
        return np.flatnonzero(keep), j[keep]

    def consensus(self, points, normals, init: np.ndarray, inlier_mm: float) -> Optional[np.ndarray]:
        """The transform the largest consistent set of pairs agrees with,
        re-pairing under it until it settles. RANSAC chooses which pairs
        agree; the transform then moves by a point-to-plane step on them.
        None when too few pairs agree."""
        transform = init
        for _ in range(MAX_ROUNDS):
            i, j = self.pairs(transform, points, normals)
            if len(i) < MIN_PAIRS:
                return None
            moved_now = transform_points(transform, points[i])
            _, inliers = ransac_rigid(moved_now, self.target[j], inlier_mm)
            if inliers.sum() < MIN_PAIRS:
                return None
            step = point_to_plane(moved_now[inliers], self.target[j[inliers]], self.normals[j[inliers]])
            transform = step @ transform
            if np.max(np.linalg.norm(transform_points(step, moved_now) - moved_now, axis=1)) < SETTLED_MM:
                break
        return transform


def _floor(residual: np.ndarray) -> float:
    finite = np.sort(residual[np.isfinite(residual)])
    best = finite[: max(1, int(FLOOR_BEST_FRACTION * finite.size))]
    return float(np.percentile(best, FLOOR_PERCENTILE))


def articular_surface(labels_vol: Volume, side: str, ct: Optional[Volume] = None) -> Optional[np.ndarray]:
    """The injured hip's voxels within ARTICULAR_GAP_MM of the femoral head:
    from the femur label when the labels have one, else from unlabelled
    bone in the CT. None when neither shows a femoral head, and then the
    ring minimum applies everywhere."""
    hip_id = _hip_ids(side)[0]
    femur_id = seg.FEMUR_R if side == "right" else seg.FEMUR_L
    labels = labels_vol.array
    hip = labels == hip_id
    if not hip.any():
        return None
    sx, sy, sz = labels_vol.spacing
    voxel_cm3 = sx * sy * sz / 1000.0
    pad = np.ceil(np.array([ARTICULAR_GAP_MM / s for s in (sz, sy, sx)])).astype(int) + 1
    idx = np.argwhere(hip)
    lo, hi = np.maximum(idx.min(axis=0) - pad, 0), np.minimum(idx.max(axis=0) + pad + 1, labels.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    head = labels[box] == femur_id
    if not head.any() and ct is not None:
        bone = (ct.array[box] >= FEMUR_BONE_HU) & (labels[box] == 0)
        near = ndi.distance_transform_edt(~hip[box], sampling=(sz, sy, sx)) <= ARTICULAR_GAP_MM
        pieces, n = ndi.label(bone)
        if n:
            sizes = np.bincount(pieces.ravel())[1:] * voxel_cm3
            touching = np.unique(pieces[near & bone])
            touching = touching[touching > 0]
            big = [t for t in touching if sizes[t - 1] >= MIN_FEMUR_CM3]
            if big:
                head = pieces == max(big, key=lambda t: sizes[t - 1])
    if not head.any():
        return None
    out = np.zeros(labels.shape, dtype=bool)
    out[box] = hip[box] & (ndi.distance_transform_edt(~head, sampling=(sz, sy, sx)) <= ARTICULAR_GAP_MM)
    return out


def find_fragments(labels_vol: Volume, mirror: ConfirmedMirror, injured: str,
                   articular: Optional[np.ndarray] = None) -> FragmentSet:
    """Find the fragments of the ``injured`` hemipelvis ("right" or
    "left"; "both" refuses) against the other side, mirrored across the
    confirmed plane. ``articular`` is the acetabular articular surface
    (articular_surface()); without it the ring minimum applies everywhere."""
    if isinstance(mirror, MirrorReference):
        raise ReferenceNotConfirmed("the mirror reference has not been confirmed (mirror.confirm); "
                                    + mirror.preselection_sentence())
    if injured not in SIDES:
        raise ValueError(f"injured must be one of {SIDES}, got {injured!r}")
    if injured == "both":
        return FragmentSet(injured, mirror.reference, mirror.choice, [], float("nan"), float("nan"),
                           mirror.uncertainty_mm, refused=(
                               "both sides are injured, so there is no intact side to mirror and no transform "
                               "home (DECISIONS 2.4); fragments are found against the mirror, so none are found "
                               "here, and fitting the fractures together is not yet built"))

    labels = labels_vol.array
    spacing = labels_vol.spacing
    voxel_cm3 = float(np.prod(spacing)) / 1000.0
    injured_id, intact_id = _hip_ids(injured)
    if not (labels == injured_id).any() or not (labels == intact_id).any():
        raise ValueError("both hip bones are needed")
    intact = _without_dust(labels == intact_id, spacing)
    # Everything voxel-wise on the injured side happens in a box around it.
    idx = np.argwhere(labels == injured_id)
    lo, hi = np.maximum(idx.min(axis=0) - 2, 0), np.minimum(idx.max(axis=0) + 3, labels.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    box_vol = Volume(labels[box], spacing, tuple(labels_vol.zyx_indices_to_world(lo[None, :])[0]))
    hip = _without_dust(labels[box] == injured_id, spacing)
    box_articular = articular[box] if articular is not None else None
    warnings = list(mirror.warnings)
    if articular is None:
        warnings.append(f"the acetabular articular surface was not located, so the {MIN_FRAGMENT_RING_CM3:.1f} cm3 "
                        f"ring minimum applied everywhere; an acetabular fragment of "
                        f"{MIN_FRAGMENT_ACETABULAR_CM3:.1f}-{MIN_FRAGMENT_RING_CM3:.1f} cm3 would not be reported")

    points, normals, _ = _surface(box_vol, hip)
    # Every surface voxel on the mirrored side, so a closest-point distance
    # is a distance to the surface and not to the nearest sampled point.
    q, qn, _ = _surface(labels_vol, intact, thin=False)
    m = mirror.plane.matrix()
    matcher = _Matcher(transform_points(m, q), qn @ m[:3, :3].T)

    # Stage 0, the main body: placed by the plane alone to start, then the
    # floor is re-measured under its own transform and it is found again.
    min_inlier = max(spacing)
    inlier = max(INLIER_FACTOR * _floor(matcher.residual(np.eye(4), points, normals)), min_inlier)
    main = matcher.consensus(points, normals, np.eye(4), inlier)
    if main is None:
        raise ValueError(f"fewer than {MIN_PAIRS} surface pairs between the injured side and the mirrored intact "
                         f"side agree with one transform (floor under the plane alone {inlier / INLIER_FACTOR:.1f} mm); "
                         "the two hip bones may not be mirror images at all")
    floor = _floor(matcher.residual(main, points, normals))
    inlier = max(INLIER_FACTOR * floor, min_inlier)
    main = matcher.consensus(points, normals, main, inlier)
    distinct = max(DISTINCT_TRANSFORM_FACTOR * floor, mirror.uncertainty_mm)

    bodies = [main]
    explained = matcher.residual(main, points, normals) < inlier
    rejected: List[Candidate] = []
    remaining = ~explained
    while len(bodies) <= MAX_FRAGMENTS and remaining.sum() >= MIN_PAIRS:
        rest = np.flatnonzero(remaining)
        found = matcher.consensus(points[rest], normals[rest], main, inlier)
        if found is None:
            break
        support = rest[matcher.residual(found, points[rest], normals[rest]) < inlier]
        if support.size < MIN_PAIRS:
            break
        remaining[support] = False
        owner = _assign(matcher, bodies + [found], points, normals, inlier)
        mask = _regions(box_vol, hip, points, owner, len(bodies) + 1, box_articular) == len(bodies)
        volume = float(mask.sum()) * voxel_cm3
        pieces, n = ndi.label(mask, structure=np.ones((3, 3, 3)))
        share = float(np.bincount(pieces.ravel())[1:].max() / mask.sum()) if n else 0.0
        reaches_joint = bool(box_articular is not None and (mask & box_articular).any())
        relative = float(np.max(np.linalg.norm(transform_points(found, points[support])
                                               - transform_points(main, points[support]), axis=1)))
        minimum = MIN_FRAGMENT_ACETABULAR_CM3 if reaches_joint else MIN_FRAGMENT_RING_CM3
        reasons = []
        if volume < minimum:
            reasons.append(f"{volume:.2f} cm3, under the {minimum:.1f} cm3 minimum "
                           f"{'at the articular surface' if reaches_joint else 'in the ring'}")
        if share < CONNECTED_SHARE:
            reasons.append(f"not one piece: {100 * share:.0f}% of it in its largest part")
        if relative <= distinct:
            reasons.append(f"moves {relative:.1f} mm off the main body, not more than {distinct:.1f} mm "
                           f"(max of {DISTINCT_TRANSFORM_FACTOR:.0f} x floor {floor:.2f} mm, plane "
                           f"uncertainty {mirror.uncertainty_mm:.2f} mm)")
        if reasons:
            rejected.append(Candidate(volume, reaches_joint, share, relative, distinct, reasons))
        else:
            bodies.append(found)

    owner = _assign(matcher, bodies, points, normals, inlier)
    fragments = []
    for k, transform in enumerate(bodies):
        own = owner == k
        if own.sum() >= MIN_PAIRS:  # settle each body on its final share of the surface
            settled = matcher.consensus(points[own], normals[own], transform, inlier)
            transform = settled if settled is not None else transform
            bodies[k] = transform
    owner = _assign(matcher, bodies, points, normals, inlier)
    regions = _regions(box_vol, hip, points, owner, len(bodies), box_articular)
    for k, transform in enumerate(bodies):
        own = owner == k
        mask = np.zeros(labels.shape, dtype=bool)
        mask[box] = regions == k
        residual = matcher.residual(transform, points[own], normals[own])
        to_parent = np.eye(4) if k == 0 else invert(bodies[0]) @ transform
        home = float(travel_mm(transform, points[own]).max()) if own.any() else 0.0
        fragments.append(Fragment(
            index=k,
            parent=None if k == 0 else 0,
            mask=mask,
            volume_cm3=float(mask.sum()) * voxel_cm3,
            to_reference=transform,
            to_parent=to_parent,
            residual_mm=float(np.percentile(residual[np.isfinite(residual)], FLOOR_PERCENTILE)) if own.any() else float("nan"),
            travel_mm=home,
            relative_travel_mm=float(travel_mm(to_parent, points[own]).max()) if own.any() else 0.0,
            plane_uncertainty_mm=mirror.uncertainty_mm,
            below_floor=bool(home < floor),
            articular=bool(box_articular is not None and (regions == k)[box_articular].any()),
            n_points=int(own.sum()),
        ))
    return FragmentSet(injured, mirror.reference, mirror.choice, fragments, floor, inlier, mirror.uncertainty_mm,
                       rejected, "", warnings)


def _assign(matcher: _Matcher, bodies, points, normals, inlier_mm) -> np.ndarray:
    """Each surface point to the body whose transform explains it best, or
    -1 when none explains it within ``inlier_mm`` (a fracture face, say).
    Then a vote among neighbours, so a body is a patch and not a speckle."""
    residuals = np.stack([matcher.residual(t, points, normals) for t in bodies])
    owner = np.argmin(residuals, axis=0)
    owner[residuals.min(axis=0) >= inlier_mm] = -1
    tree = cKDTree(points)
    _, near = tree.query(points, k=min(9, len(points)))
    for _ in range(2):
        votes = owner[near]
        smoothed = owner.copy()
        for i in np.flatnonzero(owner >= 0):
            v = votes[i][votes[i] >= 0]
            counts = np.bincount(v, minlength=len(bodies))
            if counts.max() > counts[owner[i]] + 1:
                smoothed[i] = int(np.argmax(counts))
        owner = smoothed
    return owner


def _regions(vol: Volume, hip: np.ndarray, points, owner, n_bodies: int,
             articular: Optional[np.ndarray]) -> np.ndarray:
    """Each hip voxel's body (-1 outside the hip): the body of its nearest
    explained surface point. Then every piece of a body, other than its
    largest, that is smaller than the minimum fragment for where it lies is
    carried with the body it touches most (DECISIONS 3.2)."""
    out = np.full(hip.shape, -1, dtype=np.int16)
    assigned = owner >= 0
    if not assigned.any():
        return out
    idx = np.argwhere(hip)
    _, nearest = cKDTree(points[assigned]).query(vol.zyx_indices_to_world(idx))
    out[tuple(idx.T)] = owner[assigned][nearest]
    voxel_cm3 = float(np.prod(vol.spacing)) / 1000.0
    ring = np.ones((3, 3, 3))
    for k in range(n_bodies):
        pieces, n = ndi.label(out == k, structure=ring)
        if n <= 1:
            continue
        sizes = np.bincount(pieces.ravel())[1:]
        slices = ndi.find_objects(pieces)
        for piece in np.flatnonzero(np.arange(n) != np.argmax(sizes)) + 1:
            # Work in the piece's own box, one voxel wider for its neighbours.
            window = tuple(slice(max(sl.start - 1, 0), sl.stop + 1) for sl in slices[piece - 1])
            where = pieces[window] == piece
            at_joint = articular is not None and bool((where & articular[window]).any())
            minimum = MIN_FRAGMENT_ACETABULAR_CM3 if at_joint else MIN_FRAGMENT_RING_CM3
            if sizes[piece - 1] * voxel_cm3 >= minimum:
                continue
            local = out[window]
            touching = local[ndi.binary_dilation(where, structure=ring) & ~where]
            touching = touching[(touching >= 0) & (touching != k)]
            if touching.size:
                local[where] = np.bincount(touching).argmax()
    return out


def reduce_labels(labels_vol: Volume, fragments: FragmentSet) -> Volume:
    """Virtual reduction: every body of the injured hemipelvis moved home
    by its to_reference, on the same grid; everything else untouched. This
    is the call Corridor Finder's virtual reduction makes before searching
    for corridors. Refused when there is no transform home."""
    if fragments.refused:
        raise ValueError(f"no virtual reduction: {fragments.refused}")
    injured_id = _hip_ids(fragments.side)[0]
    out = labels_vol.array.copy()
    for f in fragments.fragments:
        out[f.mask] = 0
    for f in fragments.fragments:
        idx = np.argwhere(f.mask)
        corners = labels_vol.zyx_indices_to_world(np.array([idx.min(axis=0), idx.max(axis=0)]))
        box_world = transform_points(f.to_reference, np.array(
            [[x, y, z] for x in corners[:, 0] for y in corners[:, 1] for z in corners[:, 2]]))
        lo = np.floor(labels_vol.world_to_zyx_indices(box_world.min(axis=0)).ravel()).astype(int) - 1
        hi = np.ceil(labels_vol.world_to_zyx_indices(box_world.max(axis=0)).ravel()).astype(int) + 2
        lo, hi = np.maximum(lo, 0), np.minimum(hi, out.shape)
        if np.any(hi <= lo):
            continue
        grid = np.stack(np.meshgrid(*(np.arange(a, b) for a, b in zip(lo, hi)), indexing="ij"), axis=-1).reshape(-1, 3)
        back = transform_points(invert(f.to_reference), labels_vol.zyx_indices_to_world(grid))
        src = np.rint(labels_vol.world_to_zyx_indices(back)).astype(int).T
        inside = np.all((src >= 0) & (src < np.array(out.shape)), axis=1)
        hit = np.zeros(len(grid), dtype=bool)
        hit[inside] = f.mask[tuple(src[inside].T)]
        out[tuple(grid[hit].T)] = injured_id
    return Volume(out, labels_vol.spacing, labels_vol.origin)
