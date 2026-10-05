"""Where a bone is broken: its fracture surfaces, and the sacral split.

displacement-finder DECISIONS 7c (slice 1b): both the reduction fit and the
outcome number of 1.5 are measured across fracture surfaces, so they come
first (7c.1). The surgeon's fracture marks seed the search (7c.3), the
lateral sacral fragment is split off at the sacral fracture surface and
confirmed by the surgeon (7c.5), and every face carries its cortical rim,
which survives comminution better than the cancellous face (7c.6).

**How a fracture is seen: one bone facing itself.** si_joint.py locates the
SI joint as the empty space where the nearest sacrum and the nearest hip
lie on opposite sides (si_joint.facing). Here the same test is run with one
bone label against itself: a voxel of empty space whose own nearest bone
and its neighbour's nearest bone both belong to this label, lie on opposite
sides of it, and are less than MAX_FRACTURE_SLOT_MM apart, with the two
faces' outward normals opposed. That is a slot through the bone. Every
joint of the pelvis lies between two *different* labels (SI joint, hip
joint, symphysis, L5/S1), so the test cannot see one: a voxel whose nearest
bone on either side is another label is never a candidate.

**What else is a slot, and the vetoes that remove it** (the slice 1
architect measured each on the four CLINIC cases; re-measured where noted
in the README):

- **sheet, not tube:** the sacral canal and foramina are tunnels open to
  the outside (binary_fill_holes finds only 0.01-0.13 cm3 enclosed in a
  sacrum), so inside one the nearest walls face each other along a line,
  not across a sheet. A slot's points must spread in two directions
  (SHEET_ASPECT);
- **minimum area:** one-voxel roughness of a segmentation makes hundreds of
  tiny slots per bone (240-819 clusters per bone measured), so a patch
  must reach MIN_PATCH_AREA_MM2;
- **mirror twin:** a patch whose mirror image lands on a slot of the
  contralateral bone is anatomy, which removes the obturator foramen,
  cotyloid notch, sciatic notch and each sacral foramen without a list of
  named holes. On the sacrum, its own mirror image does not count as a
  twin: a midline feature (the canal) is left to the sheet test, and a
  transverse fracture, symmetric by nature, is not removed for it. Needs a
  confirmed mirror; without one it is not applied and the result says so.
  A bilateral fracture whose two sides happen to mirror each other within
  SYMMETRY_TWIN_MM would be removed by it; the surgeon's marks override it
  (below);
- **cortex contrast:** a fracture face is exposed cancellous bone, a
  natural surface is cortex. Measured, an absolute HU threshold is useless
  (44-65% of these bones' interiors read under 150 HU, fatty marrow), but
  the cortex-to-interior ratio is a stable 2.0-4.0 on two patients, so the
  face is compared with this patient's own cortex (CORTEX_FRACTION). Needs
  the CT; without one it is not applied and the result says so.

**A fracture whose faces touch shows no slot.** There the surface comes
from slice 1: the boundary between a promoted fragment's mask and its
parent's (fragments.find_fragments). A slot found between the same two
bodies is merged into that surface. Bone that no body carries home is a
place to look, never a surface by itself: a slot in it is flagged as lying
there, and such bone with no slot in it is named in the notes. No surface
found in a bone is never "no fracture": the notes say why it may not show.

**The surgeon's marks** (corridor-finder 7.1, fracture.FracturePlane). A
patch within FAR_FROM_MARKS_MM of a mark is kept against the mirror-twin
veto (he has said a fracture is there) and listed first; every surface
further than that from every mark is flagged whenever marks were given.
Each mark point is then matched on its own: only by a surface on the bone
the mark lies on (its nearest bone), with a face within MARK_MATCH_MM of
it. Every mark point with no such surface is flagged and kept
(FractureSurfaces.unmatched_marks), so that a reduction can say it knows
nothing about the fracture there. Matched as a whole, a marked fracture
with a surface found at one end read as matched along its whole length,
and a surface on another bone, or 10-20 mm off, matched it too: past
Corridor Finder's warning radius, a screw crossing the fracture where
nothing was found would have had no warning from it.

**What a fracture surface carries.** An id (its region in a reduction is
``fracture_<id>``), the two faces with what is on each side, points on
each face with outward normals (from the bone into the fracture), the face
voxels, and which of them are the cortical rim: the face within RIM_MM of
the bone's outer surface away from the fracture. A face is the whole
broken surface of its body, not only where the two bodies still overlap:
the faces found (across a slot, or touching) are grown over the body's
exposed surface continuing the found face's plane, where the other body
no longer lies opposite it (WHOLE_FACE_BAND_MM, WHOLE_FACE_COS,
WHOLE_FACE_OPPOSITE_MM). Taken only where the bodies overlap as scanned, each
face's outline, its rim, was the outline of the overlap, so the two rims
matched in the scanned pose by construction, and a fit to them was pulled
back toward the displacement it was correcting (a sacral fracture slid
6 mm was fitted 5.6-9.4 mm off from the exact start). Points are the face
voxels' centres, as every distance in the engine is (si_joint's gap is
centre to centre), so the two faces of a fracture reduced exactly still lie
up to about a voxel apart.

**From the CT** (displacement-finder DECISIONS 7d.1, 7d.5, slice 1c), inside
each bone label, so where the label is painted solid across a fracture or
an impacted fracture leaves no gap: a **lucent line** (bone darker than the
bone either side of it, through the cancellous bone and breaking the
cortex, source CT_LUCENT) and a **dense band** (interior bone denser than
the same place on the mirrored side by IMPACTION_MARGIN_HU, or with both
sides injured than this patient's own cancellous bone nearby, with bone of
the usual density on both sides of it, source CT_IMPACTED, carrying its
thickness as impaction_depth_mm). Where, with the CT given, nothing is
found near the surgeon's marks, the plane through them is the surface
(source SURGEON_MARKS), flagged as not found, and its marks stay
unmatched. Every surface says where it came from (``source``); slice 1b's
are GAP.

**The sacral split** (7c.5). The lateral fragment is cut off along the
plane through that side's sacral fracture surfaces; where the faces still
touch, the plane carries the cut across, and the share of the cut that is
extrapolated is reported. It is a mask the surgeon confirms: every split is
unconfirmed until confirm_split, and says so. With no sacral fracture
surface on a side, no split is guessed. A cut that is not lateral is
refused: a plane far from sagittal (SPLIT_MIN_LATERAL_COS), a piece
reaching past the midline (SPLIT_MIDLINE_MM) or coming within
AURICULAR_MAX_MM of the other hip (it would carry the other SI joint),
and two sides' pieces sharing bone.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import breadth_first_order
from scipy.spatial import cKDTree

from . import segmentation as seg
from .fracture import NEAR_MARKS_MM, FracturePlane
from .fragments import MIN_FRAGMENT_RING_CM3, FragmentSet
from .mirror import ConfirmedMirror, MirrorReference, ReferenceNotConfirmed
from .reduction import REGION_RADIUS_MM
from .si_joint import AURICULAR_MAX_MM, facing
from .volume import Volume

# A slot wider than this is not looked for: the faces of a displaced
# fracture gape further apart than this only where slice 1's fragments see
# the displacement. The slice 1 architect's value, not re-measured.
MAX_FRACTURE_SLOT_MM = 6.0
MIN_FACE_OPPOSITION = -0.5  # cos of the angle between the two faces' outward normals
# Measured by the slice 1 architect: almost all of the 240-819 clusters per
# bone are 0.07-0.30 cm3 of roughness. To be checked on the real cases.
MIN_PATCH_AREA_MM2 = 40.0
SHEET_ASPECT = 2.0  # a sheet's second extent is at least this x its thickness
SYMMETRY_TWIN_MM = 4.0  # a mirrored point this close to a contralateral slot has a twin
SYMMETRY_TWIN_FRACTION = 0.5  # more than this share of a patch with twins makes it anatomy
CORTEX_RIND_MM = 1.5  # bone this close to a surface is that surface's cortex
# An interpolation from two patients' cortex-to-interior ratios (2.0-4.0),
# not a calibration: a face reading at least this share of this patient's
# cortex HU is cortex, so anatomy.
CORTEX_FRACTION = 0.6
# The rim band: wide enough to hold two voxels of rim at the CLINIC and
# phantom spacings. The cortical shell itself is thinner, so this is a band
# of the face next to the outer surface, not a measurement of cortex.
RIM_MM = 3.0
# Corridor Finder trusts a marked fracture plane within this of a mark
# (fracture.NEAR_MARKS_MM); a surface further from every mark is not the
# one that was marked.
FAR_FROM_MARKS_MM = NEAR_MARKS_MM
# A mark point is matched by a surface on its own bone with a face within
# this of it. Corridor Finder warns at a region only within
# reduction.REGION_RADIUS_MM of it, so a mark matched from further off could
# leave a screw crossing the fracture there with no warning at all.
MARK_MATCH_MM = REGION_RADIUS_MM
SPLIT_MIN_CM3 = MIN_FRAGMENT_RING_CM3  # a lateral sacral fragment is a fragment in the ring (DECISIONS 3.2)
# A lateral fragment is cut off by a plane that runs front to back and top
# to bottom: its normal within 60 degrees of left-right. A transverse
# fracture's normal lies 85-90 degrees from it, and cut along that, the
# "lateral" piece is the whole sacrum above the cut. Chosen, not calibrated.
SPLIT_MIN_LATERAL_COS = 0.5
# A lateral piece holds no bone of the other side: none of it more than
# this past the midline. A zone III fracture runs through the canal, so its
# piece may reach toward the midline, and the midline itself is only as
# good as the plane (or, with no mirror, the scanner's x axis). Chosen, not
# calibrated.
SPLIT_MIDLINE_MM = 5.0
# A fracture face is the found face (slot or contact) grown over its own
# body's exposed surface continuing the found face's own plane and facing
# the same way, where the other body no longer lies opposite it: the part
# of the face the other body has slid off. Within the rim band of that
# plane, facing within 45 degrees of it, and with none of the other body
# within twice a slot's width along its normal (the reach rims are paired
# over). Without that last test the face grew over the crushed phantom's
# crater floor, which looks at the other face 6-12 mm away, and the fit ran
# off 118 mm. Chosen, not calibrated.
WHOLE_FACE_BAND_MM = RIM_MM
WHOLE_FACE_COS = 0.7
WHOLE_FACE_OPPOSITE_MM = 2.0 * MAX_FRACTURE_SLOT_MM
WHOLE_FACE_REFITS = 5  # the face's plane is refitted to its points within the band, at most this often

# The CT route (DECISIONS 7d.1, 7d.5). Every HU compared is the CT smoothed
# by this (Gaussian sigma): a CT's white noise is tens of HU from voxel to
# voxel. A lucent line much thinner than this is blurred into the bone on
# either side: a faint line, which the surgeon's marks are the backup for.
CT_SMOOTH_MM = 1.0
SOFT_TISSUE_HU = 40.0  # blood and muscle: what fills a fracture that gapes
# A lucent line is darker than the bone on both sides of it by at least
# this, and at least half-way from that bone down to soft tissue. Chosen as
# several times the smoothed CT's noise, not calibrated.
LUCENT_MIN_CONTRAST_HU = 100.0
# The bone on either side of a lucent line is looked for up to this (plus a
# voxel) along each direction: half the widest slot looked for.
LUCENT_REACH_MM = MAX_FRACTURE_SLOT_MM / 2.0
# A lucent line breaks the cortex where at least this many of its voxels lie
# in the bone's rind (CORTEX_RIND_MM) and read, by their median, under
# CORTEX_FRACTION of this patient's cortex: more than one noisy voxel.
# Chosen, not calibrated.
BREAK_MIN_VOXELS = 3
# A dense band is looked for only this deep inside the bone: the rind is
# cortex, and a mirror a millimetre off would compare cortex with marrow.
IMPACTION_INTERIOR_MM = 2.0 * CORTEX_RIND_MM
# The same place on the mirrored side is the densest bone within this of the
# reflected point, along each axis: the mirror's measured median floor at
# the SI joint, 4.4-4.7 mm (DECISIONS, the table under section 1), rounded
# up. Normal dense bone that lies a few millimetres from where its mirror
# image puts it (subchondral bone at a joint) is then still met on the other
# side.
IMPACTION_MIRROR_REACH_MM = 5.0
# With both sides injured, or no confirmed mirror, a band is compared with
# this patient's own cancellous bone within this, along each axis: the mean
# of the interior there, less what is denser than that mean by the margin.
IMPACTION_NEARBY_MM = 15.0
# How much denser than its reference a band must be (7d.5). Measured on the
# one fully intact side on the workstation, CLINIC_0012's left hip and the
# left half of its sacrum (the surgeon read its sacral fracture as right),
# never on the fractures: see IMPACTION_MARGIN_PROVENANCE. One patient's one
# side is scarce data, and the margin also bounds what can be found: an
# impaction that is no denser than its two layers of bone laid one on the
# other adds that bone's HU above soft tissue, about 70 HU in 0012's sacrum
# (median interior 110 HU), under this margin.
IMPACTION_MARGIN_HU = 200.0
IMPACTION_MARGIN_PROVENANCE = (
    "the 99th percentile of how much denser each interior voxel of CLINIC_0012's intact side is than the densest bone "
    "within 5 mm of its mirrored place: 189 HU in the left hip, 171 HU in the left sacral half, rounded up to 25 HU; "
    "with every veto, that side shows no band against the mirror at any margin from 0 to 400 HU, and one against "
    "its own nearby bone at 100 and 150 HU, none from 200 HU; one side of one patient, not validated")
# A band is the bone around a dense core down to half its height above the
# bone's usual excess, looked for up to this far from the core.
IMPACTION_BAND_PAD_MM = 15.0
# ...and only within its slab (_in_slab), whose plane and thickness are
# refitted to the band grown within it, at most this often.
IMPACTION_SLAB_REFITS = 5
# DECISIONS 7e.2, a probable disc remnant: within this of the line through
# the S1 and S2 body centres (an adult S1 body is about 45-50 mm across, so
# its column), and within this of square to that line. Chosen from that
# anatomy, not tuned on the four CLINIC cases; it only flags, never drops.
DISC_REMNANT_BODY_RADIUS_MM = 25.0
DISC_REMNANT_MAX_TILT_DEG = 30.0
# A band of impaction has bone of the usual density on both sides of it, this
# far past its half-thickness (beyond the smoothing's blur of its edge), over
# at least this share of it. Chosen, not calibrated.
IMPACTION_FLANK_MM = 2.0 * CT_SMOOTH_MM
IMPACTION_FLANKED_SHARE = 0.5

BONE_KEYS = {seg.SACRUM: "sacrum", seg.HIP_R: "hip_right", seg.HIP_L: "hip_left"}
BONE_NAMES = {seg.SACRUM: "sacrum", seg.HIP_R: "right hip", seg.HIP_L: "left hip"}
CONTRALATERAL = {seg.SACRUM: seg.SACRUM, seg.HIP_R: seg.HIP_L, seg.HIP_L: seg.HIP_R}
SLOT, FRAGMENT_BOUNDARY = "slot", "fragment boundary"
# Where a surface came from (7d.1): the label's own gap (slice 1b's slot and
# fragment boundary routes), the CT (a lucent line through bone and cortex,
# or the dense band of impaction), or the surgeon's marked plane where
# neither found anything near his marks. Each with the route it names.
GAP, CT_LUCENT, CT_IMPACTED, SURGEON_MARKS = "gap", "ct_lucent", "ct_impacted", "surgeon_marks"
SOURCES = (GAP, CT_LUCENT, CT_IMPACTED, SURGEON_MARKS)
LUCENT_LINE, DENSE_BAND, MARKED_PLANE = "lucent line", "dense band", "marked plane"
MIRROR_REFERENCE, NEARBY_REFERENCE = "mirror", "nearby cancellous bone"
MARKS_SURFACE_FLAG = ("NOT FOUND: the plane through the surgeon's marks, used as the fracture surface because neither "
                      "the CT nor a gap in the label shows a fracture near these marks (DECISIONS 7d.1); it is where "
                      "he says the fracture is, not a surface seen in the scan")

_OFFSETS = np.array([(dz, dy, dx) for dz in (-1, 0, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                     if (dz, dy, dx) != (0, 0, 0)])
_RING = np.ones((3, 3, 3), dtype=bool)


@dataclass
class Face:
    """One side of a fracture."""

    side: str  # what lies on this side, in words ("sacrum, lateral side", "right hip fragment 1")
    label: int  # the bone label the face belongs to
    points: np.ndarray  # (n, 3) world mm, the face voxels' centres
    normals: np.ndarray  # (n, 3) unit, outward: from the bone into the fracture
    voxels: np.ndarray  # (n, 3) int, the face voxels' (z, y, x) indices on the labels grid
    rim: np.ndarray  # (n,) bool, the cortical rim (7c.6)

    @property
    def rim_points(self) -> np.ndarray:
        return self.points[self.rim]

    @property
    def rim_normals(self) -> np.ndarray:
        return self.normals[self.rim]


@dataclass
class FractureSurface:
    id: str  # "sacrum_1", "hip_right_2", "hip_right_fragment_1"
    label: int
    route: str  # SLOT, FRAGMENT_BOUNDARY, or both joined by " + "
    faces: Tuple[Face, Face]
    width_mm: float  # median gap across it, centre to centre; 0 where the faces touch
    area_mm2: float  # approximate: face voxels x voxel face area
    mark_distance_mm: Optional[float]  # to the nearest of the surgeon's marks; None when none were given
    flags: List[str] = field(default_factory=list)
    # The slot's empty voxels, (z, y, x) on the labels grid; none where the faces touch.
    gap_voxels: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.int64))
    source: str = GAP  # one of SOURCES
    # ct_impacted: the dense band's thickness along its normal (7d.4 reports
    # it as a negative gap); the faces lie either side of the band, this far
    # apart, and nothing gapes (width_mm is 0).
    impaction_depth_mm: Optional[float] = None
    density_reference: Optional[str] = None  # ct_impacted: MIRROR_REFERENCE or NEARBY_REFERENCE
    excess_hu: Optional[float] = None  # ct_impacted: how much denser than that reference, median over the band
    # The bone-labelled voxels read as the fracture, (z, y, x) on the labels
    # grid: the lucent line, the dense band, or the marked plane's cut.
    zone_voxels: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.int64))

    @property
    def region(self) -> str:
        """Its key in a reduction's residual_mm and region_xyz."""
        return f"fracture_{self.id}"

    @property
    def far_from_marks(self) -> bool:
        return self.mark_distance_mm is not None and self.mark_distance_mm > FAR_FROM_MARKS_MM

    @property
    def signed_gap_mm(self) -> float:
        """The gap as 7d.4 reports it: minus the impaction depth for an
        impacted fracture, else width_mm (nan where it was not measured)."""
        return -float(self.impaction_depth_mm) if self.impaction_depth_mm is not None else float(self.width_mm)

    def sentence(self) -> str:
        a, b = self.faces
        gap = (f"impacted {self.impaction_depth_mm:.1f} mm" if self.impaction_depth_mm is not None
               else f"gap {self.width_mm:.1f} mm" if np.isfinite(self.width_mm) else "gap not measured")
        text = (f"fracture {self.id} ({self.route}, from {self.source}): {a.side} against {b.side}, "
                f"{self.area_mm2:.0f} mm2, {gap}, rim {int(a.rim.sum())} + {int(b.rim.sum())} points")
        if self.excess_hu is not None:
            text += f", {self.excess_hu:.0f} HU denser than the {self.density_reference}"
        if self.mark_distance_mm is not None:
            text += f", {self.mark_distance_mm:.0f} mm from the nearest mark"
        return text + "".join(f"; {f}" for f in self.flags)


