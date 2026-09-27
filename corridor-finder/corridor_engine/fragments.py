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
points are removed and the search repeats on what is left, so fragments
1..k are what one transform cannot explain.

**Bone no body carries home.** Every hip voxel is carried home by its
own body's transform and mirrored back; a piece that lands further than
the inlier distance from the intact hip, and is at least the smallest
fragment there can be for where it lies (DECISIONS 3.2), is bone the
bodies found so far do not explain.

**Where the search for the next body starts.** Nearest-neighbour pairing
only finds a transform it starts near. Started from the main body alone,
a 58 cm3 iliac-wing fragment on the phantom was found at 10 and 15 mm and
missed at 20, 25 and 23.3 mm with 10 degrees: none of its pairs agreed, the
search ended, and the finder said "one body" with the fragment inside it.
So when the search from the main body finds nothing while there is bone
no body carries home, it starts again from the main body shifted by how
far that bone's unexplained surface lies from the mirrored surface no body
yet reaches (the fragment's empty home), as a whole and toward each of
that surface's largest patches, and keeps whichever start explains most
of what is left. Only then: tried every time, those starts fitted a 3 cm3
fracture face 40 mm away on the 5 mm phantom and promoted it (fact 3
again); and preferred to the main body's start whenever they explained
more, they took the 5 mm fragment from 95% to 90% pure. A body found that
way is there only because of the unexplained bone, so it must mostly be
that bone (FROM_UNEXPLAINED_SHARE): on 38 normal hemipelvises, without
that check, the only body these starts added was 8.3 cm3, 51.8 mm off, of
which 21% had been unexplained, where the phantom's 20 mm fragment was 89%
and the body found on CLINIC_0012 94%.

**Nothing unexplained is dropped silently.** When the search ends with
such bone left, its mask, its volume and the share of the surface no body
explains are carried on the result and named in its warnings and its
sentence, and reduce_labels refuses to move a hemipelvis with it in. It is
either a fragment the search did not separate or asymmetry the mirror
does not have, and nothing here can tell which.

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

**to_reference has no validated error bound**, and nothing here claims
one. The residual is how well a body fits the mirrored side, and a
closest-point distance cannot see a surface sliding along itself; on the
phantom the reduced 10 mm fragment lands p90 1.3 mm out against a residual
of 1.13 mm (0.2 mm with the exact plane, so the gap is the plane's). The
plane uncertainty is the spread between two references, not the plane's
error: on 20 normal, undisplaced pelvises the main body "travels home"
5.8-45.9 mm while it reads 0.0-32.4 mm. No number in a result tells a
displaced hemipelvis from a plane that is off, so every FragmentSet carries
the reason in ``to_reference_unvalidated`` and reduce_labels refuses unless
the caller accepts it explicitly.

**Below the floor** a number is still a number (DECISIONS 1.4): it is
flagged with the floor, never zeroed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
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
MAX_CANDIDATES = 12  # bodies examined, promoted or not, before the search stops
CLUSTER_MM = 2.0 * SAMPLE_MM  # unexplained surface points this close are one patch
START_CLUSTERS = 3  # the mirrored surface's largest unreached patches a search starts toward
FROM_UNEXPLAINED_SHARE = 0.5  # a body found from unexplained bone must be mostly that bone
ARTICULAR_GAP_MM = 6.0  # hip bone this close to the femoral head is at the joint
FEMUR_BONE_HU = 200.0  # unlabelled bone in the CT, for the femoral head
MIN_FEMUR_CM3 = 20.0  # a femoral head is far larger; smaller is not it
SIDES = ("right", "left", "both")

TO_REFERENCE_NOT_VALIDATED = (
    "the transform home has no validated error bound: on real anatomy the mirror plane's own error dominates it, "
    "and neither the residual nor the plane uncertainty bounds it")


@dataclass
class Fragment:
    index: int  # 0 is the main body
    parent: Optional[int]  # None for the main body
    mask: np.ndarray  # bool, on the labels grid, where the fragment is now
    volume_cm3: float
    to_reference: Optional[np.ndarray]  # 4x4, current position -> home; None when refused
    to_parent: np.ndarray  # 4x4, current position -> where it belongs on its parent as it lies
    residual_mm: float  # 90th percentile closest-point distance once home: fit quality, not an error bound
    travel_mm: float  # furthest any of its surface points travels home
    relative_travel_mm: float  # furthest any of its surface points travels under to_parent
    plane_uncertainty_mm: float  # carried by to_reference and travel_mm (DECISIONS 2.3); not an error bound
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
    # Hip bone that no body carries home onto the intact side, in pieces at
    # least the smallest fragment for where they lie (DECISIONS 3.2); and the
    # surface points no body explains, with their share of the surface.
    unexplained: Optional[np.ndarray] = None  # bool, on the labels grid
    unexplained_cm3: float = 0.0
    unexplained_pieces: int = 0
    unexplained_points: int = 0
    unexplained_share: float = 0.0
    # Why to_reference may not be applied as it stands; reduce_labels refuses
    # while it is set. Set on every result, hand-built ones included.
    to_reference_unvalidated: str = TO_REFERENCE_NOT_VALIDATED

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
            text += "; one body" + (" found" if self.unexplained_cm3 > 0 else "")
        if self.unexplained_cm3 > 0:
            text += (f"; {self.unexplained_cm3:.1f} cm3 in {self.unexplained_pieces} piece"
                     f"{'s' if self.unexplained_pieces != 1 else ''} that no body carries home "
                     f"({100 * self.unexplained_share:.0f}% of the surface unexplained)")
        if self.to_reference_unvalidated:
            text += "; the transform home is not validated for use"
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


def articular_surface(labels_vol: Volume, side: str, ct: Optional[Volume] = None,
                      allow_unvalidated_ct_femur: bool = False) -> Optional[np.ndarray]:
    """The injured hip's voxels within ARTICULAR_GAP_MM of the femoral head,
    from the femur label. None when the labels have no femur, and then the
    ring minimum applies everywhere (find_fragments says so).

    The femoral head can also be taken from unlabelled bone in the CT
    (FEMUR_BONE_HU), but only when ``allow_unvalidated_ct_femur`` asks for
    it: that heuristic has not been compared with a real femur segmentation,
    and a femur found in the wrong place would move the 0.5 cm3 acetabular
    minimum of DECISIONS 3.2 to the wrong bone. It is for looking, not for
    reporting (agreed with Corridor Finder, 2026-09-27, for the same reason
    its articular margin does not use it). Without the flag ``ct`` is not
    used."""
    if not allow_unvalidated_ct_femur:
        ct = None
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

    points, normals, point_voxels = _surface(box_vol, hip)
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
    refound = matcher.consensus(points, normals, main, inlier)
    main = refound if refound is not None else main
    distinct = max(DISTINCT_TRANSFORM_FACTOR * floor, mirror.uncertainty_mm)

    reference = _Intact(labels_vol, intact, m, inlier)
    bodies = [main]
    explained = matcher.residual(main, points, normals) < inlier
    rejected: List[Candidate] = []
    remaining = ~explained
    while remaining.sum() >= MIN_PAIRS:
        if len(bodies) > MAX_FRAGMENTS or len(bodies) + len(rejected) >= MAX_CANDIDATES:
            warnings.append(f"the search stopped after {len(bodies) - 1 + len(rejected)} candidates with "
                            f"{int(remaining.sum())} surface points still unexplained")
            break
        rest = np.flatnonzero(remaining)
        found, support = _search(matcher, points, normals, rest, [main], inlier)
        stray = None  # the bone no body carried home, when the search had to start from it
        if support.size < MIN_PAIRS:
            now = _regions(box_vol, hip, points, _assign(matcher, bodies, points, normals, inlier), len(bodies),
                           box_articular)
            stray, _ = reference.off(box_vol, hip, now, bodies, box_articular)
            found, support = _search(matcher, points, normals, rest, _shifted_starts(
                matcher, bodies, points, normals, rest, rest[stray[tuple(point_voxels[rest].T)]], inlier), inlier)
        if found is None or support.size < MIN_PAIRS:
            break
        remaining[support] = False
        owner = _assign(matcher, bodies + [found], points, normals, inlier)
        regions = _regions(box_vol, hip, points, owner, len(bodies) + 1, box_articular)
        mask = regions == len(bodies)
        volume = float(mask.sum()) * voxel_cm3
        pieces, n = ndi.label(mask, structure=np.ones((3, 3, 3)))
        share = float(np.bincount(pieces.ravel())[1:].max() / mask.sum()) if n else 0.0
        reaches_joint = bool(box_articular is not None and (mask & box_articular).any())
        # Measured over the candidate as it would be reported, never over
        # the islands _regions has just given to the main body: those lie far
        # from the candidate, so a rotation difference moves them further.
        own = _own(regions, point_voxels, owner, len(bodies))
        relative = float(travel_mm(invert(main) @ found, points[own]).max()) if own.any() else 0.0
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
        if stray is not None and mask.any() and (mask & stray).sum() < FROM_UNEXPLAINED_SHARE * mask.sum():
            reasons.append(f"found from bone no body carried home, but only {100 * (mask & stray).sum() / mask.sum():.0f}% "
                           f"of it is that bone, under {100 * FROM_UNEXPLAINED_SHARE:.0f}%")
        if reasons:
            rejected.append(Candidate(volume, reaches_joint, share, relative, distinct, reasons))
        else:
            bodies.append(found)

    owner = _assign(matcher, bodies, points, normals, inlier)
    regions = _regions(box_vol, hip, points, owner, len(bodies), box_articular)
    for k, transform in enumerate(bodies):
        own = _own(regions, point_voxels, owner, k)
        if own.sum() >= MIN_PAIRS:  # settle each body on its final share of the surface
            settled = matcher.consensus(points[own], normals[own], transform, inlier)
            transform = settled if settled is not None else transform
            bodies[k] = transform
    owner = _assign(matcher, bodies, points, normals, inlier)
    regions = _regions(box_vol, hip, points, owner, len(bodies), box_articular)
    fragments = []
    for k, transform in enumerate(bodies):
        # Every number is taken over the surface of the mask that is
        # reported (DECISIONS 1.2), not over what _assign first gave the body.
        own = _own(regions, point_voxels, owner, k)
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
    unvalidated = (f"{TO_REFERENCE_NOT_VALIDATED}; here the main body travels {fragments[0].travel_mm:.1f} mm "
                   f"home against a reference uncertainty of {mirror.uncertainty_mm:.1f} mm, and nothing measured "
                   f"tells a displaced hemipelvis from a mirror plane that is off")

    stray, pieces = reference.off(box_vol, hip, regions, bodies, box_articular)
    unexplained = np.zeros(labels.shape, dtype=bool)
    unexplained[box] = stray
    unexplained_cm3 = float(stray.sum()) * voxel_cm3
    unexplained_points = int((owner < 0).sum())
    share = unexplained_points / len(points)
    if pieces:
        warnings.append(f"{unexplained_cm3:.1f} cm3 of the {injured} hip, in {pieces} piece"
                        f"{'s' if pieces != 1 else ''} each at least the smallest fragment for where it lies, "
                        f"is carried by no body to within {inlier:.1f} mm of the intact side, and "
                        f"{unexplained_points} of {len(points)} surface points ({100 * share:.0f}%) are explained "
                        f"by no body: a fragment the search did not separate, or asymmetry the mirror does not have")
    return FragmentSet(injured, mirror.reference, mirror.choice, fragments, floor, inlier, mirror.uncertainty_mm,
                       rejected, "", warnings, unexplained=unexplained, unexplained_cm3=unexplained_cm3,
                       unexplained_pieces=pieces, unexplained_points=unexplained_points, unexplained_share=share,
                       to_reference_unvalidated=unvalidated)


def _clusters(points: np.ndarray, radius_mm: float) -> List[np.ndarray]:
    """Indices of each patch of points linked within ``radius_mm``, the
    largest first."""
    pairs = cKDTree(points).query_pairs(radius_mm, output_type="ndarray")
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(points), len(points)))
    _, which = connected_components(graph, directed=False)
    order = np.argsort(-np.bincount(which), kind="stable")
    return [np.flatnonzero(which == c) for c in order]


