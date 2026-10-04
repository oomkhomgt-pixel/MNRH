"""Reduction by congruence: where each moving unit of a broken pelvis goes.

displacement-finder DECISIONS 7a.5 and 7c (slice 1b), corridor-finder
DECISIONS 3.1, 3.2 and 3.6. The mirror alone is not accurate enough to put
a hemipelvis back: on normal pelvises it is off by a median of about 5 mm
at the SI joint and 10 mm at the symphysis, and most of that is genuine
left-right asymmetry (DECISIONS, the table under section 1). So the mirror
gives only the starting pose, and the pose is then fitted by congruence of
the fracture surfaces and the joint surfaces (the "jigsaw" of 2.5).

**Moving units.** Each hip bone with what travels with it: the lateral
sacral fragment when the sacrum is split (fracture_surface.split_sacrum,
7c.5) and the femoral head when the labels have one, since the head sits
in the acetabulum and a reduced hip with its head left behind would put the
head through the cup. Each promoted fragment of slice 1 is a unit of its
own. Static: the central sacrum, L5, and on a unilateral injury the intact
hemipelvis.

**Start.** A unilateral injury starts from the mirror: each body's
``to_reference`` from slice 1 (fragments.find_fragments), which the
confirmed plane placed. A bilateral injury has no mirror (2.4), so each
hemipelvis starts where it lies.

**The fit.** All units at once, by iterated point-to-plane steps (the step
register.point_to_plane takes, for several bodies):

- fracture **rims** (7c.6) meet their partner rims: across the fracture, a
  rim point lies on the partner face's tangent plane, one voxel layer off
  it (both faces are voxel centres, half a layer each side of the surface
  between them); along the fracture, where both the rim point and its
  partner lie on the outer cortex, the rim lies on the partner's outer
  cortex continued, which is what stops one face sliding over the other.
  The cancellous face is not fitted: crushed bone would pull it. Each face
  is its body's whole broken surface (fracture_surface's docstring), so its
  rim is the body's own outline, not the outline of where the two bodies
  happen to overlap as scanned. A sacral fracture a split was cut along is
  fitted as the split's whole boundary: the slot where it gapes, the
  split's contact where it touches;
- each **SI joint** closes to its target anterior width (7c.2): the intact
  side's si_joint measurement capped at 4 mm, or 4 mm when both sides are
  injured (si_joint.bridging_widths, the definition corridor-finder 2.2
  shares);
- the **symphysis** closes to SYMPHYSIS_TARGET_GAP_MM (7c.7).

A joint's target is a width: it is closed along the joint's own plane, so
it says nothing about where along the joint one side sits. Its facing
pairs are closed to the target, and the reduced joint is then measured the
way its target was (si_joint's 90th-percentile anterior gap is not a
pair's gap; the difference shows in the joint's mismatch). Every distance
is centre to centre, as si_joint measures a joint. Each region pulls with the same total weight whatever its point
count, so a large SI surface does not drown a fracture rim, and a pair far
off pulls as if it were HUBER_MM off. A motion no surface resists is never
taken: along it each unit stays where it started.

**What each region reports** (agreed with Corridor Finder): the larger of
the 90th-percentile mismatch after the fit and the error measured on
phantoms for that kind of region at its displacement (phantom_bound_mm,
DECISIONS 7d.2: measured per displacement from 0 to 30 mm, read where the
fit found the region's units displaced), and where its reduction rests on
the mirror, the mirror's floor (below); ``inf`` when the region is
unconstrained, with the reason in the notes, never a small number. The SI
joint and the symphysis are measured on the reduced labels the way their
targets were (si_joint.measure_joint_widths; symphysis_gap below). A region
is unconstrained when:

- it has too little rim or joint surface to pair (fewer than MIN_PAIRS,
  the engine's minimum for a rigid fit);
- its rims disagree: after the fit they still lie RIMS_DISAGREE_MM apart
  (90th percentile);
- some rigid motion that no surface in the whole fit resists would move
  its two sides relative to each other (PIN_MIN_SLOPE). A flat joint lets
  a hemipelvis slide along it; if nothing else pins that slide, the joint's
  error is unknown, whatever its mismatch reads;
- the fit leaves it as scanned (a fracture with both faces on one unit,
  below), or the surgeon marked a fracture there and no surface was found;
- it is a whole unit nothing pins (below);
- the fit moves its two sides relative to each other further than any
  phantom its bound was measured on reported a number at
  (PHANTOM_TRAVEL_MM: 27-28 mm; the phantoms went to 30 mm), or moves one
  of its units that far at another region: the bound says nothing beyond
  the displacements it was measured on;
- it is an impacted fracture and there is no mirror to take the length
  lost to impaction from (below).

Each region's error is the error of its two sides **relative to each
other**: at a fracture between a fragment and its parent, how far the
fragment lies from where it belongs on the parent. A screw that crosses
the fracture depends on that, not on where the pair sits in the scanner.
Where a unit itself is not pinned (some motion no surface resists moves
it NULL_RELATIVE_SHARE per mm or more), it stays where it started along
that motion, a pose no surface checked, and the whole unit is a region of
its own, ``unit_<name>_unpinned``, unconstrained, covering all of its bone
(UNIT_COVER_CELL_MM); so is a unit no region touches. The regions joining
it say so only where the motion moves their own two sides apart: a turn
about an axis through a region leaves that region nearly closed and
finite, while bone far from it swings. A fracture whose two faces lie on one unit (or on
bone that does not move) is left as scanned: the fit does not reduce it,
and how far it is out of place is not measured, so it is unconstrained.
Its rims' mismatch is no measure of that: rims are paired only within
RIM_PAIR_MAX_MM and facing squarely, so on the iliac phantom slid 6, 12
and 20 mm (fit as both injured; measured in review, before the faces were
grown) the mismatch read 4.3, 4.9 and 5.4 mm.
A fracture the surgeon marked with a mark point no surface matches
(FractureSurfaces.unmatched_marks: none on that mark's bone within
fracture_surface.MARK_MATCH_MM) is a region too, ``fracture_mark_<k>``,
unconstrained and placed at those mark points, each moved with the unit
it lies on: the fit knows nothing about the fracture there, and a missing
region would read as safe.

**Impacted fractures** (7d.6). A fracture found as a dense band
(fracture_surface.CT_IMPACTED) has no gap: its two faces lie either side
of bone driven into itself. Its rims are fitted along the fracture as any
fracture's are, but across it they do not meet: each rim point is held as
far from its partner face as at the mirror start, the length lost to
impaction taken from the mirrored side. Such a region rests on the mirror:
its notes say so and its error is at least the mirror's floor
(MIRROR_FLOOR_MM). So does any region whose two sides, or any unit whose
pose, a motion only those rows pin moves (``unit_<name>_on_mirror``, over
all of its bone); with both sides injured there is no mirror, and the
impacted region is unconstrained. An impacted surface a sacral split was
cut along is fitted on its own two faces, not as the split's boundary,
whose cut runs through the band and would hold the impaction as scanned.

**What the phantoms show** (1.5 mm voxels; the README lists each case,
PHANTOM_BOUND_TABLE_MM the worst per displacement, PHANTOM_TRAVEL_MM how far
they were displaced):
a fracture surface a few centimetres across is a short lever for a whole
hemipelvis, and a degree off at the sacrum is several millimetres at the
pubis. The fit's own cost is lower at the pose it lands on than at the
truth (on the sacral phantom slid 6 mm up, 0.71 against 0.87): the rims
resist a slide along the fracture only at the outline, so what remains is
the evidence's error, not the search's. The phantom's SI joint and
symphysis are flat, so with no fracture to pin it a hip slides along them,
both read unconstrained, and so does the hip as a whole.

**Mirror departure** (7c.4). On a unilateral injury each unit whose fitted
pose departs from its mirror start by more than the mirror's measured
normal floor for a region (MIRROR_FLOOR_MM) is flagged for the surgeon's
review. The congruence pose is used either way.

**Acceptance** (7c.8). The result is a corridor_engine.reduction.Reduction
with ``accepted_by`` left None: nothing is planned on it until the surgeon
accepts the case on the before/after sheet, and its notes say so.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from . import landmarks as landmarks_mod
from . import segmentation as seg
from . import si_joint
from .fracture_surface import (CT_IMPACTED, MARK_MATCH_MM, MAX_FRACTURE_SLOT_MM, RIM_MM, Face, FractureSurface,
                               FractureSurfaces, SacralSplit, _Normals, _rims, _whole_faces)
from .fragments import MIN_PAIRS, FragmentSet, _surface
from .mirror import surface_points
from .fracture import NEAR_MARKS_MM
from .reduction import REGION_RADIUS_MM, Move, Reduction, apply_moves
from .register import transform_points
from .volume import Volume

# DECISIONS 7c.7: the median symphyseal gap of the normal CTPelvic1K
# pelvises, measured by symphysis_gap below, centre to centre: 258 of the
# 275 normal label files (the other 17, all KITS19, stop above the
# symphysis), range 2.43-7.65 mm, 5th-95th percentile 3.32-6.20 mm; by
# subset ABDOMEN 4.63 (n 35), MSD Task 10 4.90 (155), KITS19 4.72 (27),
# CERVIX 5.23 (41). Centre to centre is the gap plus about a voxel (the
# phantom's 6 mm symphysis reads 7.5 mm at 1.5 mm voxels), so a reduced
# symphysis is only compared with it measured the same way.
SYMPHYSIS_TARGET_GAP_MM = 4.93
SYMPHYSIS_TARGET_RANGE_MM = (3.32, 6.20)  # 5th-95th percentile of the same normals
SYMPHYSIS_REACH_MM = si_joint.AURICULAR_MAX_MM  # each pubic body within this of a joint voxel
SYMPHYSIS_MIN_LEVELS = 2  # a joint seen on fewer axial levels is not measured
SI_TARGET_CAP_MM = si_joint.MAX_BRIDGE_MM  # 7c.2

# The fit.
RIM_PAIR_MAX_MM = 2.0 * MAX_FRACTURE_SLOT_MM  # rims further apart than this are not paired
INPLANE_MIN_SHARE = 0.3  # a rim voxel whose outer normal lies this little along the fracture gives no sliding row
FACE_NORMAL_RADIUS_MM = 2.0 * RIM_MM  # a rim point's fracture direction is the face's within this
# A pair is made only where the two surfaces face each other squarely,
# within about 25 degrees of opposite. si_joint locates a joint at 120
# degrees (FACING_COS), looking at the empty space between; pairs that loose
# took in the curved surround of the phantom's pubic bodies and pulled it to
# the joint's width, and corner voxels into the rims, and dragged the fit
# 8-11 mm off from starts 3-8 mm off. Squarely facing, every start tried
# settled on one pose.
SQUARE_FACING_COS = -0.9
HUBER_MM = 2.0  # a pair mismatched by more than this pulls as if by this
MAX_ROUNDS = 120
JOINT_REPAIRS = 3  # a joint is re-paired this many times, each once the fit has settled
SETTLED_MM = 0.01  # no unit point moved more than this in a round
MAX_STEP_MM = 2.0  # no unit point moves more than this in one round
DAMPING = 1e-3  # Levenberg damping, relative to each parameter's own curvature

# When a region is unconstrained (see the module docstring).
# A motion that changes the fit's mean-square mismatch by less than this
# squared, per mm moved, is one no surface resists: a tenth of a millimetre
# of rms mismatch per millimetre cannot be told from the voxel staircase.
# Chosen, not calibrated; see RIMS_DISAGREE_MM for what it was checked on.
PIN_MIN_SLOPE = 0.1
# Such a motion makes a region unconstrained when it moves the region's two
# sides relative to each other by at least this share of the motion.
NULL_RELATIVE_SHARE = 0.25
# The weakest motion the sacral phantoms' fracture rims resist reads 0.013
# (a slope of 0.11): a vertical slide along the fracture, held only by the
# top of its outline and the contact below. The phantom's flat joints,
# closed along their plane, leave their slides at exactly 0.
# Rims still this far apart (90th percentile) after the best rigid fit do
# not agree: above every mismatch a phantom fit read when its fracture
# landed within its bound (at most 2.1 mm, at 1.5 mm voxels). Not
# calibrated on real cases.
RIMS_DISAGREE_MM = 3.0

# The error measured on phantoms for each kind of region, per displacement
# (DECISIONS 7d.2): the worst landing error of a region's side relative to
# its other side, before rounding onto the grid, wherever the region reported
# a number, over the 117 fits displacement-finder/tools/phantom_bound.py runs
# (1.5 mm voxels; the README lists them): every recovery phantom of slice 1b
# (each sacral fracture, right, left and both, hinged 2-3 degrees and slid
# 1-1.5 mm, 6 mm up, back or forward or 4 mm down; the iliac wing moved 5 mm,
# or opened 2-3 mm and slid 4-6 mm; the crushed sacral fracture), the same
# fractures displaced 5, 10, 15, 20, 25 and 30 mm (each sacral fracture
# hinged 3 degrees and slid up or back, both at once, the iliac wing opened
# 2 mm, turned 3 degrees and slid laterally or forward), and the impacted
# sacral fractures; each unilateral one from the exact start and a mirror
# start 5 mm and 3 degrees off. A region's displacement is how far the fit
# moved its units, relative to what they are joined to, at it or at any
# other region (RegionFit.displacement_mm). PHANTOM_BOUND_MEASURED_MM is, at
# each displacement of PHANTOM_DISPLACEMENTS_MM, the worst landing of a
# region whose displacement lies between the displacements either side of it.
# PHANTOM_BOUND_TABLE_MM is that rounded up to half a millimetre and never
# smaller than at a smaller displacement. Between two displacements the bound
# is interpolated, so it is never lower than any landing measured between
# them: both displacements' windows hold that landing.
# - Fracture: the worst is the sacral split's own error, which grows with the
#   slide. Where the faces touch, the plane carries the cut across bone with
#   no gap in it, and voxels within half a voxel of the fracture go to the
#   wrong piece and stay as far from home as the slide: 6.24 mm at a 6 mm
#   slide, 10.86 at 10, 15.37 at 15, 25.13-25.67 at 25 (slid back or up).
#   The fit itself lands far closer (the same fractures slid up, 1.2-2.3 mm).
#   So past about 10 mm a fracture's bound is about its displacement.
# - Symphysis: 12.22 mm at 10.5 mm, the bilateral phantom slid 10 mm, where
#   the fit stops short with nothing to start from; at most 4.87 mm on every
#   unilateral fit to 27 mm. At 0-5 mm it keeps the 6.26 mm an earlier fit
#   measured on the half-crushed rim (slice 1b kept it; the present fit reads
#   no number there), so it is not lowered.
# - SI joint: never measured where it is what pins a hip (its regions here
#   have both sides on one unit and land 0), so it takes the largest of the
#   others at each displacement.
# Measured on the same phantoms the round-trip tests check, not on held-out
# ones, at one voxel size; the smallest displacement run is 3.9 mm, so the
# bound at 0 is the one measured between 0 and 5 mm.
PHANTOM_DISPLACEMENTS_MM = (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0)
PHANTOM_BOUND_MEASURED_MM = {"fracture": (1.86, 6.24, 10.86, 15.37, 25.13, 25.67, 25.67),
                             "symphysis": (6.26, 6.26, 12.22, 12.22, 4.87, 3.82, 3.02),
                             "si": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)}
PHANTOM_BOUND_TABLE_MM = {"fracture": (2.0, 6.5, 11.0, 15.5, 25.5, 26.0, 26.0),
                          "symphysis": (6.5, 6.5, 12.5, 12.5, 12.5, 12.5, 12.5),
                          "si": (6.5, 6.5, 12.5, 15.5, 25.5, 26.0, 26.0)}
# The furthest displacement at which a region reported a number on that
# family, rounded up to half a millimetre: the bound says nothing past it. The
# phantoms were displaced to 30 mm (7d.2), but at 30 mm no region reported a
# number: the sacral fracture slid 30 mm up was left unresisted along it, slid
# back it moved its unit further than 30 mm, the iliac wing slid 30 mm
# laterally left no fracture surface, and the bilateral fit's rims disagreed.
# The furthest that reported one were the iliac wing slid 25 mm (fracture
# 27.69 mm) and the sacral fracture slid 25 mm back (symphysis 26.76 mm). The
# SI joint takes the largest. A region the fit moves further is
# unconstrained, and so is every region of a unit that is (its pose is
# outside the family).
PHANTOM_TRAVEL_MM = {"fracture": 28.0, "symphysis": 27.0, "si": 28.0}

# DECISIONS, the table under section 1: the median maximum travel of a
# normal hemipelvis onto its mirror, relative to the sacrum (which cancels
# any rigid error of the plane), at the SI joint, at the symphysis, and over
# the whole hemipelvis (taken for a fracture, which is not in the table, and
# for a whole unit whose pose rests on the mirror).
MIRROR_FLOOR_MM = {"si": 4.7, "symphysis": 9.6, "fracture": 11.8, "unit": 11.8}
# An impacted fracture's rims are paired across its dense band (7d.6): reduced,
# its two faces lie about twice the band's depth apart (each fragment's bone
# in the overlap goes back to its own side), so the reach grows by that.
IMPACTED_REACH_PER_DEPTH = 2.0
# Along an impacted fracture, a rim point and its partner give a sliding row
# only where their outer cortex faces within 60 degrees of the same way
# (_pairs). Chosen, not calibrated.
IMPACTED_SLIDE_COS = 0.5

SOURCE = "displacement engine congruence fit"
NOT_ACCEPTED = ("NOT ACCEPTED: this reduction is proposed automatically; nothing may be planned on it until the "
                "surgeon has accepted this case on the before/after sheet (DECISIONS 7c.8)")
REGION_POINTS_FALLBACK = 200  # surface points that say where a region is when it has no pairs
# A region over a whole unit (one no surface pins) is its voxels, one per
# cell of this side, so that every voxel of the unit lies within half of
# Corridor Finder's warning radius of one: a screw anywhere in that bone, or
# up to the other half of the radius outside it, is warned. A sparse sample
# of the unit's surface would leave thick bone between its points further
# than the radius from every one of them.
UNIT_COVER_CELL_MM = REGION_RADIUS_MM / (2.0 * np.sqrt(3.0))
# A marked fracture's region is a grid on its plane this far apart: a point
# of the plane is at most step / sqrt(2) from the grid, well inside
# REGION_RADIUS_MM, so a screw crossing the marked fracture anywhere near an
# unmatched mark is within the warning radius of a region point.
MARK_COVER_STEP_MM = REGION_RADIUS_MM / 2.0
STATIC = -1


def phantom_bound_mm(kind: str, displacement_mm: float) -> float:
    """The error measured on phantoms for a region of this kind displaced
    this far (PHANTOM_BOUND_TABLE_MM, interpolated); inf past
    PHANTOM_TRAVEL_MM, where nothing was measured."""
    if kind not in PHANTOM_BOUND_TABLE_MM:
        raise ValueError(f"no phantom bound for a region of kind {kind!r}")
    if not np.isfinite(displacement_mm) or displacement_mm > PHANTOM_TRAVEL_MM[kind]:
        return float("inf")
    return float(np.interp(max(float(displacement_mm), 0.0), PHANTOM_DISPLACEMENTS_MM, PHANTOM_BOUND_TABLE_MM[kind]))


# --------------------------------------------------------------------------
# The symphyseal gap, measured as its target was (DECISIONS 7c.7).


def symphysis_levels(labels_vol: Volume) -> np.ndarray:
    """The symphyseal gap per axial level, mm: the median, over the level's
    joint voxels, of the distance to one hip bone plus the distance to the
    other (si_joint's gap field, centre to centre). A joint voxel is empty,
    with the nearest right hip and the nearest left hip on opposite sides of
    it (si_joint.facing), each within SYMPHYSIS_REACH_MM. Only the symphysis
    has the two hip bones that close. Empty with no symphysis found."""
    labels = labels_vol.array
    right, left = labels == seg.HIP_R, labels == seg.HIP_L
    pr, pl = surface_points(labels_vol, right), surface_points(labels_vol, left)
    if len(pr) == 0 or len(pl) == 0:
        return np.zeros(0)
    # Only where the two hips come within two reaches of each other: the
    # distance transforms are the expensive part.
    near_r = pr[cKDTree(pl).query(pr)[0] <= 2.0 * SYMPHYSIS_REACH_MM]
    near_l = pl[cKDTree(pr).query(pl)[0] <= 2.0 * SYMPHYSIS_REACH_MM]
    if len(near_r) == 0 or len(near_l) == 0:
        return np.zeros(0)
    sx, sy, sz = labels_vol.spacing
    sampling = np.array([sz, sy, sx])
    corners = labels_vol.world_to_zyx_indices(np.vstack([near_r, near_l])).T
    pad = np.ceil(SYMPHYSIS_REACH_MM / sampling).astype(int) + 2
    lo = np.maximum(np.floor(corners.min(axis=0)).astype(int) - pad, 0)
    hi = np.minimum(np.ceil(corners.max(axis=0)).astype(int) + pad + 1, labels.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    to_r, at_r = ndi.distance_transform_edt(~right[box], sampling=sampling, return_indices=True)
    to_l, at_l = ndi.distance_transform_edt(~left[box], sampling=sampling, return_indices=True)
    here = np.indices(to_r.shape)
    joint = (si_joint.facing((at_r - here) * sampling[:, None, None, None],
                             (at_l - here) * sampling[:, None, None, None], to_r, to_l)
             & (labels[box] == 0) & (to_r <= SYMPHYSIS_REACH_MM) & (to_l <= SYMPHYSIS_REACH_MM))
    gap = to_r + to_l
    return np.array([float(np.median(gap[k][joint[k]])) for k in range(joint.shape[0]) if joint[k].any()])


def symphysis_gap(labels_vol: Volume):
    """(median gap over levels, 90th percentile over levels, levels) in mm,
    or (nan, nan, levels) with no symphysis found on SYMPHYSIS_MIN_LEVELS
    levels. The median is the joint's typical width, which a fit closing the
    whole joint surface aims at; the 90th percentile is si_joint's coverage
    percentile."""
    levels = symphysis_levels(labels_vol)
    if len(levels) < SYMPHYSIS_MIN_LEVELS:
        return float("nan"), float("nan"), len(levels)
    return float(np.median(levels)), float(np.percentile(levels, si_joint.COVERAGE_PERCENTILE)), len(levels)


# --------------------------------------------------------------------------
# What the fit returns.


@dataclass
class Unit:
    """One moving unit: its voxels as scanned, its start and its fitted pose."""

    name: str  # "hip_right", "hip_right_fragment_1"
    side: str
    mask: np.ndarray  # bool, on the labels grid
    parts: List[str]  # what it is made of, in words
    start: np.ndarray  # 4x4, the mirror start (unilateral) or the identity (bilateral)
    transform: np.ndarray  # 4x4, scanned -> reduced, after the fit
    departure_mm: Dict[str, float] = field(default_factory=dict)  # per region, from the mirror start


@dataclass
class RegionFit:
    name: str  # "si_right", "symphysis", "fracture_<id>", "unit_<unit>_unpinned": the key in Reduction.residual_mm
    kind: str  # "si", "symphysis", "fracture", or "unit" (a whole unit nothing pins; always inf)
    units: Tuple[str, ...]  # the units it joins ("static" for bone that does not move)
    pairs: int  # pairs across it after the fit
    mismatch_p90_mm: float  # 90th percentile mismatch after the fit; nan when not measured
    bound_mm: float  # phantom_bound_mm at its displacement; nan for a whole unit, which has none
    residual_mm: float  # max(mismatch, bound, the mirror's floor where it rests on it), or inf when unconstrained
    xyz: np.ndarray  # (n, 3) world mm, its surface in the reduced anatomy
    unconstrained: str = ""  # why it is inf; "" when it is not
    notes: List[str] = field(default_factory=list)
    # Its two sides as scanned (a fracture's two faces; a joint's paired
    # points on each bone), and the unit each point lies on (an index into
    # CongruenceFit.units, -1 for bone that does not move): what a fit is
    # checked against a known reduction with.
    sides: Tuple[np.ndarray, np.ndarray] = (np.zeros((0, 3)), np.zeros((0, 3)))
    side_units: Tuple[np.ndarray, np.ndarray] = (np.zeros(0, int), np.zeros(0, int))
    travel_mm: float = float("nan")  # how far the fit moves its two sides relative to each other, at most
    # How far the fit moved its units, at it or at any other region: the
    # displacement its bound is read at (7d.2). nan for a whole unit.
    displacement_mm: float = float("nan")
    # The mirror's normal floor for it (MIRROR_FLOOR_MM) where its reduction
    # rests on the mirror (7d.6), which its residual is never below; nan
    # where it does not.
    floor_mm: float = float("nan")

    def sentence(self) -> str:
        if self.unconstrained:
            return f"{self.name}: UNCONSTRAINED ({self.unconstrained})"
        if self.kind == "unit":
            return (f"{self.name}: {self.residual_mm:.1f} mm (rests on the mirror: the mirror's normal floor over a "
                    f"whole hemipelvis)")
        return (f"{self.name}: {self.residual_mm:.1f} mm (90th-percentile mismatch {self.mismatch_p90_mm:.1f} mm, "
                f"phantom bound {self.bound_mm:.1f} mm at {self.displacement_mm:.1f} mm displaced, {self.pairs} pairs, "
                f"moved {self.travel_mm:.1f} mm"
                + (f", rests on the mirror, floor {self.floor_mm:.1f} mm" if np.isfinite(self.floor_mm) else "") + ")")


@dataclass
class CongruenceFit:
    injured: str  # "right", "left" or "both"
    units: List[Unit]
    regions: Dict[str, RegionFit]
    si_target_mm: Dict[str, float]
    symphysis_target_mm: float
    rounds: int
    notes: List[str] = field(default_factory=list)

    def flags(self) -> List[str]:
        """Everything the Reduction must carry: acceptance first, then every
        note, every unconstrained region with why, and every region's own
        notes under its name."""
        return ([NOT_ACCEPTED] + list(self.notes)
                + [f"{r.name}: unconstrained, its error is not known ({r.unconstrained})"
                   for r in self.regions.values() if r.unconstrained]
                + [f"{r.name}: {n}" for r in self.regions.values() for n in r.notes])

    def reduction(self) -> Reduction:
        """The fit as Corridor Finder uses it: one Move per unit, the error and
        surface per region, every flag in the notes, and not accepted."""
        return Reduction(moves=[Move(u.name, u.mask, u.transform) for u in self.units],
                         residual_mm={k: float(r.residual_mm) for k, r in self.regions.items()},
                         region_xyz={k: r.xyz for k, r in self.regions.items()},
                         source=SOURCE, notes=self.flags(), accepted_by=None)

    def sentence(self) -> str:
        return "; ".join(r.sentence() for r in self.regions.values())


# --------------------------------------------------------------------------
# One side of a region: points, normals, and which unit each lies on.


@dataclass
class _Side:
    points: np.ndarray  # (n, 3) world mm, as scanned
    normals: np.ndarray  # (n, 3) unit, outward
    unit: np.ndarray  # (n,) unit index, STATIC for bone that does not move
    half_layer: Optional[np.ndarray] = None  # (n,) mm, fracture faces only (see _half_layer)
    inplane: Optional[np.ndarray] = None  # (n, 3) unit outer normal along the fracture; 0 where unreliable
    # (n,) mm, an impacted fracture's rims only: how far beyond one voxel
    # layer each point lay from its partner face at the mirror start (7d.6).
    across: Optional[np.ndarray] = None

    def subset(self, keep: np.ndarray) -> "_Side":
        return _Side(self.points[keep], self.normals[keep], self.unit[keep],
                     None if self.half_layer is None else self.half_layer[keep],
                     None if self.inplane is None else self.inplane[keep],
                     None if self.across is None else self.across[keep])


@dataclass
class _Region:
    name: str
    kind: str
    a: _Side  # fracture: face A's rim; joint: the side paired from
    b: _Side  # fracture: face B's rim; joint: the side paired to
    target_mm: float = 0.0  # joints: the width the pairs are closed to
    reach_mm: float = RIM_PAIR_MAX_MM
    where: Optional[_Side] = None  # every point that says where the region is (fractures: whole faces)
    faces: Optional[Tuple[_Side, _Side]] = None  # fractures: the whole faces, as scanned
    # An impacted fracture (fracture_surface.CT_IMPACTED, 7d.6): its band's
    # depth, and the distance across it, rim to partner face, that the fit
    # closes it to: its distance at the mirror start. None: not taken (no
    # mirror, or no rim pairs there), and the reason; the fit then has no row
    # across it.
    depth_mm: Optional[float] = None
    across_mm: Optional[float] = None
    no_across: str = ""

    @property
    def impacted(self) -> bool:
        return self.depth_mm is not None


_ROW_FIELDS = ("region", "p", "p0", "q", "q0", "n", "target", "u", "v", "pair", "mirror")


@dataclass
class _Rows:
    """Point-to-plane rows: r = (p - q) . n - target, p on unit u, q on unit v."""

    region: np.ndarray
    p: np.ndarray
    p0: np.ndarray  # p as scanned
    q: np.ndarray
    q0: np.ndarray  # q as scanned
    n: np.ndarray
    target: np.ndarray
    u: np.ndarray
    v: np.ndarray
    pair: np.ndarray  # rows of one pair share an id (a rim pair has a normal and a sliding row)
    mirror: np.ndarray  # bool: a row across an impacted fracture, whose target comes from the mirror (7d.6)

    @property
    def deviation(self) -> np.ndarray:
        return np.einsum("ij,ij->i", self.p - self.q, self.n) - self.target

    def subset(self, keep: np.ndarray) -> "_Rows":
        return _Rows(*(getattr(self, k)[keep] for k in _ROW_FIELDS))


def _unit_of(voxels: np.ndarray, units: Sequence[Unit]) -> np.ndarray:
    out = np.full(len(voxels), STATIC, dtype=np.int64)
    if not len(voxels):
        return out
    idx = tuple(np.asarray(voxels, dtype=np.int64).T)
    for k, u in enumerate(units):
        out[u.mask[idx]] = k
    return out


def _half_layer(normals: np.ndarray, spacing) -> np.ndarray:
    """How far, on average, a face's voxel centres sit off the surface they
    digitise: half the thickness of one voxel layer along the normal. A
    boundary voxel's centre lies anywhere from 0 to max_i(s_i |n_i|) inside
    the surface, so two faces reduced exactly sit one layer apart."""
    return 0.5 * np.max(np.abs(normals) * np.asarray(spacing, dtype=float)[None, :], axis=1)


def _moved(side: _Side, poses: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
    p, n = side.points.copy(), side.normals.copy()
    m = None if side.inplane is None else side.inplane.copy()
    for k in np.unique(side.unit):
        if k == STATIC:
            continue
        sel = side.unit == k
        p[sel] = transform_points(poses[k], side.points[sel])
        n[sel] = side.normals[sel] @ poses[k][:3, :3].T
        if m is not None:
            m[sel] = side.inplane[sel] @ poses[k][:3, :3].T
    return p, n, m


# --------------------------------------------------------------------------
# Building the regions from the scanned anatomy.


def _fracture_region(labels_vol: Volume, s: FractureSurface, units: Sequence[Unit]) -> _Region:
    sampling = np.array(labels_vol.spacing[::-1], dtype=float)
    every = np.vstack([f.voxels for f in s.faces if len(f.voxels)])
    pad = np.array([3, 3, 3])
    lo = np.maximum(every.min(axis=0) - pad, 0)
    hi = np.minimum(every.max(axis=0) + pad + 1, labels_vol.array.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    # The outer cortex beside each rim voxel: the bone's surface away from
    # this fracture, as fracture_surface._rims defines it (not a face voxel,
    # not touching the slot; the box edge is not a surface). A face voxel's
    # own gradient is its face normal, so the cortex's direction is read at
    # the nearest outer-surface voxel instead.
    bone = labels_vol.array[box] == s.label
    outer = bone & ~ndi.binary_erosion(bone, border_value=1)
    outer[tuple((every - lo).T)] = False
    gap = s.gap_voxels
    inside = np.all((gap >= lo) & (gap < hi), axis=1) if len(gap) else np.zeros(0, dtype=bool)
    if inside.any():
        slot = np.zeros(bone.shape, dtype=bool)
        slot[tuple((gap[inside] - lo).T)] = True
        outer &= ~ndi.binary_dilation(slot, np.ones((3, 3, 3), dtype=bool))
    nearest = ndi.distance_transform_edt(~outer, sampling=sampling, return_distances=False,
                                         return_indices=True) if outer.any() else None
    normals_of = _Normals(bone, sampling)
    sides = []
    for face in s.faces:
        if nearest is not None and len(face.voxels):
            at = nearest[(slice(None),) + tuple((face.voxels - lo).T)].T
            g = normals_of(at)[:, ::-1]
        else:
            g = np.zeros((len(face.voxels), 3))
        # A rim voxel sits on the corner between the face and the cortex, so
        # its own normal leans toward the cortex: on the sacral phantom the
        # sliding direction taken against it ran 0.42 across the fracture,
        # and the rims hardly resisted a slide. The fracture's direction at a
        # rim is read off the face around it instead.
        normals = _face_normals(face.points, face.normals)
        along = g - np.einsum("ij,ij->i", g, normals)[:, None] * normals
        length = np.linalg.norm(along, axis=1)
        inplane = np.where((length >= INPLANE_MIN_SHARE)[:, None], along / np.maximum(length, 1e-9)[:, None], 0.0)
        sides.append(_Side(face.points, normals, _unit_of(face.voxels, units),
                           _half_layer(normals, labels_vol.spacing), inplane))
    a, b = sides
    where = _Side(np.vstack([a.points, b.points]), np.vstack([a.normals, b.normals]), np.concatenate([a.unit, b.unit]))
    depth = float(s.impaction_depth_mm) if s.source == CT_IMPACTED and s.impaction_depth_mm is not None else None
    reach = RIM_PAIR_MAX_MM + (IMPACTED_REACH_PER_DEPTH * depth if depth is not None else 0.0)
    return _Region(s.region, "fracture", a.subset(s.faces[0].rim), b.subset(s.faces[1].rim), reach_mm=reach,
                   where=where, faces=(a, b), depth_mm=depth)


def _split_surface(labels_vol: Volume, split: SacralSplit, mine: Sequence[FractureSurface]) -> FractureSurface:
    """A split sacral fracture as the fit uses it: the split's whole boundary
    with the central sacrum. Where the fracture gapes, its slot faces; where
    the faces still touch, the split's own contact with the central sacrum,
    the zero-width route fracture_surface takes for slice 1's fragments. The
    slot alone covers only the part that gapes: on the hinged sacral
    phantoms nothing on it faced down, so a vertical slide was barely
    resisted and the bilateral fit pivoted 2 degrees about its fractures.
    Face 0 is the lateral fragment, face 1 the central sacrum."""
    labels = labels_vol.array
    sampling = np.array(labels_vol.spacing[::-1], dtype=float)
    lateral_faces, medial_faces = [], []
    for sf in mine:
        a, b = sf.faces
        if split.mask[tuple(a.voxels.T)].mean() >= split.mask[tuple(b.voxels.T)].mean():
            lateral_faces.append(a)
            medial_faces.append(b)
        else:
            lateral_faces.append(b)
            medial_faces.append(a)
    idx = np.argwhere(split.mask)
    lo = np.maximum(idx.min(axis=0) - 3, 0)
    hi = np.minimum(idx.max(axis=0) + 4, labels.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    lateral = split.mask[box]
    central = (labels[box] == seg.SACRUM) & ~lateral
    cross = ndi.generate_binary_structure(3, 1)
    touch_l = np.argwhere(lateral & ndi.binary_dilation(central, cross))
    touch_c = np.argwhere(central & ndi.binary_dilation(lateral, cross))
    # Where the faces touch there is no empty space to measure a direction
    # into, so each side's normal is its own mask's gradient (as for slice
    # 1's fragments).
    vox_l = np.vstack([touch_l + lo] + [f.voxels for f in lateral_faces])
    vox_c = np.vstack([touch_c + lo] + [f.voxels for f in medial_faces])
    nrm_l = np.vstack([_Normals(lateral, sampling)(touch_l)[:, ::-1]] + [f.normals for f in lateral_faces])
    nrm_c = np.vstack([_Normals(central, sampling)(touch_c)[:, ::-1]] + [f.normals for f in medial_faces])
    vox_l, keep_l = np.unique(vox_l, axis=0, return_index=True)
    vox_c, keep_c = np.unique(vox_c, axis=0, return_index=True)
    nrm_l, nrm_c = nrm_l[keep_l], nrm_c[keep_c]
    # Each face is its piece's whole broken surface (fracture_surface's
    # docstring): the cut where the faces touch matches in the scanned pose
    # by construction, and so does the slot's outline, so with these alone
    # a sacral fracture slid 6 mm was fitted 5.6-9.4 mm off from the exact
    # start.
    central_body = (labels == seg.SACRUM) & ~split.mask
    (vox_l, nrm_l), (vox_c, nrm_c) = _whole_faces(labels_vol, [(vox_l, nrm_l, split.mask, central_body),
                                                               (vox_c, nrm_c, central_body, split.mask)])
    gap = np.vstack([sf.gap_voxels for sf in mine]) if mine else np.zeros((0, 3), dtype=np.int64)
    rim_l, rim_c = _rims(labels_vol, seg.SACRUM, [vox_l, vox_c], gap)
    faces = (Face(f"{split.side} lateral sacral fragment", seg.SACRUM, labels_vol.zyx_indices_to_world(vox_l), nrm_l,
                  vox_l, rim_l),
             Face("central sacrum", seg.SACRUM, labels_vol.zyx_indices_to_world(vox_c), nrm_c, vox_c, rim_c))
    voxel_mm2 = float(np.prod(sampling)) ** (2.0 / 3.0)
    return FractureSurface(mine[0].id, seg.SACRUM, "split boundary + slot", faces, 0.0,
                           0.5 * (len(vox_l) + len(vox_c)) * voxel_mm2, mine[0].mark_distance_mm, [], gap)


def _face_normals(points: np.ndarray, normals: np.ndarray) -> np.ndarray:
    """Each face point's normal averaged over the face within
    FACE_NORMAL_RADIUS_MM, so a rim point takes the fracture's direction and
    not the corner's."""
    if not len(points):
        return normals
    near = cKDTree(points).query_ball_point(points, FACE_NORMAL_RADIUS_MM)
    out = np.array([normals[i].sum(axis=0) for i in near])
    return out / np.maximum(np.linalg.norm(out, axis=1), 1e-9)[:, None]


def _bone_side(labels_vol: Volume, mask: np.ndarray, units: Sequence[Unit]) -> _Side:
    points, normals, voxels = _surface(labels_vol, mask)
    return _Side(points, normals, _unit_of(voxels, units))


# --------------------------------------------------------------------------
# Pairing and the step.


def _directions(region: _Region):
    """Fracture rims are paired both ways, each face onto the other; a joint
    from its first side onto its second."""
    if region.kind == "fracture":
        return ((region.a, region.b), (region.b, region.a))
    return ((region.a, region.b),)


def _match(region: _Region, poses: np.ndarray) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Per direction, which points pair with which under these poses: the
    nearest partner within the region's reach whose surface faces it."""
    out = []
    for src, dst in _directions(region):
        if not len(src.points) or not len(dst.points):
            out.append((np.zeros(0, int), np.zeros(0, int)))
            continue
        p, n_p, _ = _moved(src, poses)
        q, n_q, _ = _moved(dst, poses)
        dist, j = cKDTree(q).query(p, distance_upper_bound=region.reach_mm)
        ok = np.isfinite(dist)
        ok[ok] = np.einsum("ij,ij->i", n_p[ok], n_q[j[ok]]) <= SQUARE_FACING_COS
        out.append((np.flatnonzero(ok), j[ok]))
    return out


def _pairs(region: _Region, poses: np.ndarray, index: int,
           matched: Optional[List[Tuple[np.ndarray, np.ndarray]]] = None) -> _Rows:
    """The region's rows under these poses, for the pairs ``matched`` (or
    the pairs matched now)."""
    if matched is None:
        matched = _match(region, poses)
    rows = {k: [] for k in ("p", "p0", "q", "q0", "n", "target", "u", "v", "mirror")}
    pair_ids = []
    first = 0
    for (src, dst), (i, j) in zip(_directions(region), matched):
        if not len(i):
            continue
        p, _, m_p = _moved(src.subset(i), poses)
        q, n_q, m_q = _moved(dst.subset(j), poses)
        ids = first + np.arange(len(i))
        first += len(i)

        def add(sel, n, target, mirror=False):
            for k, x in zip(rows, (p[sel], src.points[i][sel], q[sel], dst.points[j][sel], n, target,
                                   src.unit[i][sel], dst.unit[j][sel], np.full(int(np.sum(sel)), mirror))):
                rows[k].append(x)
            pair_ids.append(ids[sel])

        every = np.ones(len(i), dtype=bool)
        if region.kind == "fracture":
            if not region.impacted:
                add(every, n_q, src.half_layer[i] + dst.half_layer[j])
            elif region.across_mm is not None:
                # 7d.6: across the band the bone is driven into itself, so
                # its rims do not meet; each rim point is held as far from its
                # partner face as at the mirror start (_set_off), the length
                # lost to impaction taken from the mirrored side. Along the
                # fracture the rims meet as at any fracture.
                add(every, n_q, src.half_layer[i] + dst.half_layer[j] + src.across[i], mirror=True)
            # A sliding row needs both ends on the outer cortex. A face voxel
            # that is a rim only because exposed fracture surface lies beside
            # it (and was taken for outer surface) is no outline: on the left
            # sacral phantom slid 6 mm such points 10 mm down the face paired
            # with the partner's top cortex and pulled 8-9.5 mm toward the
            # scanned pose.
            slide = (np.linalg.norm(m_q, axis=1) > 0) & (np.linalg.norm(m_p, axis=1) > 0)
            if region.impacted:
                # An impacted fracture's two faces are two cross-sections of
                # the bone, twice the band's depth apart, whose outlines need
                # not match: on the impacted phantom the medial face, driven
                # toward the sacral canal, has the canal's floor in its rim
                # and the lateral face has not, and those rim points paired
                # with the partner's outer outline 6 mm off. A sliding row
                # needs both ends on cortex facing the same way.
                slide &= np.einsum("ij,ij->i", m_p, m_q) >= IMPACTED_SLIDE_COS
            add(slide, m_q[slide], np.zeros(int(slide.sum())))
        else:
            # A joint's target is a width (7c.2, 7c.7): it says nothing about
            # where along the joint one side sits, so the joint is closed along
            # its own plane, and sliding along it is left to whatever surface
            # pins it. With each pair's own normal, the pairs at the edge of a
            # joint tilt: on the bilateral phantom the symphysis turned the two
            # hemipelves 2 degrees in opposite senses (a 7 mm shear), and on
            # the undisplaced one the SI joint's edges walked the hip 5 mm
            # along the joint.
            plane = n_q.mean(axis=0)
            add(every, np.repeat((plane / max(float(np.linalg.norm(plane)), 1e-9))[None], len(i), axis=0),
                np.full(len(i), region.target_mm))
    if not rows["p"]:
        empty3 = np.zeros((0, 3))
        return _Rows(np.zeros(0, int), empty3, empty3, empty3, empty3, empty3, np.zeros(0), np.zeros(0, int),
                     np.zeros(0, int), np.zeros(0, int), np.zeros(0, dtype=bool))
    cat = {k: np.concatenate(v) for k, v in rows.items()}
    return _Rows(np.full(len(cat["p"]), index), cat["p"], cat["p0"], cat["q"], cat["q0"], cat["n"], cat["target"],
                 cat["u"].astype(int), cat["v"].astype(int), np.concatenate(pair_ids), cat["mirror"].astype(bool))


def _concat(rows: Sequence[_Rows]) -> _Rows:
    return _Rows(*(np.concatenate([getattr(r, k) for r in rows]) for k in _ROW_FIELDS))


def _set_off(region: _Region, poses: np.ndarray) -> None:
    """An impacted fracture's rims made ready to fit (7d.6), at the mirror
    start ``poses``. Each rim point is moved along its face's normal to its
    face's level there (the mean over the whole face within
    FACE_NORMAL_RADIUS_MM), and then by half of how far the two faces lie
    apart at the mirror start beyond one voxel layer, so that the rims are
    paired as any fracture's rims, each with the partner beside it along the
    fracture: a CT surface's faces are the first bone either side of a band
    read from noisy HU, two voxel layers deep in places, and paired across the
    band as they lay, a rim point's nearest partner was the one across the
    least unevenness, not the one beside it. Each rim point is then held as
    far from its partner face as it lies at the mirror start (_Side.across):
    with one distance for the whole fracture, a band read thicker at one end
    than the other tilted the fit, which walked 3.3 mm and 1.9 degrees from
    the exact start on the impacted phantom. The whole faces, which say where
    the region is and what its error is measured on, are not moved."""
    for name, face in (("a", region.faces[0]), ("b", region.faces[1])):
        rim = getattr(region, name)
        normal = rim.normals.mean(axis=0)
        normal /= max(float(np.linalg.norm(normal)), 1e-9)
        level = face.points @ normal
        near = cKDTree(face.points).query_ball_point(rim.points, FACE_NORMAL_RADIUS_MM)
        smooth = np.array([level[i].mean() for i in near])
        off = 0.5 * region.across_mm - float(np.mean(rim.half_layer))
        moved = rim.points + (smooth - rim.points @ normal + off)[:, None] * normal
        setattr(region, name, _Side(moved, rim.normals, rim.unit, rim.half_layer, rim.inplane, np.zeros(len(moved))))
    region.reach_mm = RIM_PAIR_MAX_MM
    beyond = []
    for (src, dst), (i, j) in zip(_directions(region), _match(region, poses)):
        extra = np.full(len(src.points), np.nan)
        if len(i):
            p, _, _ = _moved(src.subset(i), poses)
            q, n_q, _ = _moved(dst.subset(j), poses)
            extra[i] = np.einsum("ij,ij->i", p - q, n_q) - src.half_layer[i] - dst.half_layer[j]
        beyond.append(extra)
    typical = float(np.nanmedian(np.concatenate(beyond))) if np.isfinite(np.concatenate(beyond)).any() else 0.0
    for name, extra in zip(("a", "b"), beyond):
        getattr(region, name).across[:] = np.where(np.isfinite(extra), extra, typical)


def _opened(region: _Region, poses: np.ndarray) -> float:
    """How far the fit moves an impacted fracture's faces apart across it:
    the median motion of face B's points relative to face A's unit, along
    face A's outward normal (toward B)."""
    a, b = region.faces
    normal = a.normals.mean(axis=0)
    normal /= max(float(np.linalg.norm(normal)), 1e-9)

    def pose(k):
        return np.eye(4) if k == STATIC else poses[k]
    relative = np.linalg.inv(pose(_commonest(a.unit))) @ pose(_commonest(b.unit))
    return float(np.median((transform_points(relative, b.points) - b.points) @ normal))


def _across(region: _Region, poses: np.ndarray) -> float:
    """The median distance across an impacted fracture under these poses:
    from each rim point to its partner face's tangent plane, both ways; nan
    with no rim pairs."""
    out = []
    for (src, dst), (i, j) in zip(_directions(region), _match(region, poses)):
        if len(i):
            p, _, _ = _moved(src.subset(i), poses)
            q, n_q, _ = _moved(dst.subset(j), poses)
            out.append(np.einsum("ij,ij->i", p - q, n_q))
    return float(np.median(np.concatenate(out))) if out else float("nan")


def _jacobian(rows: _Rows, centres: np.ndarray, radii: np.ndarray, n_units: int) -> np.ndarray:
    """d(residual) / d(parameters), each unit's parameters being a rotation
    about its own centre scaled to mm at its own radius, and a translation:
    a small motion moves a point x of unit k by (a_k / L_k) x (x - c_k) + t_k.
    The partner's normal turns with the partner, so moving both sides
    together changes nothing."""
    jac = np.zeros((len(rows.p), 6 * n_units))
    for side, sign in ((rows.u, 1.0), (rows.v, -1.0)):
        for k in range(n_units):
            sel = (side == k) & (rows.u != rows.v)
            if not sel.any():
                continue
            jac[sel, 6 * k:6 * k + 3] = sign * np.cross(rows.p[sel] - centres[k], rows.n[sel]) / radii[k]
            jac[sel, 6 * k + 3:6 * k + 6] = sign * rows.n[sel]
    return jac


def _weights(rows: _Rows, n_regions: int) -> np.ndarray:
    """Each region pulls with the same total weight, and a pair far off pulls
    as if it were HUBER_MM off."""
    w = np.zeros(len(rows.p))
    active = rows.u != rows.v
    dev = np.abs(rows.deviation)
    for r in range(n_regions):
        sel = (rows.region == r) & active
        if sel.any():
            w[sel] = 1.0 / sel.sum()
    return w * np.minimum(1.0, HUBER_MM / np.maximum(dev, 1e-9))


def _null_space(jac: np.ndarray, rows: _Rows, n_regions: int, resisted: bool) -> np.ndarray:
    """The motions no surface resists (``resisted`` False), or the rest
    (True), as orthonormal columns: eigenvectors of the fit's curvature
    under or over PIN_MIN_SLOPE squared. Read without the Huber weights: a
    motion is resisted when the surfaces resist it, however mismatched they
    are now."""
    w = np.zeros(len(rows.p))
    active = rows.u != rows.v
    for r in range(n_regions):
        sel = (rows.region == r) & active
        if sel.any():
            w[sel] = 1.0 / sel.sum()
    eigval, eigvec = np.linalg.eigh(jac.T @ (w[:, None] * jac))
    keep = eigval >= PIN_MIN_SLOPE ** 2
    return eigvec[:, keep if resisted else ~keep]


def _increment(a: np.ndarray, t: np.ndarray, centre: np.ndarray, radius: float) -> np.ndarray:
    omega = a / radius
    angle = float(np.linalg.norm(omega))
    rot = np.eye(3)
    if angle > 0:
        axis = omega / angle
        k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        rot = np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * (k @ k)
    out = np.eye(4)
    out[:3, :3] = rot
    out[:3, 3] = centre - rot @ centre + t
    return out


def _orthonormal(transform: np.ndarray) -> np.ndarray:
    """Many small steps accumulate rounding; Move refuses anything not rigid."""
    u, _, vt = np.linalg.svd(transform[:3, :3])
    out = transform.copy()
    out[:3, :3] = u @ vt
    return out


def _solve(regions: Sequence[_Region], poses: np.ndarray, centres0: np.ndarray,
           radii: np.ndarray) -> Tuple[np.ndarray, int]:
    """Every unit's pose, refined together by damped point-to-plane steps
    until no unit moves SETTLED_MM in two rounds.

    Rims are re-paired every round: that is what lets one face slide back
    over the other. A joint keeps its pairs until the fit settles, then is
    re-paired and the fit continues, at most JOINT_REPAIRS times. A joint
    is nearly flat, so a point paired to the wrong partner on it still has
    the right plane; re-paired every round, the symphysis's pairs crept
    along it and dragged the sacral phantom 12 mm off from a 3 mm start."""
    poses = poses.copy()
    n = len(poses)
    joints = {i: _match(r, poses) for i, r in enumerate(regions) if r.kind != "fracture"}
    rounds, settled, repairs = 0, 0, 0
    for rounds in range(1, MAX_ROUNDS + 1):
        rows = _concat([_pairs(r, poses, i, joints.get(i)) for i, r in enumerate(regions)])
        centres = np.stack([transform_points(poses[k], centres0[k][None])[0] for k in range(n)])
        jac = _jacobian(rows, centres, radii, n)
        w = _weights(rows, len(regions))
        hess = jac.T @ (w[:, None] * jac)
        grad = jac.T @ (w * rows.deviation)
        # A motion no surface resists is not taken: along it each unit stays
        # where it started. Damping alone only slowed it, and on the
        # undisplaced phantom small biases walked the hip 5 mm along its
        # flat SI joint and symphysis. The same test marks a region
        # unconstrained (_null_space).
        pinned = _null_space(jac, rows, len(regions), resisted=True)
        damp = DAMPING * (np.diag(hess) + float(np.max(np.diag(hess), initial=0.0))) + 1e-12
        if pinned.shape[1]:
            reduced = pinned.T @ (hess + np.diag(damp)) @ pinned
            step = -pinned @ np.linalg.solve(reduced, pinned.T @ grad)
        else:
            step = np.zeros(6 * n)
        # How far the step moves each unit at its radius, to cap it and to
        # know when the fit has settled.
        reach = max(float(np.linalg.norm(step[6 * k:6 * k + 3])) + float(np.linalg.norm(step[6 * k + 3:6 * k + 6]))
                    for k in range(n))
        if reach > MAX_STEP_MM:
            step *= MAX_STEP_MM / reach
        for k in range(n):
            poses[k] = _orthonormal(_increment(step[6 * k:6 * k + 3], step[6 * k + 3:6 * k + 6], centres[k],
                                               radii[k]) @ poses[k])
        settled = settled + 1 if reach < SETTLED_MM else 0
        if settled >= 2:
            if repairs >= JOINT_REPAIRS or not joints:
                break
            joints = {i: _match(regions[i], poses) for i in joints}
            repairs += 1
            settled = 0
    return poses, rounds


# --------------------------------------------------------------------------
# The public entry point.


def fit_reduction(labels_vol: Volume, injured: str, surfaces: FractureSurfaces,
                  fragment_set: Optional[FragmentSet] = None,
                  splits: Optional[Dict[str, SacralSplit]] = None,
                  landmarks: Optional[dict] = None,
                  si_target_mm: Optional[Dict[str, float]] = None,
                  symphysis_target_mm: float = SYMPHYSIS_TARGET_GAP_MM) -> CongruenceFit:
    """Fit the reduction of the ``injured`` side ("right", "left" or
    "both") by congruence.

    ``surfaces`` are the fracture surfaces of the scanned anatomy
    (fracture_surface.find_fracture_surfaces). A unilateral injury needs
    ``fragment_set``, slice 1's result for that side, for its units and its
    mirror start; a bilateral one has neither (2.4) and starts where it lies.
    ``splits`` are the sacral splits (fracture_surface.split_sacrum); an
    unconfirmed split is used and every result says it is unconfirmed.
    ``landmarks`` (landmarks.detect_landmarks of the scanned labels; found
    here when not given) place the S1-S2 band si_joint measures in; the
    central sacrum does not move, so it serves the reduced labels too.
    ``si_target_mm`` and ``symphysis_target_mm`` replace the targets of 7c.2
    and 7c.7, which every result names."""
    if injured not in ("right", "left", "both"):
        raise ValueError(f"injured must be 'right', 'left' or 'both', got {injured!r}")
    sides = ["right", "left"] if injured == "both" else [injured]
    notes: List[str] = []
    if injured != "both":
        if fragment_set is None or fragment_set.refused or not fragment_set.fragments:
            raise ValueError("a unilateral injury starts from the mirror (DECISIONS 7c, 7a.5): pass slice 1's "
                             "fragment set for the injured side"
                             + (f" ({fragment_set.refused})" if fragment_set is not None and fragment_set.refused else ""))
        if fragment_set.side != injured:
            raise ValueError(f"the fragment set is for the {fragment_set.side} side, the injury is {injured}")
        notes.append("started from slice 1's transform home onto the mirrored intact side, which has no validated "
                     "error bound; the pose was then fitted by congruence")
    else:
        notes.append("both sides injured: no mirror (DECISIONS 2.4), so each hemipelvis started where it lies; "
                     "slice 1 finds no fragments without a mirror, so only the hip bones (and any sacral split) move")
        fragment_set = None
    labels = labels_vol.array
    units = _units(labels_vol, sides, fragment_set, splits or {}, notes)
    for i, a in enumerate(units):
        for b in units[i + 1:]:
            shared = int((a.mask & b.mask).sum())
            if shared:
                raise ValueError(f"{a.name} and {b.name} share {shared} voxels, which would be moved twice "
                                 "(two sacral splits claiming the same bone?)")
    poses = np.stack([u.start for u in units])

    if landmarks is None:
        landmarks = landmarks_mod.detect_landmarks(labels_vol)
    scanned_widths = si_joint.measure_joint_widths(labels_vol, landmarks)
    targets = _si_targets(scanned_widths, injured, si_target_mm, notes)
    notes.append(f"symphysis closed to {symphysis_target_mm:.2f} mm centre to centre"
                 + (f" (DECISIONS 7c.7: the median of the normal pelvises; their 5th-95th percentile is "
                    f"{SYMPHYSIS_TARGET_RANGE_MM[0]:.2f}-{SYMPHYSIS_TARGET_RANGE_MM[1]:.2f} mm, and how far this "
                    f"patient's own normal gap lies from the median is in no region's error)"
                    if symphysis_target_mm == SYMPHYSIS_TARGET_GAP_MM else " (given by the caller, not 7c.7's median)"))

    # The regions, from the scanned anatomy.
    # A sacral fracture a used split was cut along is fitted as the split's
    # whole boundary, under the first surface's id.
    # An impacted surface the split was cut along is fitted on its own two
    # faces, either side of its band: the split's cut runs through the band,
    # where the two fragments' bone overlaps, and fitted there it would hold
    # the impaction as scanned.
    by_split: Dict[str, List[FractureSurface]] = {}
    for side in sides:
        split = (splits or {}).get(side)
        if split is not None and not split.refused:
            by_split[side] = [sf for sf in surfaces.surfaces if sf.id in split.surface_ids and sf.source != CT_IMPACTED]
    joined = {sf.id for group in by_split.values() for sf in group}
    regions: List[_Region] = [_fracture_region(labels_vol, sf, units) for sf in surfaces.surfaces if sf.id not in joined]
    for side, group in by_split.items():
        if not group:
            continue
        regions.append(_fracture_region(labels_vol, _split_surface(labels_vol, splits[side], group), units))
        notes.append(f"fracture_{group[0].id}: fitted as the {side} split's whole boundary with the central sacrum "
                     f"({', '.join(sf.id for sf in group)} where it gapes; where it touches, the split's cut, which "
                     "the plane carries across and the surgeon confirms with the split)")
    sacrum_side = _bone_side(labels_vol, labels == seg.SACRUM, units) if (labels == seg.SACRUM).any() else None
    hip_sides = {side: _bone_side(labels_vol, labels == hip, units)
                 for side, hip in (("right", seg.HIP_R), ("left", seg.HIP_L)) if (labels == hip).any()}
    # Each joint's facing pairs are closed to its target width. si_joint's
    # width is the 90th percentile of the anterior gap over levels and
    # symphysis_gap's the median of per-level medians, neither a pair's own
    # gap, so the reduced joint is measured again the way its target was, and
    # the difference is its mismatch. (Relating the two through the intact
    # joint was tried: on CLINIC_0012 si_joint reads the intact joint 7.6 mm
    # while its pairs read about 3 mm, which asked the injured joint's pairs
    # for -0.5 mm and drove the hip into the sacrum.)
    for side in sides:
        if side in hip_sides and sacrum_side is not None:
            regions.append(_Region(f"si_{side}", "si", hip_sides[side], sacrum_side, targets[side],
                                   si_joint.AURICULAR_MAX_MM))
    if len(hip_sides) == 2:
        regions.append(_Region("symphysis", "symphysis", hip_sides["right"], hip_sides["left"], symphysis_target_mm,
                               2.0 * SYMPHYSIS_REACH_MM))

    centres0, radii = [], []
    for u in units:
        voxels = labels_vol.mask_voxel_centers_world(u.mask)
        centres0.append(voxels.mean(axis=0))
        radii.append(max(float(np.sqrt(np.mean(np.sum((voxels[::7] - centres0[-1]) ** 2, axis=1)))), 1.0))
    centres0, radii = np.stack(centres0), np.array(radii)
    n = len(units)
    # 7d.6: the length lost to an impaction comes from the mirrored side, so
    # each impacted fracture is closed to its distance across at the mirror
    # start. A bilateral injury has no mirror (2.4): nothing restores it.
    for region in regions:
        if not region.impacted:
            continue
        if injured == "both":
            region.no_across = ("both sides are injured, so there is no mirror (DECISIONS 2.4) to take the length "
                                "lost to impaction from (7d.6)")
            continue
        across = _across(region, poses)
        if np.isfinite(across):
            region.across_mm = across
            _set_off(region, poses)
        else:
            region.no_across = (f"no rim pairs across it within {region.reach_mm:.0f} mm at the mirror start, so the "
                                "length lost to impaction cannot be taken from the mirror (7d.6)")
    poses, rounds = _solve(regions, poses, centres0, radii)
    for u, pose in zip(units, poses):
        u.transform = pose

    final = [_pairs(r, poses, i) for i, r in enumerate(regions)]
    rows = _concat(final)
    centres = np.stack([transform_points(poses[k], centres0[k][None])[0] for k in range(n)])

    reduced, overlaps = apply_moves(labels_vol, [Move(u.name, u.mask, u.transform) for u in units])
    widths = si_joint.measure_joint_widths(reduced, landmarks) if any(r.kind == "si" for r in regions) else {}
    sym_levels = symphysis_levels(reduced) if any(r.kind == "symphysis" for r in regions) else np.zeros(0)
    names = [u.name for u in units]

    # Which motions no surface resists is read only off the regions that are
    # trustworthy in their own right. A region unconstrained for its own
    # reasons (too little rim, rims that disagree, not reduced, moved further
    # than the phantoms, no joint found) is not evidence of anything, so its
    # rows must not count toward pinning a unit: if they did, a unit could
    # read as pinned on surfaces already judged unreliable, and a screw in it
    # would go unwarned. Its own reasons do not depend on the null space, so
    # they are read first with no unresisted motion at all. Leaving rows out
    # can only add unresisted motions, so this can only add warnings.
    no_motion = np.zeros((6 * n, 0))
    own = [_assess(region, rr, poses, centres, radii, no_motion, names, widths, sym_levels, targets,
                   symphysis_target_mm) for region, rr in zip(regions, final)]
    trusted = [i for i, fit in enumerate(own) if not fit.unconstrained]
    trusted_rows = rows.subset(np.isin(rows.region, trusted))
    jac = _jacobian(trusted_rows, centres, radii, n)
    null = _null_space(jac, trusted_rows, len(regions), resisted=False)
    unpinned = {k: _unit_null_share(labels_vol, u, k, centres, radii, null) for k, u in enumerate(units)}
    unpinned = {k: share for k, share in unpinned.items() if share >= NULL_RELATIVE_SHARE}
    # The motions only the mirror pins: those no surface resists once the
    # rows across impacted fractures, whose distance is the mirror's, are
    # left out. A region or unit they move rests on the mirror (7d.6).
    on_mirror = trusted_rows.subset(~trusted_rows.mirror)
    mirror_null = (_null_space(_jacobian(on_mirror, centres, radii, n), on_mirror, len(regions), resisted=False)
                   if trusted_rows.mirror.any() else null[:, :0])

    out: Dict[str, RegionFit] = {}
    for i, (region, rr) in enumerate(zip(regions, final)):
        # A region unconstrained for its own reasons says so, in its own
        # words: its rows were left out of the null space, so reassessing it
        # would only blame the unresisted motion that leaving them out made.
        out[region.name] = own[i] if own[i].unconstrained else _assess(
            region, rr, poses, centres, radii, null, names, widths, sym_levels, targets, symphysis_target_mm)
    # A unit no region touches would move with no error said anywhere; one
    # that some motion no surface resists moves as a whole stays where it
    # started along that motion, a pose no surface checked. Either way its
    # error is unknown everywhere in it, not only at the regions whose own
    # two sides that motion moves apart (a turn about an axis through a
    # region barely moves that region's sides relative to each other, and
    # leaves it finite), so the whole unit is a region of its own.
    started = "slice 1's mirror start" if injured != "both" else "where it lies as scanned"
    for k, u in enumerate(units):
        if not any(u.name in r.units for r in out.values()):
            name = f"fracture_{u.name}"
            why = ("no fracture surface was found between it and its parent, so nothing pins it: its pose is "
                   f"where it started ({started})")
            out[name] = RegionFit(name, "fracture", (u.name,), 0, float("nan"), float("nan"), float("inf"),
                                  _unit_cover(labels_vol, u), why)
        elif k in unpinned:
            name = f"unit_{u.name}_unpinned"
            why = (f"not pinned down as a whole: a rigid motion no surface in the fit resists moves it "
                   f"{unpinned[k]:.2f} mm per mm, and along that motion it stays where it started ({started}), "
                   "which no surface checked; this region covers all of its bone")
            notes.append(f"{u.name} is not pinned down as a whole ({unpinned[k]:.2f} mm per mm under a motion no "
                         f"surface resists): {name} covers all of it and is unconstrained")
            out[name] = RegionFit(name, "unit", (u.name,), 0, float("nan"), float("nan"), float("inf"),
                                  _unit_cover(labels_vol, u), why)
    if mirror_null.shape[1]:
        notes += _rests_on_mirror(labels_vol, out, regions, final, units, unpinned, centres, radii, mirror_null)
    _beyond_the_family(out)
    _bound_by_displacement(out)
    out.update(_mark_regions(labels_vol, surfaces, units))
    if injured != "both":
        notes += _departures(units, regions, final)
    for name, count in overlaps.items():
        if count:
            notes.append(f"{name}: {count} voxels land on bone that does not move")
    return CongruenceFit(injured, units, out, {s: targets[s] for s in sides}, float(symphysis_target_mm), rounds,
                         list(surfaces.flags()) + notes)


def _units(labels_vol: Volume, sides: Sequence[str], fragment_set: Optional[FragmentSet],
           splits: Dict[str, SacralSplit], notes: List[str]) -> List[Unit]:
    labels = labels_vol.array
    units: List[Unit] = []
    for side in sides:
        hip_id = seg.HIP_R if side == "right" else seg.HIP_L
        femur_id = seg.FEMUR_R if side == "right" else seg.FEMUR_L
        hip = labels == hip_id
        if not hip.any():
            raise ValueError(f"there is no {side} hip bone in the labels")
        moved_fragments = [f for f in fragment_set.fragments if f.index > 0] if fragment_set is not None else []
        mask = hip.copy()
        for f in moved_fragments:
            mask &= ~f.mask
        parts = [f"{side} hip" + (" (main body)" if moved_fragments else "")]
        split = splits.get(side)
        if split is not None and not split.refused:
            mask |= split.mask & (labels == seg.SACRUM)
            parts.append(f"{side} lateral sacral fragment ({split.volume_cm3:.1f} cm3)")
            notes += [f"{side} sacral split: {n}" for n in split.notes]
            if split.confirmed:
                notes.append(f"{side} sacral split confirmed by {split.confirmed_by}")
        femur = labels == femur_id
        if femur.any():
            mask |= femur
            parts.append(f"{side} femur")
        start = fragment_set.fragments[0].to_reference if fragment_set is not None else np.eye(4)
        units.append(Unit(f"hip_{side}", side, mask, parts, np.array(start, dtype=float), np.array(start, dtype=float)))
        for f in moved_fragments:
            units.append(Unit(f"hip_{side}_fragment_{f.index}", side, f.mask & hip, [f"{side} hip fragment {f.index}"],
                              np.array(f.to_reference, dtype=float), np.array(f.to_reference, dtype=float)))
    for side, split in splits.items():
        if side not in sides and split is not None and not split.refused:
            notes.append(f"the {side} sacral split is not moved: the {side} side is not the injured one here")
    return units


def _si_targets(widths: Dict[str, si_joint.JointWidth], injured: str, given: Optional[Dict[str, float]],
                notes: List[str]) -> Dict[str, float]:
    if given is not None:
        notes.append("SI joint targets given by the caller, not 7c.2's: "
                     + ", ".join(f"{k} {v:.2f} mm" for k, v in sorted(given.items())))
        return {"right": float(given.get("right", SI_TARGET_CAP_MM)), "left": float(given.get("left", SI_TARGET_CAP_MM))}
    targets = si_joint.bridging_widths(widths, injured)
    if injured == "both":
        notes.append(f"both SI joints closed to {SI_TARGET_CAP_MM:.1f} mm (both sides injured, DECISIONS 7c.2)")
    else:
        intact = "left" if injured == "right" else "right"
        w = widths[intact]
        if np.isfinite(w.measured_mm):
            notes.append(f"{injured} SI joint closed to {targets[injured]:.2f} mm: the intact {intact} joint's anterior "
                         f"gap {w.measured_mm:.2f} mm" + (f", capped at {SI_TARGET_CAP_MM:.1f} mm"
                                                           if w.measured_mm > SI_TARGET_CAP_MM else "")
                         + " (DECISIONS 7c.2)")
        else:
            notes.append(f"the intact {intact} SI joint could not be measured ({w.warning}), so the {injured} joint "
                         f"was closed to the {SI_TARGET_CAP_MM:.1f} mm cap (DECISIONS 7c.2)")
    return targets


def _assess(region: _Region, rows: _Rows, poses, centres, radii, null, names, widths, sym_levels, targets,
            symphysis_target) -> RegionFit:
    """The region's error: its mismatch after the fit against the phantom
    bound, or why it is unconstrained."""
    n_units = len(names)
    involved = sorted({int(k) for k in np.concatenate([rows.u, rows.v])} if len(rows.p) else set())
    if region.where is not None:
        involved = sorted(set(involved) | {int(k) for k in region.where.unit})
    elif not involved and len(region.a.unit):
        # No pairs: the unit most of the paired-from side is on.
        values, counts = np.unique(region.a.unit, return_counts=True)
        involved = [int(values[np.argmax(counts)])]
    unit_names = tuple("static" if k == STATIC else names[k] for k in involved)
    pairs = int(len(np.unique(rows.pair))) if len(rows.p) else 0
    xyz = _region_xyz(region, rows, poses)
    notes: List[str] = []
    why = ""
    mismatch = float("nan")
    floor = float("nan")
    if region.kind == "fracture":
        if pairs:
            dev = rows.deviation
            per_pair = np.zeros(int(rows.pair.max()) + 1)
            np.add.at(per_pair, rows.pair, dev ** 2)
            mismatch = float(np.percentile(np.sqrt(per_pair[np.unique(rows.pair)]), 90))
        # Read off the faces, not the pairs: with too few rim pairs left (or
        # none), a fracture the fit never reduced must still say so first.
        on_units = ({int(k) for k in region.faces[0].unit} | {int(k) for k in region.faces[1].unit}
                    if region.faces is not None else set(involved))
        reduced_here = len(on_units) > 1 and not (len(rows.p) and np.all(rows.u == rows.v))
        if not reduced_here:
            on = "bone that does not move" if unit_names == ("static",) else " and ".join(unit_names)
            seen = (f"its rims' mismatch, {mismatch:.1f} mm, is paired only within {region.reach_mm:.0f} mm and does "
                    "not grow with the displacement" if pairs else "no rim pairs at all")
            why = (f"NOT REDUCED: both faces lie on {on}, so the fit leaves this fracture as scanned, and how far "
                   f"it is out of place is not measured ({seen})")
        elif region.impacted and region.across_mm is None:
            why = (f"IMPACTION NOT RESTORED: an impacted fracture ({region.depth_mm:.1f} mm dense band) and "
                   f"{region.no_across}, so the fit does not say how far across it the fragments belong")
        elif pairs < MIN_PAIRS:
            why = (f"too little rim: {pairs} rim pairs within {region.reach_mm:.0f} mm after the fit, fewer than "
                   f"{MIN_PAIRS}")
        elif mismatch > RIMS_DISAGREE_MM:
            why = (f"its rims disagree: still {mismatch:.1f} mm apart (90th percentile) after the best rigid fit, "
                   f"more than {RIMS_DISAGREE_MM:.1f} mm")
        if reduced_here and region.impacted and region.across_mm is not None:
            floor = MIRROR_FLOOR_MM["fracture"]
            notes.append(f"rests on the mirror: impacted ({region.depth_mm:.1f} mm dense band), so its rims were fitted "
                         f"along the fracture only, and across it the length lost to impaction was taken from the "
                         f"mirrored side (DECISIONS 7d.6): the fit moves its faces {_opened(region, poses):.1f} mm apart "
                         f"across the band; its error is therefore at least the mirror's normal floor, {floor:.1f} mm "
                         "(DECISIONS section 1)")
    else:
        if region.kind == "si":
            side = region.name.split("_", 1)[1]
            w = widths.get(side)
            if w is None or w.n_samples == 0:
                why = (f"si_joint finds no joint on the reduced labels ({w.warning if w is not None else 'not measured'})")
            else:
                mismatch = float(np.percentile(np.abs(w.gaps_mm - targets[side]), 90))
        else:
            if len(sym_levels) < SYMPHYSIS_MIN_LEVELS:
                why = f"no symphysis found on the reduced labels ({len(sym_levels)} levels)"
            else:
                mismatch = float(np.percentile(np.abs(sym_levels - symphysis_target), 90))
        if not why and pairs < MIN_PAIRS:
            why = (f"too little joint surface: {pairs} facing pairs within {region.reach_mm:.0f} mm after the fit, "
                   f"fewer than {MIN_PAIRS}")
    if not why and null.shape[1] and len(rows.p):
        share = _null_share(rows, centres, radii, null, n_units)
        if share >= NULL_RELATIVE_SHARE:
            moving = [names[k] for k in involved if k != STATIC]
            why = (f"a rigid motion that no surface in the fit resists moves its two sides {share:.2f} mm per mm "
                   f"relative to each other: {', '.join(moving)} can slide or turn here unopposed")
    if region.faces is not None:
        sides = (region.faces[0].points, region.faces[1].points)
        side_units = (region.faces[0].unit, region.faces[1].unit)
        partners = tuple(np.full(len(u), _commonest(other)) for u, other in zip(side_units, side_units[::-1]))
    else:
        sides, side_units = (rows.p0, rows.q0), (rows.u, rows.v)
        partners = (rows.v, rows.u)
    travel = _travel(sides, side_units, partners, poses)
    limit = PHANTOM_TRAVEL_MM[region.kind]
    if not why and travel > limit:
        why = (f"displaced further than the phantoms its error was measured on: the fit moves its two sides up to "
               f"{travel:.1f} mm relative to each other, and its bound was measured only up to {limit:.1f} mm")
    # Its own displacement for now; _bound_by_displacement reads the bound
    # again once every region's travel is known.
    bound = phantom_bound_mm(region.kind, travel)
    residual = float("inf") if why else float(np.nanmax([mismatch, bound, floor]))
    return RegionFit(region.name, region.kind, unit_names, pairs, mismatch, bound, residual, xyz, why, notes, sides,
                     side_units, travel, travel, floor)


def _beyond_the_family(regions: Dict[str, RegionFit]) -> None:
    """Every region of a unit the fit moved further, at some region, than the
    phantoms measured is outside the family its bound was measured on:
    unconstrained, naming where."""
    beyond: Dict[str, str] = {}
    for r in regions.values():
        if np.isfinite(r.travel_mm) and r.travel_mm > PHANTOM_TRAVEL_MM[r.kind]:
            for u in r.units:
                if u != "static":
                    beyond.setdefault(u, f"{r.name}, {r.travel_mm:.1f} mm against {PHANTOM_TRAVEL_MM[r.kind]:.1f} mm")
    for r in regions.values():
        hit = [f"{u} (at {beyond[u]})" for u in r.units if u in beyond]
        if not hit:
            continue
        why = ("displaced further than the phantoms its error was measured on: the fit moves "
               + "; ".join(hit) + " further than any phantom it was measured on")
        # A region already unconstrained for another reason gets this one
        # too: it is the root cause the surgeon needs to read, and the other
        # reason (an unresisted motion, say) may exist only because the
        # far-displaced region's own surfaces were rightly not trusted.
        if r.unconstrained and "further than the phantoms" not in r.unconstrained:
            r.unconstrained = f"{r.unconstrained}; and {why}"
        elif not r.unconstrained:
            r.unconstrained = why
        r.residual_mm = float("inf")


def _bound_by_displacement(regions: Dict[str, RegionFit]) -> None:
    """Each region's bound read off the measured table (7d.2) at its
    displacement: the furthest the fit moved any of its units relative to
    what that unit is joined to, at this region or at any other. A fit that
    stops short moves a region less than its unit is displaced (the sacral
    phantom slid 10 mm up from the wrong mirror start: its symphysis moved
    6.5 mm and landed 8.4 mm off, its fracture moved 10.2 mm), so the bound
    is read where the unit was found displaced, not only at the region.

    The limits differ by kind, so a unit can be within the limit of the
    region that moved it (_beyond_the_family passes it) and past the limit
    of another region on it: the bound there is inf, and the reason is said
    here, where the inf is made, never left for someone else to find."""
    unit_travel: Dict[str, Tuple[float, str]] = {}
    for r in regions.values():
        if np.isfinite(r.travel_mm):
            for u in r.units:
                if u != "static" and r.travel_mm > unit_travel.get(u, (0.0, ""))[0]:
                    unit_travel[u] = (r.travel_mm, r.name)
    for r in regions.values():
        if r.kind == "unit" or not np.isfinite(r.travel_mm):
            continue
        r.displacement_mm = max([r.travel_mm] + [unit_travel[u][0] for u in r.units if u in unit_travel])
        r.bound_mm = phantom_bound_mm(r.kind, r.displacement_mm)
        if np.isinf(r.bound_mm):
            limit = PHANTOM_TRAVEL_MM[r.kind]
            hit = [f"{u} moved {unit_travel[u][0]:.1f} mm at {unit_travel[u][1]}" for u in r.units
                   if u in unit_travel and unit_travel[u][0] > limit]
            if r.travel_mm > limit:
                hit.insert(0, f"its two sides moved {r.travel_mm:.1f} mm relative to each other")
            why = ("displaced further than the phantoms its error was measured on: " + "; ".join(hit)
                   + f", and the {r.kind} bound was measured only up to {limit:.1f} mm")
            if r.unconstrained and "further than the phantoms" not in r.unconstrained:
                r.unconstrained = f"{r.unconstrained}; and {why}"
            elif not r.unconstrained:
                r.unconstrained = why
            r.residual_mm = float("inf")
        elif not r.unconstrained:
            r.residual_mm = float(np.nanmax([r.mismatch_p90_mm, r.bound_mm, r.floor_mm]))


def _rests_on_mirror(labels_vol: Volume, regions: Dict[str, RegionFit], fitted: Sequence[_Region],
                     final: Sequence[_Rows], units: Sequence[Unit], unpinned: Dict[int, float], centres, radii,
                     mirror_null: np.ndarray) -> List[str]:
    """7d.6: where a motion only the mirror pins (mirror_null: no surface
    resists it once the rows across impacted fractures are left out) moves a
    region's two sides apart, that region rests on the mirror, and its error
    is at least the mirror's floor for its kind; where it moves a whole unit,
    the unit rests on the mirror, and a region over all its bone,
    ``unit_<name>_on_mirror``, carries the floor for a whole hemipelvis. Read
    as the unpinned test is (NULL_RELATIVE_SHARE). Without this, the mirror's
    length across an impacted fracture would pin a unit no surface pins, and
    a screw far from every region in it would read as safe."""
    n = len(units)
    impacted = ", ".join(r.name for r in fitted if r.impacted and r.across_mm is not None)
    notes = []
    for region, rows in zip(fitted, final):
        fit = regions[region.name]
        if fit.unconstrained or region.impacted or not len(rows.p):
            continue
        share = _null_share(rows, centres, radii, mirror_null, n)
        if share >= NULL_RELATIVE_SHARE:
            fit.floor_mm = MIRROR_FLOOR_MM[fit.kind]
            fit.notes.append(f"rests on the mirror: a motion that only the length taken from the mirror across "
                             f"{impacted} pins moves its two sides {share:.2f} mm per mm (DECISIONS 7d.6), so its error "
                             f"is at least the mirror's normal floor here, {fit.floor_mm:.1f} mm (DECISIONS section 1)")
    for k, u in enumerate(units):
        if k in unpinned or not any(u.name in r.units for r in regions.values()):
            continue
        share = _unit_null_share(labels_vol, u, k, centres, radii, mirror_null)
        if share < NULL_RELATIVE_SHARE:
            continue
        name = f"unit_{u.name}_on_mirror"
        floor = MIRROR_FLOOR_MM["unit"]
        regions[name] = RegionFit(name, "unit", (u.name,), 0, float("nan"), float("nan"), floor,
                                  _unit_cover(labels_vol, u), floor_mm=floor,
                                  notes=[f"rests on the mirror: a motion that only the length taken from the mirror "
                                         f"across {impacted} pins moves it {share:.2f} mm per mm, so where it lies "
                                         "along that motion is the mirror's (DECISIONS 7d.6); this region covers all "
                                         f"of its bone with the mirror's normal floor over a whole hemipelvis, "
                                         f"{floor:.1f} mm (DECISIONS section 1)"])
        notes.append(f"{u.name} rests on the mirror as a whole ({share:.2f} mm per mm under a motion only the mirror "
                     f"pins): {name} covers all of it at {floor:.1f} mm")
    return notes


def _commonest(units: np.ndarray) -> int:
    if not len(units):
        return STATIC
    values, counts = np.unique(units, return_counts=True)
    return int(values[np.argmax(counts)])


def _travel(sides, side_units, partners, poses) -> float:
    """The most any point of either side moves under the fit relative to the
    unit it is joined to across the region (0 where both are one unit)."""
    def pose(k):
        return np.eye(4) if k == STATIC else poses[k]
    worst = 0.0
    for points, units, other in zip(sides, side_units, partners):
        if not len(points):
            continue
        keys = np.stack([units, other], axis=1)
        for own, partner in np.unique(keys, axis=0):
            if own == partner:
                continue
            sel = (units == own) & (other == partner)
            relative = np.linalg.inv(pose(partner)) @ pose(own)
            worst = max(worst, float(np.max(np.linalg.norm(transform_points(relative, points[sel]) - points[sel],
                                                           axis=1))))
    return worst


def _null_share(rows: _Rows, centres, radii, null, n_units) -> float:
    """The most the unresisted motions move the region's two sides relative
    to each other, rms over its pairs, per unit of motion."""
    take = np.unique(np.linspace(0, len(rows.p) - 1, min(len(rows.p), 2000)).astype(int))
    p, u, v = rows.p[take], rows.u[take], rows.v[take]
    d = np.zeros((3 * len(p), 6 * n_units))
    for side, sign in ((u, 1.0), (v, -1.0)):
        for k in range(n_units):
            sel = np.flatnonzero((side == k) & (u != v))
            if not len(sel):
                continue
            r = (p[sel] - centres[k]) / radii[k]
            for axis in range(3):
                e = np.zeros(3)
                e[axis] = 1.0
                # d(motion)/d(a_axis) = e x r ; d(motion)/d(t_axis) = e
                d[3 * sel[:, None] + np.arange(3), 6 * k + axis] = sign * np.cross(e, r)
                d[3 * sel + axis, 6 * k + 3 + axis] = sign
    m = d @ null
    return float(np.linalg.svd(m, compute_uv=False)[0] / np.sqrt(len(p))) if m.size else 0.0


def _unit_null_share(labels_vol: Volume, unit: Unit, k: int, centres, radii, null) -> float:
    """The most the unresisted motions move this unit's own surface, rms
    over a sample of it, per unit of motion."""
    if not null.shape[1]:
        return 0.0
    pts = _surface(labels_vol, unit.mask)[0]
    pts = transform_points(unit.transform, pts[:: max(1, len(pts) // 500)])
    r = (pts - centres[k]) / radii[k]
    a, t = null[6 * k:6 * k + 3], null[6 * k + 3:6 * k + 6]
    # The motion of each point under each unresisted direction: a x r + t.
    motion = np.stack([np.cross(a[:, z], r) + t[:, z] for z in range(null.shape[1])], axis=2)
    return float(np.linalg.svd(motion.reshape(-1, motion.shape[2]), compute_uv=False)[0] / np.sqrt(len(pts)))


def _unit_cover(labels_vol: Volume, unit: Unit) -> np.ndarray:
    """Points over the whole of a unit in the reduced anatomy: one of its
    voxels in each UNIT_COVER_CELL_MM cell it occupies."""
    voxels = np.argwhere(unit.mask)
    if not len(voxels):
        return np.zeros((0, 3))
    cell = np.maximum(np.floor(UNIT_COVER_CELL_MM / np.array(labels_vol.spacing[::-1], dtype=float)), 1).astype(int)
    keys = voxels // cell
    _, first = np.unique(np.ravel_multi_index(tuple(keys.T), tuple(keys.max(axis=0) + 1)), return_index=True)
    return transform_points(unit.transform, labels_vol.zyx_indices_to_world(voxels[first]))


def _region_xyz(region: _Region, rows: _Rows, poses) -> np.ndarray:
    """Where the region is in the reduced anatomy. Never empty: Corridor
    Finder never reads a region with no place as safe, but it could not warn
    near one either."""
    if region.where is not None:
        p, _, _ = _moved(region.where, poses)
        return p
    if len(rows.p):
        return np.vstack([rows.p, rows.q])
    a, _, _ = _moved(region.a, poses)
    b, _, _ = _moved(region.b, poses)
    if not len(a) or not len(b):
        return a if len(a) else b
    d, _ = cKDTree(b).query(a)
    return a[np.argsort(d)[:REGION_POINTS_FALLBACK]]


def _plane_basis(normal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Two orthonormal directions in the plane with this normal."""
    n = np.asarray(normal, dtype=float) / np.linalg.norm(normal)
    helper = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(n, helper)
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(n, e1)


def _mark_regions(labels_vol: Volume, surfaces: FractureSurfaces, units: Sequence[Unit]) -> Dict[str, RegionFit]:
    """A region for each fracture the surgeon marked with a mark point no
    surface matches (fracture_surface.MARK_MATCH_MM, on its own bone):
    unconstrained, over the marked plane within fracture.NEAR_MARKS_MM of
    those marks (as far as Corridor Finder treats the plane as the
    fracture), each patch moved with the unit its mark's bone lies in (a
    mark in a gap takes the nearer face)."""
    out: Dict[str, RegionFit] = {}
    for k, mark in enumerate(surfaces.unmatched_marks, start=1):
        pts = mark.points
        voxel = mark.bone_voxel[mark.unmatched]
        on_bone = voxel[:, 0] >= 0
        unit = np.full(len(pts), STATIC, dtype=np.int64)
        unit[on_bone] = _unit_of(voxel[on_bone], units)
        # Cover the marked fracture itself around each unmatched mark, not
        # only the mark: Corridor Finder treats a marked plane as the fracture
        # out to NEAR_MARKS_MM from its marks, and nothing is known about it
        # anywhere there, so a screw crossing it between two marks must be
        # warned too. A grid on the plane, MARK_COVER_STEP_MM apart, puts every
        # point of that patch within REGION_RADIUS_MM of a region point.
        cover, cover_unit = [pts], [unit]
        e1, e2 = _plane_basis(mark.plane.normal)
        steps = np.arange(-NEAR_MARKS_MM, NEAR_MARKS_MM + 1e-9, MARK_COVER_STEP_MM)
        uu, vv = np.meshgrid(steps, steps)
        disc = np.hypot(uu, vv) <= NEAR_MARKS_MM
        offsets = uu[disc][:, None] * e1 + vv[disc][:, None] * e2
        for p, u in zip(pts, unit):
            on_plane = p - float(np.dot(p - mark.plane.point, mark.plane.normal)) * mark.plane.normal
            cover.append(on_plane + offsets)
            cover_unit.append(np.full(len(offsets), u, dtype=np.int64))
        pts_all, unit_all = np.vstack(cover), np.concatenate(cover_unit)
        xyz = pts_all.copy()
        for u in np.unique(unit_all):
            if u != STATIC:
                xyz[unit_all == u] = transform_points(units[u].transform, pts_all[unit_all == u])
        on = tuple(sorted({"static" if u == STATIC else units[u].name for u in unit}))
        name = f"fracture_mark_{k}"
        who = " and ".join("bone that does not move" if u == "static" else u for u in on)
        why = (f"the surgeon marked a fracture at ({', '.join(f'{c:.0f}' for c in mark.plane.point)}) mm and at "
               f"{len(pts)} of its {len(mark.unmatched)} marks no fracture surface was found on the bone the mark "
               f"lies on within {MARK_MATCH_MM:.0f} mm, so the fit knows nothing about it there: those marks lie on "
               f"{who}, carried as a whole with this fracture as scanned; this region covers the marked plane "
               f"within {NEAR_MARKS_MM:.0f} mm of them")
        out[name] = RegionFit(name, "fracture", on, 0, float("nan"), float("nan"), float("inf"),
                              xyz, why)
    return out


def _departures(units: Sequence[Unit], regions: Sequence[_Region], final: Sequence[_Rows]) -> List[str]:
    """7c.4: each unit's fitted pose against its mirror start, at each region
    it takes part in (a fracture's faces, a joint's paired points), against
    the mirror's measured floor there."""
    flags = []
    for k, u in enumerate(units):
        for region, rows in zip(regions, final):
            if region.where is not None:
                pts = region.where.points[region.where.unit == k]
            else:
                # Both sides of a joint: the symphysis is paired from the right
                # hip, so the left hip is only ever the side paired to.
                pts = np.vstack([rows.p0[rows.u == k], rows.q0[rows.v == k]])
            if not len(pts):
                continue
            moved = float(np.max(np.linalg.norm(transform_points(u.transform, pts) - transform_points(u.start, pts),
                                                axis=1)))
            u.departure_mm[region.name] = moved
            floor = MIRROR_FLOOR_MM[region.kind]
            if moved > floor:
                flags.append(f"{u.name}: the congruence pose departs from the mirror start by {moved:.1f} mm at "
                             f"{region.name}, more than the mirror's normal floor there ({floor:.1f} mm, DECISIONS "
                             f"section 1): for the surgeon's review (7c.4); the congruence pose is used")
    return flags