@dataclass
class Patch:
    """A slot examined and not accepted, with why."""

    label: int
    area_mm2: float
    width_mm: float
    extents_mm: Tuple[float, float, float]  # standard deviations along its three principal axes
    centre: np.ndarray  # world mm
    twin_share: Optional[float]  # None when the veto was not applied
    cortex_ratio: Optional[float]  # None when the veto was not applied
    reasons: List[str]
    source: str = GAP  # the route that found it (SOURCES)


@dataclass
class UnmatchedMarks:
    """A fracture the surgeon marked, and which of its mark points no
    surface found matches (MARK_MATCH_MM, on the mark's own bone)."""

    plane: FracturePlane  # the marked fracture, as given
    unmatched: np.ndarray  # (n,) bool over plane.marks
    bone: np.ndarray  # (n,) the label of the bone each mark lies on (its nearest, within FAR_FROM_MARKS_MM); 0 none
    bone_voxel: np.ndarray  # (n, 3) int, (z, y, x) of that nearest bone voxel; -1 where there is none
    nearest_mm: np.ndarray  # (n,) to the nearest face of a surface on that bone; inf when there is none

    @property
    def points(self) -> np.ndarray:
        return self.plane.marks[self.unmatched]


@dataclass
class FractureSurfaces:
    surfaces: List[FractureSurface]
    rejected: List[Patch]
    small_patches: Dict[str, int]  # per bone key, slots under MIN_PATCH_AREA_MM2 (not listed one by one)
    candidate_points: Dict[str, np.ndarray]  # per bone key, every slot voxel before any veto, world mm
    cortex_hu: Dict[str, float]  # per bone key, this patient's cortex (median HU of the outer rind)
    twin_checked: bool
    cortex_checked: bool
    marks_given: int
    notes: List[str] = field(default_factory=list)
    # Each marked fracture with a mark point no surface matches: he says a
    # fracture is there and none was found, so a reduction built on these
    # surfaces knows nothing about it and must say so where it lies
    # (congruence makes each one a region of unknown error at those points).
    unmatched_marks: List[UnmatchedMarks] = field(default_factory=list)
    ct_checked: bool = False  # the CT route ran (it needs the CT)
    density_reference: str = ""  # what a dense band was compared with: MIRROR_REFERENCE or NEARBY_REFERENCE
    impaction_margin_hu: Optional[float] = None  # how much denser it had to be (IMPACTION_MARGIN_HU)
    # Per bone key, every voxel the CT route read as lucent line or dense
    # band before any veto, world mm.
    lucent_points: Dict[str, np.ndarray] = field(default_factory=dict)
    dense_points: Dict[str, np.ndarray] = field(default_factory=dict)
    ct_small_patches: Dict[str, int] = field(default_factory=dict)  # "<bone key> <source>": under MIN_PATCH_AREA_MM2

    def flags(self) -> List[str]:
        """Everything a reduction built on these surfaces must carry in its
        notes: the notes, and each surface's flags with its id."""
        return list(self.notes) + [f"fracture {s.id}: {f}" for s in self.surfaces for f in s.flags]

    def sentence(self) -> str:
        if not self.surfaces:
            text = "no fracture surface found"
        else:
            text = f"{len(self.surfaces)} fracture surface{'s' if len(self.surfaces) != 1 else ''}: " + \
                   ", ".join(s.id for s in self.surfaces)
        return text + "".join(f"; {n}" for n in self.notes)


# --------------------------------------------------------------------------
# Slots: one bone facing itself.


@dataclass
class _Slots:
    label: int
    lo: np.ndarray  # the box's corner on the labels grid
    sampling: np.ndarray  # (sz, sy, sx)
    v: np.ndarray  # (k, 3) the gap voxel each pair is seen from, box indices
    near: np.ndarray  # (k, 3) its own nearest bone voxel
    far: np.ndarray  # (k, 3) the nearest bone voxel across the slot
    n_near: np.ndarray  # (k, 3) zyx unit, outward normal of the near face
    n_far: np.ndarray  # (k, 3) zyx unit, outward normal of the far face
    width: np.ndarray  # (k,) mm, the gap across, centre to centre
    patch_of_pair: np.ndarray  # (k,) patch id, 1-based
    slot_voxels: np.ndarray  # (m, 3) box indices
    patch_of_voxel: np.ndarray  # (m,) patch id
    n_patches: int


def _box(shape, idx: np.ndarray, pad: np.ndarray):
    lo = np.maximum(idx.min(axis=0) - pad, 0)
    hi = np.minimum(idx.max(axis=0) + pad + 1, shape)
    return lo, hi, tuple(slice(a, b) for a, b in zip(lo, hi))


def _sampling(vol: Volume) -> np.ndarray:
    sx, sy, sz = vol.spacing
    return np.array([sz, sy, sx], dtype=float)


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _slots(labels_vol: Volume, label: int) -> Optional[_Slots]:
    labels = labels_vol.array
    where = np.argwhere(labels == label)
    if where.shape[0] == 0:
        return None
    sampling = _sampling(labels_vol)
    pad = np.ceil(MAX_FRACTURE_SLOT_MM / sampling).astype(int) + 2
    lo, hi, box = _box(labels.shape, where, pad)
    lab = labels[box]
    bone = lab == label
    other = (lab != 0) & ~bone
    at = np.empty((3,) + bone.shape, dtype=np.int32)
    to_bone = ndi.distance_transform_edt(~bone, sampling=sampling, return_indices=True, indices=at)
    reach = MAX_FRACTURE_SLOT_MM / 2.0 + float(sampling.max())
    # Nearest bone of any label is this one (si_joint's facing test, one
    # label against itself): the joints, between two labels, drop out here.
    candidate = (lab == 0) & (to_bone <= reach)
    if other.any():
        candidate &= to_bone < ndi.distance_transform_edt(~other, sampling=sampling)
    del to_bone
    vi = np.argwhere(candidate)
    pv = at[:, vi[:, 0], vi[:, 1], vi[:, 2]].T.astype(np.int64)
    a = (pv - vi) * sampling  # to its own nearest bone, mm
    la = np.linalg.norm(a, axis=1)
    normal_of = _Normals(bone, sampling)
    n_pv = normal_of(pv)
    shape = np.array(bone.shape)
    found = {k: [] for k in ("i", "far", "n_far", "width")}
    for e in _OFFSETS:
        wi = vi + e
        inside = np.flatnonzero(np.all((wi >= 0) & (wi < shape), axis=1))
        w = wi[inside]
        ok = bone[tuple(w.T)] | candidate[tuple(w.T)]
        i, w = inside[ok], w[ok]
        pw = at[:, w[:, 0], w[:, 1], w[:, 2]].T.astype(np.int64)  # a bone voxel's nearest bone is itself
        b = (pw - vi[i]) * sampling  # from the same point to the bone across
        n_near, n_far = n_pv[i], normal_of(pw)
        # The gap across the slot along the near face's normal, centre to
        # centre, as si_joint measures a joint (its gap field). Taking off a
        # voxel instead read a 4.8 mm phantom gap as 3.7 mm: the nearest
        # bone voxels already sit at the shallow edge of each face.
        width = np.einsum("ij,ij->i", (pw - pv[i]) * sampling, n_near)
        keep = (facing(a[i].T, b.T, la[i], np.linalg.norm(b, axis=1))
                & (np.einsum("ij,ij->i", n_near, n_far) <= MIN_FACE_OPPOSITION)
                & (width > 0) & (width <= MAX_FRACTURE_SLOT_MM))
        found["i"].append(i[keep])
        found["far"].append(pw[keep])
        found["n_far"].append(n_far[keep])
        found["width"].append(width[keep])
    i = np.concatenate(found["i"])
    v = vi[i]
    slot = np.zeros(bone.shape, dtype=bool)
    slot[tuple(v.T)] = True
    patches, n = ndi.label(slot, structure=_RING)
    slot_voxels = np.argwhere(slot)
    return _Slots(label, lo, sampling, v, pv[i], np.concatenate(found["far"]), n_pv[i],
                  np.concatenate(found["n_far"]), np.concatenate(found["width"]),
                  patches[tuple(v.T)], slot_voxels, patches[tuple(slot_voxels.T)], int(n))