def _search(matcher: _Matcher, points, normals, rest, starts, inlier_mm):
    """Of the transforms consensus reaches on the ``rest`` points from each
    start, the one that explains most of them, and those it explains."""
    found, support = None, rest[:0]
    for start in starts:
        candidate = matcher.consensus(points[rest], normals[rest], start, inlier_mm)
        if candidate is None:
            continue
        agree = rest[matcher.residual(candidate, points[rest], normals[rest]) < inlier_mm]
        if agree.size > support.size:
            found, support = candidate, agree
    return found, support


def _shifted_starts(matcher: _Matcher, bodies, points, normals, rest, stray, inlier_mm):
    """When ``stray`` (the unexplained points, of ``rest``, on bone no body
    carries home) are enough to pair: the main body's transform shifted by
    how far they lie from the mirrored surface no body yet reaches, as a
    whole and toward each of its START_CLUSTERS largest patches (see the
    module docstring)."""
    main = bodies[0]
    if stray.size < MIN_PAIRS:
        return
    explained = np.setdiff1d(np.arange(len(points)), rest)
    if explained.size:
        residuals = np.stack([matcher.residual(t, points[explained], normals[explained]) for t in bodies])
        best = np.argmin(residuals, axis=0)
        claimed = np.concatenate([transform_points(t, points[explained[best == k]]) for k, t in enumerate(bodies)])
        reach, _ = cKDTree(claimed).query(matcher.target)
        empty = matcher.target[reach >= inlier_mm]
    else:
        empty = matcher.target
    if len(empty) < MIN_PAIRS:
        return
    moved = transform_points(main, points[stray])
    shift = np.eye(4)
    shift[:3, 3] = empty.mean(axis=0) - moved.mean(axis=0)
    yield shift @ main
    for home in _clusters(empty, CLUSTER_MM)[:START_CLUSTERS]:
        if home.size >= MIN_PAIRS:
            shift = np.eye(4)
            shift[:3, 3] = empty[home].mean(axis=0) - moved.mean(axis=0)
            yield shift @ main