class _Normals:
    """Outward surface normals (zyx, unit) of a mask at given voxels, from
    the gradient of the mask smoothed by one voxel. Read off the voxels
    themselves, a staircase on a sloping surface has a step facing a
    riser, which looks like a one-voxel slot; smoothed, it is the slope.
    One voxel is little enough that each face of a one-voxel slot keeps
    its own direction (the gap is a dip in the smoothed mask)."""

    def __init__(self, mask: np.ndarray, sampling: np.ndarray):
        self.smooth = ndi.gaussian_filter(mask.astype(np.float32), 1.0, mode="nearest")
        self.sampling = sampling
        self.shape = np.array(mask.shape)

    def __call__(self, at: np.ndarray) -> np.ndarray:
        grad = np.zeros((len(at), 3))
        for axis in range(3):
            step = np.zeros(3, dtype=np.int64)
            step[axis] = 1
            up = np.minimum(at + step, self.shape - 1)
            down = np.maximum(at - step, 0)
            grad[:, axis] = ((self.smooth[tuple(up.T)] - self.smooth[tuple(down.T)])
                             / (self.sampling[axis] * np.maximum(up[:, axis] - down[:, axis], 1)))
        return _unit(-grad)


def _world(vol: Volume, lo: np.ndarray, idx: np.ndarray) -> np.ndarray:
    return vol.zyx_indices_to_world(np.asarray(idx) + lo) if len(idx) else np.zeros((0, 3))


def _xyz(zyx: np.ndarray) -> np.ndarray:
    return np.asarray(zyx)[..., ::-1]


# --------------------------------------------------------------------------
# The public entry point.


def find_fracture_surfaces(labels_vol: Volume, mirror: Optional[ConfirmedMirror] = None,
                           ct: Optional[Volume] = None, marks: Optional[Sequence[FracturePlane]] = None,
                           fragment_sets: Sequence[FragmentSet] = (),
                           bones: Sequence[int] = (seg.SACRUM, seg.HIP_R, seg.HIP_L),
                           injured: Optional[str] = None) -> FractureSurfaces:
    """The fracture surfaces of ``bones`` (engine label ids).

    ``mirror`` (confirmed; an unconfirmed MirrorReference refuses) enables
    the mirror-twin veto, ``ct`` (on the labels grid) the cortex contrast
    veto and the CT route (7d.1); each one missing is said in the notes.
    ``marks`` are the surgeon's fracture marks (7c.3): they seed the search,
    and where nothing is found near them, with the CT given, their plane
    becomes the surface (source SURGEON_MARKS). ``fragment_sets`` are slice 1's results, one per
    injured side, for the zero-width route. ``injured`` ("right", "left" or
    "both") says what a dense band is compared with (7d.5): the mirrored
    side, unless both sides are injured or there is no confirmed mirror,
    when it is the patient's own bone nearby, and the result says so."""
    if isinstance(mirror, MirrorReference):
        raise ReferenceNotConfirmed("the mirror reference has not been confirmed (mirror.confirm); "
                                    + mirror.preselection_sentence())
    if ct is not None and ct.array.shape != labels_vol.array.shape:
        raise ValueError(f"the CT {ct.array.shape} is not on the label grid {labels_vol.array.shape}")
    unknown = [b for b in bones if b not in BONE_KEYS]
    if unknown:
        raise ValueError(f"fracture surfaces are found in the sacrum and the hips, not label {unknown}")
    if injured not in (None, "right", "left", "both"):
        raise ValueError(f"injured must be 'right', 'left', 'both' or None, got {injured!r}")
    marks = list(marks or [])
    mark_points = np.vstack([m.marks for m in marks]) if marks else np.zeros((0, 3))
    mark_tree = cKDTree(mark_points) if len(mark_points) else None
    sampling = _sampling(labels_vol)
    voxel_mm2 = float(np.prod(sampling)) ** (2.0 / 3.0)
    notes: List[str] = []
    if mirror is None:
        notes.append("mirror-twin veto not applied (no confirmed mirror): a symmetric anatomical notch or foramen "
                     "is not removed by it")
    if ct is None:
        notes.append("cortex contrast veto not applied (no CT): a natural surface lined with cortex is not "
                     "removed by it")

    wanted = list(dict.fromkeys(bones))
    examined = wanted + ([CONTRALATERAL[b] for b in wanted if CONTRALATERAL[b] not in wanted] if mirror else [])
    slots = {b: _slots(labels_vol, b) for b in examined}
    candidate_points = {BONE_KEYS[b]: (_world(labels_vol, s.lo, s.slot_voxels) if s else np.zeros((0, 3)))
                        for b, s in slots.items() if b in wanted}
    trees = {}
    if mirror is not None:
        for b, s in slots.items():
            if s is not None and len(s.slot_voxels):
                trees[b] = (cKDTree(_world(labels_vol, s.lo, s.slot_voxels)), s.patch_of_voxel)
    cortex_hu = {}
    accepted: List[Tuple[int, _Slots, int, Optional[float], List[str]]] = []
    rejected: List[Patch] = []
    small: Dict[str, int] = {}
    for b in wanted:
        s = slots[b]
        key = BONE_KEYS[b]
        small[key] = 0
        if s is None:
            notes.append(f"no {BONE_NAMES[b]} in the labels")
            continue
        if ct is not None:
            cortex_hu[key] = _cortex_hu(labels_vol, ct, b)
        for p in range(1, s.n_patches + 1):
            pairs = s.patch_of_pair == p
            faces = np.unique(np.vstack([s.near[pairs], s.far[pairs]]), axis=0)
            area = 0.5 * len(faces) * voxel_mm2
            if area < MIN_PATCH_AREA_MM2:
                small[key] += 1
                continue
            points = _world(labels_vol, s.lo, s.slot_voxels[s.patch_of_voxel == p])
            centre = points.mean(axis=0)
            extents = np.linalg.svd(points - centre, compute_uv=False) / np.sqrt(len(points))
            extents = np.pad(extents, (0, 3 - len(extents)))
            width = float(np.median(s.width[pairs]))
            face_points = _world(labels_vol, s.lo, faces)
            distance = float(mark_tree.query(face_points)[0].min()) if mark_tree is not None else None
            near_mark = distance is not None and distance <= FAR_FROM_MARKS_MM
            reasons, kept_for = [], []
            if extents[1] < SHEET_ASPECT * extents[2]:
                reasons.append(f"a tube, not a sheet (extents {extents[0]:.1f} / {extents[1]:.1f} / "
                               f"{extents[2]:.1f} mm): a canal or foramen")
            twin = None
            if mirror is not None and CONTRALATERAL[b] in trees:
                twin = _twin_share(points, mirror, trees[CONTRALATERAL[b]], own_patch=p if CONTRALATERAL[b] == b else None)
                if twin > SYMMETRY_TWIN_FRACTION:
                    if near_mark:
                        kept_for.append(f"kept although {100 * twin:.0f}% of it has a mirror twin, because the "
                                        f"surgeon marked a fracture {distance:.0f} mm away")
                    else:
                        reasons.append(f"{100 * twin:.0f}% of it has a mirror twin on the "
                                       f"{BONE_NAMES[CONTRALATERAL[b]]}: anatomy")
            elif mirror is not None:
                twin = 0.0
            ratio = None
            if ct is not None:
                ratio = _cortex_ratio(labels_vol, ct, b, faces + s.lo, cortex_hu[key])
                if ratio >= CORTEX_FRACTION:
                    reasons.append(f"its face reads {100 * ratio:.0f}% of this patient's cortex HU "
                                   f"({cortex_hu[key]:.0f}), at least {100 * CORTEX_FRACTION:.0f}%: cortex, so anatomy")
            if reasons:
                rejected.append(Patch(b, area, width, tuple(float(x) for x in extents), centre, twin, ratio, reasons))
            else:
                accepted.append((b, s, p, distance, kept_for))

    surfaces = [_slot_surface(labels_vol, mirror, b, s, p, distance, kept_for)
                for b, s, p, distance, kept_for in accepted]
    for fs in fragment_sets:
        surfaces = _fragment_surfaces(labels_vol, fs, surfaces, mark_tree, notes)

    route = _CtRoute(mark_tree=mark_tree)
    if ct is not None:
        if mirror is not None and injured != "both":
            route.reference = MIRROR_REFERENCE
        else:
            route.reference = NEARBY_REFERENCE
            why = "both sides are injured" if injured == "both" else "there is no confirmed mirror"
            notes.append(f"a dense band is compared with this patient's own cancellous bone within "
                         f"{IMPACTION_NEARBY_MM:.0f} mm, not with the mirrored side, because {why} (DECISIONS 7d.5): "
                         "normal dense bone, such as the subchondral bone of a joint, can read as impaction")
        notes.append(f"a dense band reads as impaction when at least {IMPACTION_MARGIN_HU:.0f} HU denser than the "
                     f"{route.reference} (IMPACTION_MARGIN_HU: {IMPACTION_MARGIN_PROVENANCE})")
        for b in wanted:
            if slots[b] is not None and BONE_KEYS[b] not in cortex_hu:
                cortex_hu[BONE_KEYS[b]] = _cortex_hu(labels_vol, ct, b)
        _ct_route(labels_vol, ct, mirror, wanted, cortex_hu, route, notes)
        surfaces += _not_already_found(labels_vol, route.surfaces, surfaces, notes)
        rejected += route.rejected
        for s in surfaces:
            if s.source != GAP and mark_tree is not None:
                s.mark_distance_mm = _distance(s, mark_tree)
    else:
        notes.append("CT route not run (no CT): a fracture whose faces touch, an impacted fracture, and one the "
                     "label is painted across are not found")
    for b in wanted:
        if slots[b] is not None and not any(s.label == b for s in surfaces):
            faint = (f", and in the CT a line less than {LUCENT_MIN_CONTRAST_HU:.0f} HU darker or a band less than "
                     f"{IMPACTION_MARGIN_HU:.0f} HU denser than its reference is not seen" if ct is not None else "")
            notes.append(f"no fracture surface found in the {BONE_NAMES[b]}: a fracture whose faces touch, or gape "
                         f"wider than {MAX_FRACTURE_SLOT_MM:.0f} mm, leaves no slot{faint}, so this does not say the "
                         f"{BONE_NAMES[b]} is intact")
    # Matched against what was found only: a marks surface is where he says
    # the fracture is, not a surface seen, so each of its marks stays
    # unmatched (and a reduction still knows nothing found there).
    unmatched = _match_marks(labels_vol, marks, surfaces, notes)
    # The backup is for where the CT shows nothing (7d.1); with no CT that is
    # not known, so the marks stay what slice 1b made them.
    if ct is not None:
        surfaces += _marks_surfaces(labels_vol, mirror, unmatched, wanted, notes)
    elif unmatched:
        notes.append("the plane through the surgeon's marks is not made a fracture surface where nothing was found "
                     "near them, because there is no CT: whether the CT shows a fracture there is not known")
    if mark_tree is not None:
        for s in surfaces:
            if s.source == SURGEON_MARKS:
                s.mark_distance_mm = _distance(s, mark_tree)
        for s in surfaces:
            if s.far_from_marks:
                s.flags.append(f"{s.mark_distance_mm:.0f} mm from every mark the surgeon placed, more than "
                               f"{FAR_FROM_MARKS_MM:.0f} mm: found automatically, not where a fracture was marked")
    _flag_disc_remnants(labels_vol, surfaces, notes)
    # The surgeon's marked fractures first, then the largest.
    surfaces.sort(key=lambda s: (not (s.mark_distance_mm is not None and not s.far_from_marks), -s.area_mm2))
    counts: Dict[int, int] = {}
    for s in surfaces:
        if not s.id:  # a slot of its own; a fragment's surface is named after the fragment
            counts[s.label] = counts.get(s.label, 0) + 1
            s.id = f"{BONE_KEYS[s.label]}_{counts[s.label]}"
    return FractureSurfaces(surfaces, rejected, small, candidate_points, cortex_hu, mirror is not None,
                            ct is not None, len(marks), notes, unmatched, ct is not None, route.reference,
                            IMPACTION_MARGIN_HU if ct is not None else None, route.lucent_points,
                            route.dense_points, route.small)


def _surface_plane(surface: FractureSurface) -> Tuple[np.ndarray, np.ndarray]:
    """A surface's centre and unit normal, from both faces' points."""
    pts = np.vstack([f.points for f in surface.faces if len(f.points)])
    centre = pts.mean(axis=0)
    normal = np.linalg.svd(pts - centre, full_matrices=False)[2][-1]
    return centre, normal / np.linalg.norm(normal)


def _flag_disc_remnants(labels_vol: Volume, surfaces: List[FractureSurface], notes: List[str]) -> None:
    """DECISIONS 7e.2. Every adult sacrum has the remnant disc spaces of its
    fused segments (S1-S2, S2-S3 ...): thin transverse plates across the
    vertebral body column, which can read as a lucent line or, with their
    dense end plates, as an impacted band. On the four CLINIC cases every
    sacral surface the CT route found was read by the surgeon as not a
    fracture, one of them lying exactly along such a junction. A sacral
    surface that lies **within the body column** (its centre within
    DISC_REMNANT_BODY_RADIUS_MM of the line through the S1 and S2 body
    centres) **and across it** (its normal within DISC_REMNANT_MAX_TILT_DEG
    of that line) is **flagged** as a probable disc remnant for the surgeon,
    not dropped: a transverse sacral fracture can run there too."""
    sacral = [s for s in surfaces if s.label == seg.SACRUM and any(len(f.points) for f in s.faces)]
    if not sacral:
        return
    from . import landmarks as landmarks_mod  # only needed when the sacrum has a surface

    marks = landmarks_mod.detect_landmarks(labels_vol)
    if "s1_body_center" not in marks or "s2_body_center" not in marks:
        notes.append("probable disc remnants not checked: the S1 and S2 body centres were not found")
        return
    s1 = np.asarray(marks["s1_body_center"].xyz, dtype=float)
    s2 = np.asarray(marks["s2_body_center"].xyz, dtype=float)
    axis = (s1 - s2) / max(float(np.linalg.norm(s1 - s2)), 1e-9)
    cos_max = np.cos(np.radians(DISC_REMNANT_MAX_TILT_DEG))
    for s in sacral:
        centre, normal = _surface_plane(s)
        off_axis = float(np.linalg.norm(np.cross(centre - s1, axis)))
        across = abs(float(np.dot(normal, axis)))
        if off_axis <= DISC_REMNANT_BODY_RADIUS_MM and across >= cos_max:
            tilt = float(np.degrees(np.arccos(min(1.0, across))))
            s.flags.append(
                f"probable disc remnant (7e.2): it lies across the sacral body, {off_axis:.0f} mm from the line "
                f"through the S1 and S2 body centres and {tilt:.0f} degrees from square to it, where the junction "
                "of two fused sacral segments lies in every adult; a transverse fracture can run here too, so it "
                "is kept for the surgeon to judge")


def _distance(surface: FractureSurface, tree: cKDTree) -> float:
    return float(min(tree.query(f.points)[0].min() for f in surface.faces if len(f.points)))


def nearest_bone_voxels(labels_vol: Volume, points: np.ndarray, reach_mm: float) -> np.ndarray:
    """Per point (world mm), the (z, y, x) of the nearest bone voxel of any
    label within ``reach_mm``, or -1 where there is none: the bone a mark
    lies on (a mark in a fracture's gap takes the nearer face)."""
    labels = labels_vol.array
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    pad = np.ceil(reach_mm / _sampling(labels_vol)).astype(int)
    out = np.full((len(points), 3), -1, dtype=np.int64)
    for i, zyx in enumerate(np.rint(labels_vol.world_to_zyx_indices(points).T).astype(int)):
        lo, hi = np.maximum(zyx - pad, 0), np.minimum(zyx + pad + 1, labels.shape)
        if np.any(hi <= lo):
            continue
        bone = np.argwhere(labels[tuple(slice(a, b) for a, b in zip(lo, hi))] > 0) + lo
        if not len(bone):
            continue
        d = np.linalg.norm(labels_vol.zyx_indices_to_world(bone) - points[i], axis=1)
        j = int(np.argmin(d))
        if d[j] <= reach_mm:
            out[i] = bone[j]
    return out


def _match_marks(labels_vol: Volume, marks: Sequence[FracturePlane], surfaces: Sequence[FractureSurface],
                 notes: List[str]) -> List[UnmatchedMarks]:
    """Each marked fracture with a mark point that no surface on that mark's
    own bone comes within MARK_MATCH_MM of, mark point by mark point; each is
    said in the notes."""
    labels = labels_vol.array
    trees = {}
    for label in {s.label for s in surfaces}:
        faces = [f.points for s in surfaces if s.label == label for f in s.faces if len(f.points)]
        if faces:
            trees[label] = cKDTree(np.vstack(faces))
    out: List[UnmatchedMarks] = []
    for m in marks:
        pts = np.asarray(m.marks, dtype=float).reshape(-1, 3)
        voxel = nearest_bone_voxels(labels_vol, pts, FAR_FROM_MARKS_MM)
        found = voxel[:, 0] >= 0
        bone = np.zeros(len(pts), dtype=np.int64)
        bone[found] = labels[tuple(voxel[found].T)]
        nearest = np.full(len(pts), np.inf)
        for i in np.flatnonzero(found):
            if int(bone[i]) in trees:
                nearest[i] = float(trees[int(bone[i])].query(pts[i])[0])
        missed = ~(nearest <= MARK_MATCH_MM)
        if not missed.any():
            continue
        out.append(UnmatchedMarks(m, missed, bone, voxel, nearest))
        where = []
        for i in np.flatnonzero(missed):
            at = f"({', '.join(f'{c:.0f}' for c in pts[i])})"
            if not bone[i]:
                where.append(f"{at} with no bone within {FAR_FROM_MARKS_MM:.0f} mm")
                continue
            b = int(bone[i])
            on = (BONE_NAMES.get(b) or ("lumbar spine" if b == seg.LUMBAR else None)
                  or seg.LABEL_NAMES.get(b, f"label {b}").replace("_", " "))
            off = f"nearest surface on it {nearest[i]:.0f} mm" if np.isfinite(nearest[i]) else "no surface on it"
            where.append(f"{at} on the {on}, {off}")
        notes.append(f"no fracture surface found within {MARK_MATCH_MM:.0f} mm on the bone it lies on for "
                     f"{int(missed.sum())} of the {len(pts)} marks of the fracture marked at "
                     f"({', '.join(f'{c:.0f}' for c in m.point)}) mm: " + "; ".join(where))
    return out


def _twin_share(points: np.ndarray, mirror: ConfirmedMirror, contralateral, own_patch: Optional[int]) -> float:
    """The share of a patch's points whose mirror image lies within
    SYMMETRY_TWIN_MM of a slot of the contralateral bone (on the sacrum, of
    a slot other than this patch)."""
    tree, patch_of = contralateral
    reflected = mirror.plane.reflect(points)
    if own_patch is None:
        dist, _ = tree.query(reflected, distance_upper_bound=SYMMETRY_TWIN_MM)
        return float(np.mean(np.isfinite(dist)))
    hits = tree.query_ball_point(reflected, SYMMETRY_TWIN_MM)
    return float(np.mean([bool(np.any(patch_of[h] != own_patch)) if h else False for h in hits]))


def _cortex_hu(labels_vol: Volume, ct: Volume, label: int) -> float:
    """This patient's cortex for this bone: the median HU of its rind."""
    labels = labels_vol.array
    sampling = _sampling(labels_vol)
    _, _, box = _box(labels.shape, np.argwhere(labels == label), np.array([2, 2, 2]))
    bone = labels[box] == label
    rind = bone & (ndi.distance_transform_edt(bone, sampling=sampling) <= CORTEX_RIND_MM)
    return float(np.median(ct.array[box][rind]))


def _cortex_ratio(labels_vol: Volume, ct: Volume, label: int, face_voxels: np.ndarray, cortex: float) -> float:
    """The face's own rind (the bone within CORTEX_RIND_MM of its face
    voxels), as a share of the patient's cortex."""
    sampling = _sampling(labels_vol)
    pad = np.ceil(CORTEX_RIND_MM / sampling).astype(int) + 1
    lo, _, box = _box(labels_vol.array.shape, face_voxels, pad)
    face = np.zeros(labels_vol.array[box].shape, dtype=bool)
    face[tuple((face_voxels - lo).T)] = True
    near = (ndi.distance_transform_edt(~face, sampling=sampling) <= CORTEX_RIND_MM) & (labels_vol.array[box] == label)
    return float(np.median(ct.array[box][near])) / cortex if cortex > 0 else float("inf")


# --------------------------------------------------------------------------
# Building a surface: faces, sides, normals, rims.


def _orient(s: _Slots, p: int) -> np.ndarray:
    """+1 / -1 per pair of patch ``p``: whether its near face is face A.
    Each slot voxel crosses the slot one way (from its own nearest face to
    the other); that direction is made to agree from neighbour to
    neighbour over the patch, so face A is one face all along even where
    the surface curves."""
    pairs = np.flatnonzero(s.patch_of_pair == p)
    voxels, which = np.unique(s.v[pairs], axis=0, return_inverse=True)
    which = which.ravel()
    cross = np.zeros((len(voxels), 3))
    np.add.at(cross, which, _unit((s.far[pairs] - s.near[pairs]) * s.sampling))
    cross = _unit(cross)
    lo = voxels.min(axis=0)
    index = np.full(tuple(voxels.max(axis=0) - lo + 1), -1, dtype=np.int64)
    index[tuple((voxels - lo).T)] = np.arange(len(voxels))
    rows, cols = [], []
    for e in _OFFSETS[:13]:
        to = voxels - lo + e
        inside = np.all((to >= 0) & (to < np.array(index.shape)), axis=1)
        j = np.full(len(voxels), -1)
        j[inside] = index[tuple(to[inside].T)]
        ok = j >= 0
        rows.append(np.flatnonzero(ok))
        cols.append(j[ok])
    rows, cols = np.concatenate(rows), np.concatenate(cols)
    graph = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(voxels), len(voxels))).tocsr()
    sign = np.zeros(len(voxels))
    for start in range(len(voxels)):
        if sign[start]:
            continue
        sign[start] = 1.0
        order, parent = breadth_first_order(graph, start, directed=False, return_predecessors=True)
        for node in order[1:]:
            up = parent[node]
            sign[node] = sign[up] * (1.0 if cross[node] @ cross[up] >= 0 else -1.0)
    return sign[which]


def _faces_from_pairs(s: _Slots, p: int):
    """Face A and face B of a slot patch: each face's voxels (box indices)
    and their outward normals (zyx, unit)."""
    pairs = np.flatnonzero(s.patch_of_pair == p)
    sign = _orient(s, p)
    near_a = sign > 0
    vox = {"a": np.vstack([s.near[pairs][near_a], s.far[pairs][~near_a]]),
           "b": np.vstack([s.far[pairs][near_a], s.near[pairs][~near_a]])}
    nrm = {"a": np.vstack([s.n_near[pairs][near_a], s.n_far[pairs][~near_a]]),
           "b": np.vstack([s.n_far[pairs][near_a], s.n_near[pairs][~near_a]])}
    out, counts = {}, {}
    for k in ("a", "b"):
        voxels, which, count = np.unique(vox[k], axis=0, return_inverse=True, return_counts=True)
        normals = np.zeros((len(voxels), 3))
        np.add.at(normals, which.ravel(), nrm[k])
        out[k] = (voxels, _unit(normals))
        counts[k] = dict(zip(map(tuple, voxels), count))
    # A voxel the orientation put on both faces (a strongly folded patch)
    # stays on the face more of its pairs put it on (face A on a tie).
    for k, other in (("a", "b"), ("b", "a")):
        mine, theirs = counts[k], counts[other]
        keep = np.array([mine[v] > theirs.get(v, 0) or (mine[v] == theirs.get(v, 0) and k == "a")
                         for v in map(tuple, out[k][0])], dtype=bool)
        out[k] = (out[k][0][keep], out[k][1][keep])
    return out["a"], out["b"]


def _rims(labels_vol: Volume, label: int, faces: Sequence[np.ndarray], gap: np.ndarray) -> List[np.ndarray]:
    """Per face (voxels on the labels grid), which voxels are its cortical
    rim: within RIM_MM of the bone's outer surface away from this fracture.
    The faces hold only the voxels nearest the slot, so the rest of the
    exposed face is told apart by touching the slot's empty voxels ``gap``:
    counted as outer surface, it made every face voxel on the phantom a rim,
    9 mm deep. Where the slot gapes wider than MAX_FRACTURE_SLOT_MM the
    exposed face is still taken for outer surface."""
    sampling = _sampling(labels_vol)
    every = np.vstack([f for f in faces if len(f)])
    pad = np.ceil(RIM_MM / sampling).astype(int) + 2
    lo, _, box = _box(labels_vol.array.shape, every, pad)
    bone = labels_vol.array[box] == label
    # The box edge cuts through bone; it is not a surface.
    outer = bone & ~ndi.binary_erosion(bone, border_value=1)
    outer[tuple((every - lo).T)] = False
    inside = np.all((gap >= lo) & (gap < lo + np.array(bone.shape)), axis=1)
    if inside.any():
        slot = np.zeros(bone.shape, dtype=bool)
        slot[tuple((gap[inside] - lo).T)] = True
        outer &= ~ndi.binary_dilation(slot, _RING)
    if not outer.any():
        return [np.zeros(len(f), dtype=bool) for f in faces]
    to_outer = ndi.distance_transform_edt(~outer, sampling=sampling)
    return [to_outer[tuple((f - lo).T)] <= RIM_MM if len(f) else np.zeros(0, dtype=bool) for f in faces]


def _lateral(mirror: Optional[ConfirmedMirror], labels_vol: Volume):
    """The patient's left-right axis (toward the right) and the midline
    offset along it: the confirmed plane, or else the scanner's x axis
    through the sacrum's median x."""
    if mirror is not None:
        return mirror.plane.normal, mirror.plane.offset_mm
    sacrum = labels_vol.array == seg.SACRUM
    x = labels_vol.origin[0] + np.arange(labels_vol.array.shape[2]) * labels_vol.spacing[0]
    midline = float(np.median(x[np.nonzero(sacrum)[2]])) if sacrum.any() else float(x.mean())
    return np.array([1.0, 0.0, 0.0]), midline


def _side_words(mirror, labels_vol, centre: np.ndarray, normal_a: np.ndarray) -> Tuple[str, str]:
    """Which way each face lies, from face A's mean outward normal (which
    points at face B): its largest component of left-right (as lateral or
    medial), front-back and up-down."""
    axis, offset = _lateral(mirror, labels_vol)
    outward = axis * (1.0 if centre @ axis - offset >= 0 else -1.0)
    # Face A's normal points at B: pointing laterally, A is the medial side.
    # Each pair is (A's word when the component is positive, when negative).
    parts = [(normal_a @ outward, ("medial", "lateral")), (normal_a[1], ("posterior", "anterior")),
             (normal_a[2], ("caudad", "cephalad"))]
    value, (if_positive, if_negative) = max(parts, key=lambda t: abs(t[0]))
    return (if_positive, if_negative) if value >= 0 else (if_negative, if_positive)