class _Intact:
    """The intact hip, for asking where a body's transform carries bone."""

    def __init__(self, labels_vol: Volume, intact: np.ndarray, mirror_matrix: np.ndarray, reach_mm: float):
        self.labels_vol = labels_vol
        self.mirror = mirror_matrix
        sx, sy, sz = labels_vol.spacing
        pad = np.ceil(np.array([reach_mm / s for s in (sz, sy, sx)])).astype(int) + 1
        idx = np.argwhere(intact)
        self.lo = np.maximum(idx.min(axis=0) - pad, 0)
        self.hi = np.minimum(idx.max(axis=0) + pad + 1, intact.shape)
        box = tuple(slice(a, b) for a, b in zip(self.lo, self.hi))
        self.near = ndi.distance_transform_edt(~intact[box], sampling=(sz, sy, sx)) <= reach_mm

    def off(self, vol: Volume, hip: np.ndarray, regions: np.ndarray, bodies,
            articular: Optional[np.ndarray]) -> Tuple[np.ndarray, int]:
        """The hip voxels (on ``vol``'s grid) that their own body's
        transform, followed by the mirror back across the plane, does not
        carry to within the reach of the intact hip, kept only in pieces at
        least the smallest fragment for where they lie (DECISIONS 3.2); and
        how many such pieces there are. A voxel in no body is carried
        nowhere."""
        stray = hip.copy()
        for k, transform in enumerate(bodies):
            voxels = np.argwhere(regions == k)
            # The transform carries a body home onto the mirrored intact
            # side; the mirror, its own inverse, carries that onto the intact.
            world = transform_points(self.mirror @ transform, vol.zyx_indices_to_world(voxels))
            at = np.rint(self.labels_vol.world_to_zyx_indices(world)).astype(int) - self.lo[:, None]
            inside = np.all((at >= 0) & (at < (self.hi - self.lo)[:, None]), axis=0)
            landed = np.zeros(len(voxels), dtype=bool)
            landed[inside] = self.near[tuple(at[:, inside])]
            stray[tuple(voxels[landed].T)] = False
        pieces, n = ndi.label(stray, structure=np.ones((3, 3, 3)))
        if not n:
            return stray, 0
        sx, sy, sz = vol.spacing
        sizes = np.bincount(pieces.ravel())[1:] * (sx * sy * sz / 1000.0)
        at_joint = np.zeros(n + 1, dtype=bool)
        if articular is not None:
            at_joint[np.unique(pieces[articular & stray])] = True
        minimum = np.where(at_joint[1:], MIN_FRAGMENT_ACETABULAR_CM3, MIN_FRAGMENT_RING_CM3)
        keep = np.flatnonzero(sizes >= minimum) + 1
        return np.isin(pieces, keep), int(keep.size)


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