def _slot_surface(labels_vol: Volume, mirror, label: int, s: _Slots, p: int, distance, kept_for) -> FractureSurface:
    (va, na), (vb, nb) = _faces_from_pairs(s, p)
    va, vb = va + s.lo, vb + s.lo
    na, nb = _xyz(na), _xyz(nb)
    gap = s.slot_voxels[s.patch_of_voxel == p] + s.lo
    centre = labels_vol.zyx_indices_to_world(np.vstack([va, vb])).mean(axis=0)
    word_a, word_b = _side_words(mirror, labels_vol, centre, _unit(na.mean(axis=0)))
    voxel_mm2 = float(np.prod(s.sampling)) ** (2.0 / 3.0)
    area = 0.5 * (len(va) + len(vb)) * voxel_mm2  # the slot as found, before its faces are grown
    # Both faces are this label, so the body of each, and what lies opposite
    # it, is the label; facing toward the other face keeps the two apart.
    bone = labels_vol.array == label
    (va, na), (vb, nb) = _whole_faces(labels_vol, [(va, na, bone, bone), (vb, nb, bone, bone)])
    rim_a, rim_b = _rims(labels_vol, label, [va, vb], gap)
    name = BONE_NAMES[label]
    faces = (Face(f"{name}, {word_a} side", label, labels_vol.zyx_indices_to_world(va), na, va, rim_a),
             Face(f"{name}, {word_b} side", label, labels_vol.zyx_indices_to_world(vb), nb, vb, rim_b))
    return FractureSurface("", label, SLOT, faces, float(np.median(s.width[s.patch_of_pair == p])),
                           area, distance, list(kept_for), gap)


def _whole_faces(labels_vol: Volume, faces):
    """Each found face [(voxels, normals xyz, its body's mask, the other
    body's mask)] grown over its body's exposed surface (bone next to empty
    space) that lies within WHOLE_FACE_BAND_MM of the found face's own
    plane, faces within WHOLE_FACE_COS of the found face's mean normal, has
    no voxel of the other body within WHOLE_FACE_OPPOSITE_MM along its
    normal, and is connected to the face found. Returns [(voxels, normals)]
    in the same order, the found voxels first. A face too small to have a
    plane is left as found."""
    sampling = _sampling(labels_vol)
    labels = labels_vol.array
    pad = np.ceil(WHOLE_FACE_BAND_MM / sampling).astype(int) + 2
    cross = ndi.generate_binary_structure(3, 1)
    out = []
    # The ray starts a whole voxel out along every axis: on a CT's anisotropic
    # grid a shorter first step along the coarse axis lands back in the
    # voxel itself, which for a slot (its own label is the other body) reads
    # as bone opposite. The bone opposite is thicker than that step.
    steps = np.arange(float(sampling.max()), WHOLE_FACE_OPPOSITE_MM + 1e-9, 0.5 * float(sampling.min()))
    for voxels, normals, body, other in faces:
        if len(voxels) < 3:
            out.append((voxels, normals))
            continue
        # The face's own plane, refitted to the points within the band of it:
        # a few found voxels on crushed bone behind the face (the crushed
        # phantom's crater floor, 6 mm behind) otherwise pull the plane
        # between the two, and the face grew over the crater.
        points = labels_vol.zyx_indices_to_world(voxels)
        keep = np.ones(len(points), dtype=bool)
        for _ in range(WHOLE_FACE_REFITS):
            centre = points[keep].mean(axis=0)
            plane = np.linalg.svd(points[keep] - centre, full_matrices=False)[2][-1]
            within = np.abs((points - centre) @ plane) <= WHOLE_FACE_BAND_MM
            if within.sum() < 3 or np.array_equal(within, keep):
                break
            keep = within
        toward = _unit(normals.mean(axis=0))
        # Only where the body comes near the plane: a box around those voxels.
        idx = np.argwhere(body)
        near = np.abs((labels_vol.zyx_indices_to_world(idx) - centre) @ plane) <= WHOLE_FACE_BAND_MM
        lo, _, box = _box(labels.shape, np.vstack([idx[near], voxels]), pad)
        own = body[box]
        cand = np.argwhere(own & ndi.binary_dilation(labels[box] == 0, cross))
        if not len(cand):
            out.append((voxels, normals))
            continue
        normal_of = _Normals(own, sampling)
        off = (labels_vol.zyx_indices_to_world(cand + lo) - centre) @ plane
        n_cand = _xyz(normal_of(cand))
        ok = (np.abs(off) <= WHOLE_FACE_BAND_MM) & (n_cand @ toward >= WHOLE_FACE_COS)
        # Along its normal, out of its own bone: the other body opposite it
        # means the two still overlap there (or it is crushed bone behind the
        # face), not a face the other body has slid off.
        at = cand[ok] + lo
        ray = (n_cand[ok][:, ::-1] / sampling)[:, None, :] * steps[None, :, None] + at[:, None, :]
        ray = np.clip(np.rint(ray).astype(np.int64), 0, np.array(labels.shape) - 1)
        opposite = other[ray[..., 0], ray[..., 1], ray[..., 2]].any(axis=1)
        ok[np.flatnonzero(ok)[opposite]] = False
        allowed = np.zeros(own.shape, dtype=bool)
        allowed[tuple(cand[ok].T)] = True
        seeds = np.zeros(own.shape, dtype=bool)
        seeds[tuple((voxels - lo).T)] = True
        extra = np.argwhere(ndi.binary_propagation(seeds, structure=_RING, mask=allowed | seeds) & ~seeds)
        out.append((np.vstack([voxels, extra + lo]), np.vstack([normals, _xyz(normal_of(extra))])))
    return out


# --------------------------------------------------------------------------
# The zero-width route: slice 1's fragment boundaries.


def _fragment_surfaces(labels_vol: Volume, fs: FragmentSet, surfaces: List[FractureSurface], mark_tree,
                       notes: List[str]) -> List[FractureSurface]:
    """Each promoted fragment's boundary with its parent, joined with any
    slot found between the same two bodies; and what slice 1 left
    unexplained, looked in but never taken as a surface."""
    if fs.refused or not fs.fragments:
        return surfaces
    label = seg.HIP_R if fs.side == "right" else seg.HIP_L
    sampling = _sampling(labels_vol)
    voxel_mm2 = float(np.prod(sampling)) ** (2.0 / 3.0)
    cross = ndi.generate_binary_structure(3, 1)
    out = list(surfaces)
    for frag in fs.fragments:
        if frag.parent is None:
            continue
        parent = fs.fragments[frag.parent]
        lo, _, box = _box(frag.mask.shape, np.argwhere(frag.mask), np.array([3, 3, 3]))
        f, pm = frag.mask[box], parent.mask[box]
        # Only the fragment's own body: slice 1 lets up to a tenth of a
        # fragment lie in other pieces (fragments.CONNECTED_SHARE), and on
        # the phantom their boundaries with the main body lay 35-100 mm from
        # the fracture and outnumbered it.
        pieces, n = ndi.label(f, structure=_RING)
        if n > 1:
            f = pieces == np.argmax(np.bincount(pieces.ravel())[1:]) + 1
        face_f = np.argwhere(f & ndi.binary_dilation(pm, cross))
        face_p = np.argwhere(pm & ndi.binary_dilation(f, cross))
        vf, vp = face_f + lo, face_p + lo
        # Where the faces touch there is no empty space to measure a
        # direction into, so the normal is each body's own mask gradient.
        nf = _xyz(_Normals(f, sampling)(face_f))
        np_ = _xyz(_Normals(pm, sampling)(face_p))
        widths = [np.zeros(len(face_f))]
        gaps = [np.zeros((0, 3), dtype=np.int64)]
        routes = [FRAGMENT_BOUNDARY] if len(face_f) else []
        for s in list(out):
            if s.route != SLOT or s.label != label:
                continue
            a, b = s.faces
            a_in_f, b_in_p = frag.mask[tuple(a.voxels.T)].mean(), parent.mask[tuple(b.voxels.T)].mean()
            b_in_f, a_in_p = frag.mask[tuple(b.voxels.T)].mean(), parent.mask[tuple(a.voxels.T)].mean()
            if a_in_f > 0.5 and b_in_p > 0.5:
                mine, theirs = a, b
            elif b_in_f > 0.5 and a_in_p > 0.5:
                mine, theirs = b, a
            else:
                continue
            out.remove(s)
            vf, nf = np.vstack([vf, mine.voxels]), np.vstack([nf, mine.normals])
            vp, np_ = np.vstack([vp, theirs.voxels]), np.vstack([np_, theirs.normals])
            widths.append(np.full(len(mine.voxels), s.width_mm))
            gaps.append(s.gap_voxels)
            if SLOT not in routes:
                routes.append(SLOT)
        if not len(vf) or not len(vp):
            notes.append(f"{fs.side} hip fragment {frag.index}: it touches its parent nowhere and no slot was found "
                         f"between them, so it has no fracture surface")
            continue
        gap = np.vstack(gaps)
        vf, kf = np.unique(vf, axis=0, return_index=True)
        vp, kp = np.unique(vp, axis=0, return_index=True)
        nf, np_ = nf[kf], np_[kp]
        parent_body = parent.mask & ~frag.mask
        (vf, nf), (vp, np_) = _whole_faces(labels_vol, [(vf, nf, frag.mask, parent_body),
                                                        (vp, np_, parent_body, frag.mask)])
        rim_f, rim_p = _rims(labels_vol, label, [vf, vp], gap)
        faces = (Face(f"{fs.side} hip fragment {frag.index}", label, labels_vol.zyx_indices_to_world(vf), nf, vf, rim_f),
                 Face(f"{fs.side} hip {'main body' if frag.parent == 0 else f'fragment {frag.parent}'}", label,
                      labels_vol.zyx_indices_to_world(vp), np_, vp, rim_p))
        flags = []
        if len(face_f):
            flags.append("where its faces touch it is slice 1's boundary between the two bodies' masks, not a "
                         "surface seen in the scan, and only as good as those masks")
        surface = FractureSurface(f"{BONE_KEYS[label]}_fragment_{frag.index}", label, " + ".join(routes), faces,
                                  float(np.median(np.concatenate(widths))), 0.5 * (len(vf) + len(vp)) * voxel_mm2,
                                  None, flags, gap)
        if mark_tree is not None:
            surface.mark_distance_mm = _distance(surface, mark_tree)
        out.append(surface)
    if fs.unexplained is not None and fs.unexplained.any():
        near = ndi.binary_dilation(fs.unexplained, _RING)
        inside = [s for s in out if s.label == label and any(near[tuple(f.voxels.T)].any() for f in s.faces)]
        for s in inside:
            s.flags.append(f"lies in bone that no body carries home (slice 1, {fs.unexplained_cm3:.1f} cm3)")
        if not inside:
            notes.append(f"{fs.unexplained_cm3:.1f} cm3 of the {fs.side} hip is carried home by no body (slice 1), "
                         "and no fracture surface was found in it; it is not taken as a surface by itself")
    return out


# --------------------------------------------------------------------------
# The CT route (7d.1, 7d.5): fractures the label does not show.


@dataclass
class _CtRoute:
    reference: str = ""
    mark_tree: Optional[cKDTree] = None
    surfaces: List[FractureSurface] = field(default_factory=list)
    rejected: List[Patch] = field(default_factory=list)
    small: Dict[str, int] = field(default_factory=dict)
    lucent_points: Dict[str, np.ndarray] = field(default_factory=dict)
    dense_points: Dict[str, np.ndarray] = field(default_factory=dict)


@dataclass
class _Lucent:
    """The voxels of one bone that read as a lucent line, on a box."""

    label: int
    lo: np.ndarray
    voxels: np.ndarray  # (m, 3) box indices
    normals: np.ndarray  # (m, 3) zyx unit, across the line (the direction its bone either side was found along)
    rind: np.ndarray  # (m,) bool, in the bone's rind (CORTEX_RIND_MM)
    hu: np.ndarray  # (m,) the CT's own HU, unsmoothed
    patch_of_voxel: np.ndarray
    n_patches: int
    # (m, 2, 3) box indices: the bone either side of each voxel along its
    # direction, back of normals and ahead of it: the first voxel at least
    # half-way back up from the line to its flank. The fracture's faces.
    edges: np.ndarray
    width_mm: np.ndarray  # (m,) the line's width there, edge to edge, centre to centre


def _smoothed(ct: Volume, box, sampling: np.ndarray, within: np.ndarray) -> np.ndarray:
    """The CT on ``box`` smoothed by CT_SMOOTH_MM over the voxels of
    ``within`` only (a normalised convolution), -inf elsewhere. Smoothed
    across the bone's surface, a one-voxel cortex bled into the bone under
    it: the marrow of a thin iliac wing read 150 HU darker than the bone
    beside it on the phantom, a lucent line the whole wing wide."""
    sigma = CT_SMOOTH_MM / sampling
    weight = ndi.gaussian_filter(within.astype(np.float32), sigma)
    total = ndi.gaussian_filter(np.where(within, ct.array[box], 0).astype(np.float32), sigma)
    return np.where(within, total / np.maximum(weight, 1e-6), -np.inf).astype(np.float32)


def _gather(a: np.ndarray, at: np.ndarray, fill):
    """a at each (z, y, x) of ``at``, ``fill`` where it falls outside a."""
    inside = np.all((at >= 0) & (at < np.array(a.shape)), axis=1)
    out = np.full(len(at), fill, dtype=a.dtype)
    out[inside] = a[tuple(at[inside].T)]
    return out


def _lucent(labels_vol: Volume, ct: Volume, label: int, cortex: float) -> Optional[_Lucent]:
    """Each voxel of the bone darker than the bone on both sides of it, along
    some direction within LUCENT_REACH_MM, by LUCENT_MIN_CONTRAST_HU and at
    least half-way down to soft tissue. The bone's two layers are read
    apart, each smoothed over itself only: inside the bone (deeper than
    CORTEX_RIND_MM) a voxel is compared with interior bone either side, which
    must be cancellous (under CORTEX_FRACTION of this patient's cortex), as a
    fracture face is; in the rind, with the rind either side along the
    surface, the cortex either side of the break."""
    labels = labels_vol.array
    where = np.argwhere(labels == label)
    if not len(where):
        return None
    sampling = _sampling(labels_vol)
    lo, _, box = _box(labels.shape, where, np.array([1, 1, 1]))
    bone = labels[box] == label
    depth = ndi.distance_transform_edt(bone, sampling=sampling)
    shell = bone & (depth <= CORTEX_RIND_MM)
    marrow = _smoothed(ct, box, sampling, bone & ~shell)
    cortex_layer = _smoothed(ct, box, sampling, shell)
    vi = np.argwhere(bone)
    rind = shell[tuple(vi.T)]
    own = np.where(shell, cortex_layer, marrow)
    gv = own[tuple(vi.T)]
    best = np.zeros(len(vi), dtype=np.float32)
    best_dir = np.full(len(vi), -1)
    for d, e in enumerate(_OFFSETS[:13]):
        step_mm = float(np.linalg.norm(e * sampling))
        for k in range(1, int((LUCENT_REACH_MM + float(sampling.max())) // step_mm) + 1):
            flank = np.where(rind,
                             np.minimum(_gather(cortex_layer, vi + k * e, -np.inf),
                                        _gather(cortex_layer, vi - k * e, -np.inf)),
                             np.minimum(_gather(marrow, vi + k * e, -np.inf), _gather(marrow, vi - k * e, -np.inf)))
            dip = flank - gv
            ok = ((dip >= LUCENT_MIN_CONTRAST_HU) & (2.0 * gv <= flank + SOFT_TISSUE_HU) & (dip > best)
                  & (rind | (flank < CORTEX_FRACTION * cortex)))
            best[ok] = dip[ok]
            best_dir[ok] = d
    hit = best_dir >= 0
    voxels = vi[hit]
    e = _OFFSETS[best_dir[hit]]
    layer, level = np.where(rind[hit], 1, 0), gv[hit] + 0.5 * best[hit]
    reach = int((LUCENT_REACH_MM + float(sampling.max())) // float(sampling.min())) + 1
    edges = np.zeros((len(voxels), 2, 3), dtype=np.int64)
    steps = np.zeros((len(voxels), 2))
    for side, sign in enumerate((-1, 1)):
        found = np.zeros(len(voxels), dtype=bool)
        for k in range(1, reach + 1):
            at = voxels + sign * k * e
            value = np.where(layer == 1, _gather(cortex_layer, at, -np.inf), _gather(marrow, at, -np.inf))
            now = ~found & (value >= level)
            edges[now, side], steps[now, side] = at[now], k
            found |= now
        # The flank the dip was measured to is that high, so an edge is met;
        # this only guards a voxel at the box's edge.
        edges[~found, side], steps[~found, side] = voxels[~found], 0
    width = steps.sum(axis=1) * np.linalg.norm(e * sampling, axis=1)
    mask = np.zeros(bone.shape, dtype=bool)
    mask[tuple(voxels.T)] = True
    patches, n = ndi.label(mask, structure=_RING)
    return _Lucent(label, lo, voxels, _unit(e * sampling), rind[hit], ct.array[box][tuple(voxels.T)].astype(float),
                   patches[tuple(voxels.T)], int(n), edges, width)


def _merged(face: np.ndarray, normals: np.ndarray, zone: np.ndarray):
    """One face of a lucent line: its edge voxels, each once with the mean
    of the normals given for it, less any that are part of the line."""
    voxels, which = np.unique(face, axis=0, return_inverse=True)
    which = which.ravel()
    summed = np.zeros((len(voxels), 3))
    np.add.at(summed, which, normals)
    dims = np.maximum(voxels.max(axis=0), zone.max(axis=0)) + 1
    keep = ~np.isin(np.ravel_multi_index(voxels.T, dims), np.ravel_multi_index(zone.T, dims))
    return voxels[keep], _unit(summed[keep])


def _two_faces(bone: np.ndarray, zone: np.ndarray, normal_grid: np.ndarray, sampling: np.ndarray):
    """The bone voxels touching ``zone`` (a mask of the line or band, on the
    same box) on each side of it: side A where the zone's normal at the
    nearest zone voxel points away from them (their outward normal is that
    normal), side B the other way. A voxel mostly beside the zone's edge
    rather than across it is on neither. Returns (voxels A, normals A zyx,
    voxels B, normals B zyx), box indices."""
    near = np.argwhere(bone & ndi.binary_dilation(zone, _RING) & ~zone)
    if not len(near):
        empty = np.zeros((0, 3), dtype=np.int64)
        return empty, np.zeros((0, 3)), empty, np.zeros((0, 3))
    at = ndi.distance_transform_edt(~zone, sampling=sampling, return_distances=False, return_indices=True)
    s = at[(slice(None),) + tuple(near.T)].T
    n = normal_grid[tuple(s.T)]
    vec = (near - s) * sampling
    along = np.einsum("ij,ij->i", vec, n)
    across = np.abs(along) >= 0.5 * np.linalg.norm(vec, axis=1)
    a, b = across & (along < 0), across & (along > 0)
    return near[a], n[a], near[b], -n[b]


def _ct_surface(labels_vol: Volume, mirror, label: int, va, na, vb, nb, zone, source: str, route: str,
                width: float, area: float, flags=(), **ct) -> FractureSurface:
    """A surface from the CT route or the marks: voxels on the labels grid,
    normals xyz, outward (from the bone into the fracture)."""
    centre = labels_vol.zyx_indices_to_world(np.vstack([va, vb])).mean(axis=0)
    word_a, word_b = _side_words(mirror, labels_vol, centre, _unit(na.mean(axis=0)))
    # The label has no gap here, so no outer surface of it lies in the
    # fracture to keep off the rim.
    rim_a, rim_b = _rims(labels_vol, label, [va, vb], np.zeros((0, 3), dtype=np.int64))
    name = BONE_NAMES[label]
    faces = (Face(f"{name}, {word_a} side", label, labels_vol.zyx_indices_to_world(va), na, va, rim_a),
             Face(f"{name}, {word_b} side", label, labels_vol.zyx_indices_to_world(vb), nb, vb, rim_b))
    return FractureSurface("", label, route, faces, float(width), float(area), None, list(flags),
                           source=source, zone_voxels=np.asarray(zone, dtype=np.int64), **ct)


def _extents(points: np.ndarray):
    centre = points.mean(axis=0)
    _, singular, vt = np.linalg.svd(points - centre, full_matrices=False)
    extents = np.pad(singular / np.sqrt(len(points)), (0, 3 - len(singular)))
    return centre, extents, vt[-1]


def _columns(points: np.ndarray, normal: np.ndarray, cell: float) -> Tuple[np.ndarray, int]:
    """Which column along ``normal`` each point lies in, on cells of
    ``cell`` mm across it, and how many columns there are."""
    u = np.cross(normal, [1.0, 0.0, 0.0] if abs(normal[0]) < 0.9 else [0.0, 1.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    cells = np.floor(np.stack([points @ u, points @ v], axis=1) / cell).astype(np.int64)
    _, which = np.unique(cells, axis=0, return_inverse=True)
    which = which.ravel()
    return which, int(which.max()) + 1 if len(which) else 0


def _projected_area(points: np.ndarray, normal: np.ndarray, cell: float) -> float:
    """The area points cover seen along ``normal``, on cells of ``cell`` mm."""
    return float(_columns(points, normal, cell)[1]) * cell * cell


def _ct_route(labels_vol: Volume, ct: Volume, mirror: Optional[ConfirmedMirror], wanted: Sequence[int],
              cortex_hu: Dict[str, float], route: _CtRoute, notes: List[str]) -> None:
    examined = list(wanted) + ([CONTRALATERAL[b] for b in wanted if CONTRALATERAL[b] not in wanted] if mirror else [])
    cortex = dict(cortex_hu)  # the contralateral bones' too, for the twin veto; only the wanted ones are reported
    lucent = {}
    for b in examined:
        key = BONE_KEYS[b]
        if key not in cortex and (labels_vol.array == b).any():
            cortex[key] = _cortex_hu(labels_vol, ct, b)
        lucent[b] = _lucent(labels_vol, ct, b, cortex[key]) if key in cortex else None
    trees = {}
    if mirror is not None:
        for b, z in lucent.items():
            if z is not None and len(z.voxels):
                trees[b] = (cKDTree(_world(labels_vol, z.lo, z.voxels)), z.patch_of_voxel)
    for b in wanted:
        if lucent[b] is None:
            continue
        key = BONE_KEYS[b]
        route.lucent_points[key] = _world(labels_vol, lucent[b].lo, lucent[b].voxels)
        _lucent_surfaces(labels_vol, mirror, lucent[b], cortex[key], trees, route)
        _dense_surfaces(labels_vol, ct, mirror, b, route, notes)


def _lucent_surfaces(labels_vol, mirror, z: _Lucent, cortex: float, trees, route: _CtRoute) -> None:
    sampling = _sampling(labels_vol)
    voxel_mm2 = float(np.prod(sampling)) ** (2.0 / 3.0)
    key = BONE_KEYS[z.label]
    small = f"{key} {CT_LUCENT}"
    route.small.setdefault(small, 0)
    for p in range(1, z.n_patches + 1):
        mine = z.patch_of_voxel == p
        voxels = z.voxels[mine]
        if len(voxels) < 3:
            route.small[small] += 1
            continue
        points = _world(labels_vol, z.lo, voxels)
        centre, extents, plane = _extents(points)
        # Face A lies back along the patch's normal, face B ahead of it;
        # each voxel's own direction is turned to agree.
        ahead = z.normals[mine] @ plane[::-1] >= 0
        normals = z.normals[mine] * np.where(ahead, 1.0, -1.0)[:, None]
        edges = z.edges[mine]
        (va, na), (vb, nb) = [_merged(np.where(ahead[:, None], edges[:, side], edges[:, 1 - side]), sign * normals,
                                      voxels) for side, sign in ((0, 1.0), (1, -1.0))]
        area = 0.5 * (len(va) + len(vb)) * voxel_mm2
        if area < MIN_PATCH_AREA_MM2 or not len(va) or not len(vb):
            route.small[small] += 1
            continue
        va, vb = va + z.lo, vb + z.lo
        na, nb = _xyz(na), _xyz(nb)
        pa, pb = labels_vol.zyx_indices_to_world(va), labels_vol.zyx_indices_to_world(vb)
        width = float(np.median(z.width_mm[mine]))
        reasons = []
        if extents[1] < SHEET_ASPECT * extents[2]:
            reasons.append(f"a tube, not a sheet (extents {extents[0]:.1f} / {extents[1]:.1f} / {extents[2]:.1f} mm): "
                           "a vessel channel or foramen")
        in_rind = z.rind[mine]
        ratio = float(np.median(z.hu[mine][in_rind])) / cortex if in_rind.any() and cortex > 0 else None
        if int(in_rind.sum()) < BREAK_MIN_VOXELS or ratio is None or ratio >= CORTEX_FRACTION:
            reasons.append(f"no break in the cortex ({int(in_rind.sum())} of its voxels in the rind"
                           + (f", reading {100 * ratio:.0f}% of this patient's cortex HU" if ratio is not None else "")
                           + "): a lucency inside intact bone, not a fracture")
        if int((~in_rind).sum()) < BREAK_MIN_VOXELS:
            reasons.append(f"in the cortex only ({int((~in_rind).sum())} of its voxels in the bone beneath it): a thin "
                           "or uneven cortex, not a fracture through the bone")
        twin, kept_for = None, []
        distance = float(route.mark_tree.query(np.vstack([pa, pb]))[0].min()) if route.mark_tree is not None else None
        if mirror is not None and CONTRALATERAL[z.label] in trees:
            twin = _twin_share(points, mirror, trees[CONTRALATERAL[z.label]],
                               own_patch=p if CONTRALATERAL[z.label] == z.label else None)
            if twin > SYMMETRY_TWIN_FRACTION:
                if distance is not None and distance <= FAR_FROM_MARKS_MM:
                    kept_for.append(f"kept although {100 * twin:.0f}% of it has a mirror twin, because the surgeon "
                                    f"marked a fracture {distance:.0f} mm away")
                else:
                    reasons.append(f"{100 * twin:.0f}% of it has a mirror twin on the "
                                   f"{BONE_NAMES[CONTRALATERAL[z.label]]}: anatomy")
        elif mirror is not None:
            twin = 0.0
        if reasons:
            route.rejected.append(Patch(z.label, area, width, tuple(float(x) for x in extents), centre, twin, ratio,
                                        reasons, CT_LUCENT))
            continue
        route.surfaces.append(_ct_surface(
            labels_vol, mirror, z.label, va, na, vb, nb, voxels + z.lo, CT_LUCENT, LUCENT_LINE, width, area,
            [f"found from the CT, a lucent line through the bone with a break in its cortex ({int(in_rind.sum())} "
             f"voxels at {100 * ratio:.0f}% of this patient's cortex HU), not from a gap in the label"] + kept_for))


def _dense_surfaces(labels_vol: Volume, ct: Volume, mirror, label: int, route: _CtRoute, notes: List[str]) -> None:
    """Dense bands of one bone: interior bone (IMPACTION_INTERIOR_MM deep)
    denser than its reference (_density_excess) by IMPACTION_MARGIN_HU,
    each band a sheet reaching the bone's outer layers with bone of the
    usual density on both sides of it. A band's thickness is taken at half
    its height above the bone's typical excess, so it does not depend on the
    margin that found it."""
    found = _density_excess(labels_vol, ct, mirror, label, route.reference, notes)
    if found is None:
        return
    lo, bone, depth, interior, excess = found
    key = BONE_KEYS[label]
    sampling = _sampling(labels_vol)
    voxel_mm3 = float(np.prod(sampling))
    baseline = float(np.nanmedian(excess))
    dense = np.nan_to_num(excess, nan=-np.inf) > IMPACTION_MARGIN_HU
    route.dense_points[key] = _world(labels_vol, lo, np.argwhere(dense))
    patches, n = ndi.label(dense, structure=_RING)
    small = f"{key} {CT_IMPACTED}"
    route.small.setdefault(small, 0)
    cell = float(sampling.max())
    reach = IMPACTION_INTERIOR_MM + float(sampling.max())
    pad = np.ceil(IMPACTION_BAND_PAD_MM / sampling).astype(int) + 1
    covered = np.zeros(bone.shape, dtype=bool)
    objects = ndi.find_objects(patches)
    # The largest first: a band whose dense core is broken into pieces by
    # noise is one band, found from its largest piece, and the other pieces
    # inside it are not found again.
    order = np.argsort(-np.bincount(patches.ravel(), minlength=n + 1)[1:], kind="stable") + 1
    for p in order:
        where = objects[p - 1]
        if where is None:
            continue
        own = np.argwhere(patches[where] == p) + np.array([s.start for s in where])
        if covered[tuple(own.T)].any():
            continue
        if len(own) * voxel_mm3 < MIN_PATCH_AREA_MM2 * float(sampling.min()):
            route.small[small] += 1
            continue
        peak = float(np.percentile(excess[tuple(own.T)], 90))
        half = 0.5 * (peak + baseline)
        plo, _, pbox = _box(bone.shape, own, pad)
        over_idx = np.argwhere(np.nan_to_num(excess[pbox], nan=-np.inf) >= half)
        over_points = labels_vol.zyx_indices_to_world(over_idx + plo + lo)
        # Grown down to half height only within the band's own slab, about
        # its fitted plane: grown freely, it ran on through touching bone
        # over half height, off the band's plane, to 7.5 mm from the right
        # 6 mm phantom's band against the mirror and 12 mm (6 mm) and 30 mm
        # (4 mm) against nearby bone. Started from the dense core's plane,
        # refitted to the band.
        # The first slab is as thick as the band grown freely, seen along the
        # core's normal: too thick if anything, and the refits narrow it.
        centre, _, normal = _extents(labels_vol.zyx_indices_to_world(own + lo))
        slab = np.ones(len(over_idx), dtype=bool)
        band, kept = None, None
        for refit in range(IMPACTION_SLAB_REFITS + 1):
            if refit:
                slab = _in_slab(over_points, centre, normal, thickness, sampling)
            grown = np.zeros(bone[pbox].shape, dtype=bool)
            grown[tuple(over_idx[slab].T)] = True
            pieces, _ = ndi.label(grown, structure=_RING)
            keep = np.unique(pieces[tuple((own - plo).T)])
            band = np.isin(pieces, keep[keep > 0])
            now = band[tuple(over_idx.T)]
            if not now.any() or (kept is not None and np.array_equal(now, kept)):
                break
            kept = now
            if refit:
                centre, _, normal = _extents(over_points[now])
            thickness = int(now.sum()) * voxel_mm3 / _projected_area(over_points[now], normal, cell)
        if not band.any():
            route.small[small] += 1
            continue
        covered[pbox] |= band
        band_idx = np.argwhere(band)
        points = labels_vol.zyx_indices_to_world(band_idx + plo + lo)
        centre, extents, normal = _extents(points)
        area = _projected_area(points, normal, cell)
        thickness = len(band_idx) * voxel_mm3 / area
        median_excess = float(np.median(excess[pbox][band]))
        local_bone = bone[pbox]
        reaches = float(depth[pbox][band].min()) <= reach
        # Bone either side of it, back to this bone's usual density: the two
        # fragments driven together. Subchondral bone lies against its joint
        # surface, with bone on one side only.
        # Looked for from just past the band's blurred edge out to
        # IMPACTION_FLANK_MM past it, so dense bone a few millimetres
        # further on (the subchondral bone of a narrow fragment) does not
        # hide the bone between.
        # Measured from the band's own middle in each column across it, so
        # a voxel at one edge of the band does not look for its far side
        # inside the band.
        column, n_columns = _columns(points, normal, cell)
        along = (points - centre) @ normal
        middle = (np.bincount(column, weights=along, minlength=n_columns)
                  / np.maximum(np.bincount(column, minlength=n_columns), 1))[column]
        mid_points = points + (middle - along)[:, None] * normal
        steps = 0.5 * thickness + np.arange(CT_SMOOTH_MM, IMPACTION_FLANK_MM + 1e-9, 0.5 * float(sampling.min()))
        lowest = []
        for sign in (1.0, -1.0):
            reads = np.full((len(points), len(steps)), np.inf, dtype=np.float32)
            for k, step in enumerate(steps):
                at = np.rint(labels_vol.world_to_zyx_indices(mid_points + sign * step * normal).T).astype(np.int64) - lo
                reads[:, k] = np.nan_to_num(_gather(excess, at, np.nan), nan=np.inf)
            lowest.append(reads.min(axis=1))  # inf where no compared bone lies there
        flanked = float(np.mean(np.logical_and(*[side < half for side in lowest])))
        reasons = []
        if area < MIN_PATCH_AREA_MM2:
            route.small[small] += 1
            continue
        if extents[1] < SHEET_ASPECT * extents[2]:
            reasons.append(f"a lump, not a band (extents {extents[0]:.1f} / {extents[1]:.1f} / {extents[2]:.1f} mm): "
                           "a bone island, not a fracture")
        if not reaches:
            reasons.append("wholly inside the bone, reaching none of its outer layers: not a fracture through it")
        if flanked < IMPACTION_FLANKED_SHARE:
            reasons.append(f"bone of the usual density on both sides of only {100 * flanked:.0f}% of it: dense against "
                           "one side, as the subchondral bone under a joint surface is, not bone driven into itself")
        if reasons:
            route.rejected.append(Patch(label, area, -thickness, tuple(float(x) for x in extents), centre, None, None,
                                        reasons, CT_IMPACTED))
            continue
        # Carried on through the rind, where it was not looked for, along
        # its own plane: so its faces run out to the cortex, where the rims
        # are.
        # A rind voxel continues the band where it lies level with its
        # nearest band voxel along the band's normal: the band carried on
        # outward, not thickened; and within the band's slab about its
        # fitted plane, since level with a voxel at the band's ragged edge
        # can still be off the band.
        local_idx = np.argwhere(local_bone & ~interior[pbox])
        if len(local_idx):
            to_band, nearest = ndi.distance_transform_edt(~band, sampling=sampling, return_indices=True)
            nearest = nearest[(slice(None),) + tuple(local_idx.T)].T
            level = np.abs(((local_idx - nearest) * sampling) @ normal[::-1]) <= 0.5 * float(sampling.max())
            level &= _in_slab(labels_vol.zyx_indices_to_world(local_idx + plo + lo), centre, normal, thickness,
                              sampling)
            extra = local_idx[(to_band[tuple(local_idx.T)] <= reach) & level]
            band[tuple(extra.T)] = True
        grid = np.zeros(band.shape + (3,))
        grid[band] = normal[::-1]
        va, na, vb, nb = _two_faces(local_bone, band, grid, sampling)
        if not len(va) or not len(vb):
            continue
        flags = [f"found from the CT, a dense band {median_excess:.0f} HU denser than the {route.reference}, "
                 f"{thickness:.1f} mm thick: bone driven into itself (impacted), not a gap in the label"]
        if route.reference == NEARBY_REFERENCE:
            flags.append("compared with this patient's own bone nearby, not the mirrored side: normal dense bone, "
                         "such as the subchondral bone of a joint, can read as this")
        route.surfaces.append(_ct_surface(
            labels_vol, mirror, label, va + plo + lo, _xyz(na), vb + plo + lo, _xyz(nb), np.argwhere(band) + plo + lo,
            CT_IMPACTED, DENSE_BAND, 0.0, area, flags, impaction_depth_mm=float(thickness),
            density_reference=route.reference, excess_hu=median_excess))


def _in_slab(points: np.ndarray, centre: np.ndarray, normal: np.ndarray, thickness: float,
             sampling: np.ndarray) -> np.ndarray:
    """Which points (world mm) lie within a band's slab: no further from its
    plane (centre, unit normal) than half its thickness and one voxel."""
    return np.abs((points - centre) @ normal) <= 0.5 * thickness + float(sampling.max())


def _density_excess(labels_vol: Volume, ct: Volume, mirror, label: int, reference: str, notes: List[str]):
    """How much denser each interior voxel of one bone (IMPACTION_INTERIOR_MM
    deep) is than its reference (7d.5), the CT smoothed over the interior
    only: the densest interior bone of the contralateral bone within
    IMPACTION_MIRROR_REACH_MM of the reflected point (MIRROR_REFERENCE), or
    this bone's own cancellous bone within IMPACTION_NEARBY_MM
    (NEARBY_REFERENCE). Returns (box corner, bone, depth mm, interior,
    excess HU: nan where not compared) on the bone's box, or None, said in
    the notes, where nothing can be compared."""
    labels = labels_vol.array
    sampling = _sampling(labels_vol)
    lo, _, box = _box(labels.shape, np.argwhere(labels == label), np.array([1, 1, 1]))
    bone = labels[box] == label
    depth = ndi.distance_transform_edt(bone, sampling=sampling)
    interior = bone & (depth >= IMPACTION_INTERIOR_MM)
    g = _smoothed(ct, box, sampling, interior)
    vi = np.argwhere(interior)
    if not len(vi):
        return None
    if reference == MIRROR_REFERENCE:
        other = CONTRALATERAL[label]
        if other == label:
            lo_c, g_c, interior_c = lo, g, interior
        else:
            where = np.argwhere(labels == other)
            if not len(where):
                notes.append(f"no {BONE_NAMES[other]} to compare the {BONE_NAMES[label]}'s density with: no dense band "
                             f"looked for in the {BONE_NAMES[label]}")
                return None
            lo_c, _, box_c = _box(labels.shape, where, np.array([1, 1, 1]))
            bone_c = labels[box_c] == other
            interior_c = bone_c & (ndi.distance_transform_edt(bone_c, sampling=sampling) >= IMPACTION_INTERIOR_MM)
            g_c = _smoothed(ct, box_c, sampling, interior_c)
        size = tuple(2 * np.ceil(IMPACTION_MIRROR_REACH_MM / sampling).astype(int) + 1)
        densest = ndi.maximum_filter(np.where(interior_c, g_c, -np.inf).astype(np.float32), size=size)
        reflected = mirror.plane.reflect(labels_vol.zyx_indices_to_world(vi + lo))
        at = np.rint(labels_vol.world_to_zyx_indices(reflected).T).astype(np.int64) - lo_c
        ref = _gather(densest, at, -np.inf)
    else:
        # Its cancellous bone: the mean of the interior nearby, then again
        # leaving out what is denser than that by the margin (a dense band
        # itself, the subchondral bone of a joint), which pulled the mean of
        # the impacted phantom's sacrum up past its band.
        size = tuple(2 * np.ceil(IMPACTION_NEARBY_MM / sampling).astype(int) + 1)
        within = interior
        for _ in range(2):
            total = ndi.uniform_filter(np.where(within, g, 0.0).astype(np.float32), size=size)
            count = ndi.uniform_filter(within.astype(np.float32), size=size)
            mean = np.where(count > 0, total / np.maximum(count, 1e-6), np.inf)
            within = interior & (g < mean + IMPACTION_MARGIN_HU)
        ref = mean[tuple(vi.T)]
    compared = np.isfinite(ref)
    if compared.mean() < 0.5:
        notes.append(f"only {100 * compared.mean():.0f}% of the {BONE_NAMES[label]}'s interior has interior bone at "
                     f"the mirrored place to compare its density with")
    if not compared.any():
        return None
    excess = np.full(bone.shape, np.nan, dtype=np.float32)
    excess[tuple(vi[compared].T)] = g[tuple(vi[compared].T)] - ref[compared]
    return lo, bone, depth, interior, excess


def _not_already_found(labels_vol: Volume, found: List[FractureSurface], surfaces: List[FractureSurface],
                       notes: List[str]) -> List[FractureSurface]:
    """The CT route's surfaces less those the gap route already has: most of
    a lucent line lying within two voxels of a gap surface on its bone."""
    reach = 2.0 * float(_sampling(labels_vol).max())
    out = []
    for s in found:
        gap = [np.vstack([f.points for f in g.faces] + ([labels_vol.zyx_indices_to_world(g.gap_voxels)]
                                                         if len(g.gap_voxels) else []))
               for g in surfaces if g.label == s.label and g.source == GAP]
        if gap and s.source == CT_LUCENT:
            share = float(np.mean(cKDTree(np.vstack(gap)).query(labels_vol.zyx_indices_to_world(s.zone_voxels))[0]
                                  <= reach))
            if share > 0.5:
                notes.append(f"a lucent line in the {BONE_NAMES[s.label]} ({s.area_mm2:.0f} mm2) is the gap route's own "
                             f"surface ({100 * share:.0f}% of it beside one), so it is not listed twice")
                continue
        out.append(s)
    return out


def _marks_surfaces(labels_vol: Volume, mirror, unmatched: List[UnmatchedMarks], wanted: Sequence[int],
                    notes: List[str]) -> List[FractureSurface]:
    """Where the CT and the gap route found nothing near the surgeon's marks
    (7d.1), the plane through all of that fracture's marks, clipped to the
    bone those marks lie on and to within NEAR_MARKS_MM of them: a cut one
    voxel thick, and the bone touching it on each side as its two faces."""
    labels = labels_vol.array
    sampling = _sampling(labels_vol)
    voxel_mm2 = float(np.prod(sampling)) ** (2.0 / 3.0)
    half = 0.5 * float(sampling.max())
    out = []
    for um in unmatched:
        plane = um.plane
        for b in sorted({int(x) for x in um.bone[um.unmatched]}):
            if b not in wanted:
                continue
            marks = plane.marks[um.unmatched & (um.bone == b)]
            centre_idx = np.rint(labels_vol.world_to_zyx_indices(marks).T).astype(np.int64)
            lo, _, box = _box(labels.shape, centre_idx, np.ceil(NEAR_MARKS_MM / sampling).astype(int) + 2)
            vi = np.argwhere(labels[box] == b)
            if not len(vi):
                continue
            world = labels_vol.zyx_indices_to_world(vi + lo)
            near = cKDTree(marks).query(world)[0] <= NEAR_MARKS_MM
            off = (world - plane.point) @ plane.normal
            cut = near & (np.abs(off) <= half)
            if not cut.any():
                notes.append(f"the plane marked at ({', '.join(f'{c:.0f}' for c in plane.point)}) mm does not cross the "
                             f"{BONE_NAMES[b]} within {NEAR_MARKS_MM:.0f} mm of its marks: no surface made from it")
                continue
            cut_mask = np.zeros(labels[box].shape, dtype=bool)
            cut_mask[tuple(vi[cut].T)] = True
            beside = ndi.binary_dilation(cut_mask, _RING)[tuple(vi.T)] & ~cut & near
            va, vb = vi[beside & (off < 0)] + lo, vi[beside & (off > 0)] + lo
            if not len(va) or not len(vb):
                continue
            n = np.asarray(plane.normal, dtype=float)
            out.append(_ct_surface(labels_vol, mirror, b, va, np.tile(n, (len(va), 1)), vb, np.tile(-n, (len(vb), 1)),
                                   vi[cut] + lo, SURGEON_MARKS, MARKED_PLANE, float("nan"),
                                   0.5 * (len(va) + len(vb)) * voxel_mm2, [MARKS_SURFACE_FLAG]))
            notes.append(f"the fracture marked at ({', '.join(f'{c:.0f}' for c in plane.point)}) mm is a surface "
                         f"from the surgeon's marks on the {BONE_NAMES[b]} ({SURGEON_MARKS}): nothing was found near "
                         f"{len(marks)} of its marks")
    return out


# --------------------------------------------------------------------------
# The sacral split (7c.5).

SPLIT_UNCONFIRMED = ("UNCONFIRMED: the sacral split is proposed automatically and the surgeon has not confirmed it "
                     "on the review sheet (DECISIONS 7c.5); it is not to be used as confirmed")


@dataclass
class SacralSplit:
    side: str  # "right" or "left"
    mask: Optional[np.ndarray]  # bool on the labels grid: the lateral fragment; None when refused
    volume_cm3: float
    surface_ids: List[str]  # the sacral fracture surfaces it was cut along
    plane_point: Optional[np.ndarray]  # world mm
    plane_normal: Optional[np.ndarray]  # unit, pointing lateral
    plane_rms_mm: float  # how far the found faces lie off the cut plane
    # Approximate share of the cut where a fracture surface was found (by any
    # route but the surgeon's marks, which are not found); the rest is
    # carried across by the plane.
    slot_share: float
    refused: str = ""
    confirmed_by: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    @property
    def confirmed(self) -> bool:
        return self.confirmed_by is not None

    def sentence(self) -> str:
        if self.refused:
            return f"{self.side} sacrum: no split ({self.refused})"
        text = (f"{self.side} sacrum: lateral fragment {self.volume_cm3:.1f} cm3 split off along "
                f"{', '.join(self.surface_ids)} (cut plane rms {self.plane_rms_mm:.1f} mm; a surface found over about "
                f"{100 * self.slot_share:.0f}% of the cut, the rest carried across by the plane)")
        return text + (f"; confirmed by {self.confirmed_by}" if self.confirmed else f"; {SPLIT_UNCONFIRMED}")


def split_sacrum(labels_vol: Volume, surfaces: FractureSurfaces,
                 mirror: Optional[ConfirmedMirror] = None) -> Dict[str, SacralSplit]:
    """The lateral sacral fragment on each side, cut off along that side's
    sacral fracture surfaces. Unconfirmed until confirm_split; refused,
    with the reason, wherever no split can be made from what was found."""
    if isinstance(mirror, MirrorReference):
        raise ReferenceNotConfirmed("the mirror reference has not been confirmed (mirror.confirm); "
                                    + mirror.preselection_sentence())
    axis, offset = _lateral(mirror, labels_vol)
    out = {}
    for side, sign in (("right", 1.0), ("left", -1.0)):
        mine = [s for s in surfaces.surfaces if s.label == seg.SACRUM
                and sign * (np.vstack([f.points for f in s.faces]).mean(axis=0) @ axis - offset) > 0]
        if not mine:
            out[side] = _refused(side, f"no sacral fracture surface found on the {side}; no split is guessed")
            continue
        out[side] = _split_one(labels_vol, side, sign * axis, mine, mirror)
    # Two pieces sharing bone would move it twice, once with each hip.
    if not out["right"].refused and not out["left"].refused:
        shared = int((out["right"].mask & out["left"].mask).sum())
        if shared:
            for side in ("right", "left"):
                split = out[side]
                out[side] = _refused(side, f"its piece shares {shared} voxels with the other side's, so neither is "
                                           "a lateral fragment; no split is guessed", split.surface_ids,
                                     point=split.plane_point, normal=split.plane_normal, rms=split.plane_rms_mm)
    return out


def _refused(side: str, why: str, ids=(), **plane) -> SacralSplit:
    return SacralSplit(side, None, 0.0, list(ids), plane.get("point"), plane.get("normal"),
                       plane.get("rms", float("nan")), 0.0, refused=why, notes=[f"{side} sacrum: no split ({why})"])


def _split_one(labels_vol: Volume, side: str, outward: np.ndarray, mine: List[FractureSurface],
               mirror) -> SacralSplit:
    ids = [s.id for s in mine]
    points = np.vstack([f.points for s in mine for f in s.faces])
    centre = points.mean(axis=0)
    normal = np.linalg.svd(points - centre, full_matrices=False)[2][-1]
    normal = normal if normal @ outward >= 0 else -normal
    rms = float(np.sqrt(np.mean(((points - centre) @ normal) ** 2)))
    plane = {"point": centre, "normal": normal, "rms": rms}
    if rms > MAX_FRACTURE_SLOT_MM:
        return _refused(side, f"the {side} sacral fracture surfaces lie {rms:.1f} mm (rms) off any one plane, so "
                              "the plane cannot carry the cut across; no split is guessed", ids, **plane)
    lateral_cos = float(normal @ outward)
    if lateral_cos < SPLIT_MIN_LATERAL_COS:
        return _refused(side, f"the cut plane is not lateral: its normal lies {np.degrees(np.arccos(lateral_cos)):.0f} "
                              f"degrees from left-right, more than {np.degrees(np.arccos(SPLIT_MIN_LATERAL_COS)):.0f} "
                              "(cut along a transverse fracture, the piece would be the whole upper sacrum); no split "
                              "is guessed", ids, **plane)
    # Face by face, which is the lateral piece's: its outward normal points medially.
    lateral_faces = [f for s in mine for f in s.faces if f.normals.mean(axis=0) @ normal < 0]
    medial_faces = [f for s in mine for f in s.faces if f.normals.mean(axis=0) @ normal >= 0]
    if not lateral_faces or not medial_faces:
        return _refused(side, "the faces of the sacral fracture do not face each other across the cut plane", ids, **plane)

    labels = labels_vol.array
    sampling = _sampling(labels_vol)
    sacrum_idx = np.argwhere(labels == seg.SACRUM)
    lo, _, box = _box(labels.shape, sacrum_idx, np.array([1, 1, 1]))
    sacrum = labels[box] == seg.SACRUM
    idx = np.argwhere(sacrum)
    signed = (labels_vol.zyx_indices_to_world(idx + lo) - centre) @ normal
    # Two voxels thick, so no diagonal neighbour bridges the cut.
    band_mm = float(sampling.max())
    band = np.zeros(sacrum.shape, dtype=bool)
    band[tuple(idx[np.abs(signed) <= band_mm].T)] = True
    pieces, _ = ndi.label(sacrum & ~band, structure=_RING)

    def owners(faces):
        vox = np.vstack([f.voxels for f in faces]) - lo
        ids_ = pieces[tuple(vox.T)]
        return set(int(i) for i in np.unique(ids_[ids_ > 0]))

    lateral_ids, medial_ids = owners(lateral_faces), owners(medial_faces)
    if not lateral_ids:
        return _refused(side, "the lateral face lies wholly in the cut band; the fragment is too thin to split", ids, **plane)
    if lateral_ids & medial_ids:
        return _refused(side, "the cut plane does not separate the two faces of the sacral fracture (the surface "
                              "curves too much for one plane); no split is guessed", ids, **plane)
    lateral = np.isin(pieces, sorted(lateral_ids))
    lateral_side = np.zeros(sacrum.shape, dtype=bool)
    lateral_side[tuple(idx[signed > 0].T)] = True
    # The band's lateral half goes with the piece it touches, however deep.
    lateral = ndi.binary_propagation(lateral, structure=_RING, mask=lateral | (band & lateral_side))
    mask = np.zeros(labels.shape, dtype=bool)
    mask[box] = lateral
    voxel_cm3 = float(np.prod(sampling)) / 1000.0
    volume = float(lateral.sum()) * voxel_cm3
    if volume < SPLIT_MIN_CM3:
        return _refused(side, f"the piece cut off is {volume:.1f} cm3, under the {SPLIT_MIN_CM3:.1f} cm3 smallest "
                              "fragment in the ring", ids, **plane)
    axis, offset = _lateral(mirror, labels_vol)
    piece = labels_vol.zyx_indices_to_world(np.argwhere(lateral) + lo)
    across = float(np.max(-(piece @ axis - offset) * np.sign(outward @ axis)))
    if across > SPLIT_MIDLINE_MM:
        return _refused(side, f"the piece cut off reaches {across:.0f} mm past the midline, more than "
                              f"{SPLIT_MIDLINE_MM:.0f} mm, so it holds bone of the other side and is not the {side} "
                              "lateral fragment; no split is guessed", ids, **plane)
    hip = seg.HIP_R if side == "right" else seg.HIP_L
    hip_mask = labels == hip
    if not hip_mask.any():
        return _refused(side, f"there is no {side} hip to carry the lateral fragment", ids, **plane)
    _, _, hbox = _box(labels.shape, np.argwhere(mask), np.ceil(AURICULAR_MAX_MM / sampling).astype(int) + 1)
    to_hip = ndi.distance_transform_edt(~hip_mask[hbox], sampling=sampling)
    if not (to_hip[mask[hbox]] <= AURICULAR_MAX_MM).any():
        return _refused(side, f"the piece cut off does not reach the {side} SI joint (nowhere within "
                              f"{AURICULAR_MAX_MM:.0f} mm of the {side} hip), so it is not the lateral fragment",
                        ids, **plane)
    other = "left" if side == "right" else "right"
    other_hip = labels[hbox] == (seg.HIP_L if side == "right" else seg.HIP_R)
    if other_hip.any():
        closest = float(ndi.distance_transform_edt(~other_hip, sampling=sampling)[mask[hbox]].min())
        if closest <= AURICULAR_MAX_MM:
            return _refused(side, f"the piece cut off comes within {closest:.1f} mm of the {other} hip, so it would "
                                  f"carry the {other} SI joint and moving it with the {side} hip would pull that joint "
                                  "apart; no split is guessed", ids, **plane)
    # The cut through bone (the band's voxels over its thickness) against
    # the slot's own area: how much of the split the plane extrapolates.
    cut_mm2 = float((band & sacrum).sum()) * float(np.prod(sampling)) / (2.0 * band_mm)
    slot_mm2 = sum(s.area_mm2 for s in mine if s.source != SURGEON_MARKS)
    share = slot_mm2 / (slot_mm2 + cut_mm2) if slot_mm2 + cut_mm2 > 0 else 0.0
    notes = [SPLIT_UNCONFIRMED]
    marked = [s.id for s in mine if s.source == SURGEON_MARKS]
    if marked:
        notes.append(f"cut along the plane through the surgeon's marks ({', '.join(marked)}), where no fracture was "
                     "found in the CT or the label (DECISIONS 7d.1): the split is where he says the fracture is")
    if share < 0.5:
        notes.append(f"more than half of this cut ({100 * (1 - share):.0f}%) is the plane carried on from "
                     f"{slot_mm2:.0f} mm2 of fracture surface, not a surface found: check it with particular care")
    if rms > 0.5 * MAX_FRACTURE_SLOT_MM:
        notes.append(f"the {side} sacral fracture is not flat (rms {rms:.1f} mm off the cut plane): check the cut")
    if mirror is None:
        notes.append("lateral was taken from the scanner's x axis, not a confirmed mirror plane")
    return SacralSplit(side, mask, volume, ids, centre, normal, rms, float(share), notes=notes)


def confirm_split(split: SacralSplit, confirmed_by: str) -> SacralSplit:
    """The surgeon's confirmation of a split on the review sheet: who, and
    when. A refused split cannot be confirmed."""
    if split.refused:
        raise ValueError(f"there is no {split.side} split to confirm: {split.refused}")
    if not confirmed_by:
        raise ValueError("a confirmation says who confirmed the split")
    return replace(split, confirmed_by=confirmed_by, notes=[n for n in split.notes if n != SPLIT_UNCONFIRMED])