def _own(regions: np.ndarray, point_voxels: np.ndarray, owner: np.ndarray, k: int) -> np.ndarray:
    """The surface points that lie in body ``k``'s final region, after
    _regions has carried small pieces to their neighbours (DECISIONS 3.2),
    and that some body explains (a fracture face explained by none is not
    fitted, so it is not measured)."""
    return (regions[tuple(point_voxels.T)] == k) & (owner >= 0)


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


def reduce_labels(labels_vol: Volume, fragments: FragmentSet, accept_unvalidated: bool = False) -> Volume:
    """Virtual reduction: every body of the injured hemipelvis moved home
    by its to_reference, on the same grid; everything else untouched. Where
    a moved body lands on another bone, that bone is kept: the overlap is
    the reduction's own error, and erasing a sacrum under it would change
    the corridors. This is the call Corridor Finder's virtual reduction
    makes before searching for corridors. Refused when there is no
    transform home, and while ``fragments.to_reference_unvalidated`` is set
    unless ``accept_unvalidated`` says the caller knows: that is for
    measuring the reduction itself against a phantom's known transform, not
    for moving a patient's hemipelvis before corridors are planned on it.
    Refused regardless while fragments.unexplained_cm3 is not zero."""
    if fragments.refused:
        raise ValueError(f"no virtual reduction: {fragments.refused}")
    if fragments.to_reference_unvalidated and not accept_unvalidated:
        raise ValueError(f"no virtual reduction: {fragments.to_reference_unvalidated} "
                         "(accept_unvalidated=True applies it anyway)")
    if fragments.unexplained_cm3 > 0:
        # Not waived by accept_unvalidated, which accepts the plane's error:
        # this bone would be moved by a transform known not to be its own.
        raise ValueError(f"no virtual reduction: {fragments.unexplained_cm3:.1f} cm3 of the {fragments.side} hip "
                         "is carried home by no body, so moving the hemipelvis would leave it out of place")
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
        target = tuple(grid[hit].T)
        out[target] = np.where(out[target] == 0, injured_id, out[target])
    return Volume(out, labels_vol.spacing, labels_vol.origin)
