"""Each sacroiliac joint in this patient: its anterior gap and its step.

DECISIONS.md section 2. Iliosacral and transiliac screws cross the SI
joint, which a bone segmentation shows as a gap; the clearance rule counts
that gap as bone up to a width (segmentation.sacroiliac_gap_fill). A fixed
2 mm was too narrow: in the sample CT the gap's median was about 4 mm, so
no sacral screw fitted. The width is therefore measured per patient.

**Where it is measured.** At the anterior bony margin of the joint, the way
it is read off a CT: the anterior edge of the sacrum's auricular surface
against the anterior edge of the ilium's, at every level through the S1-S2
band. Measuring the whole joint instead takes in the interosseous
ligament's space behind it, which is naturally wide and irregular: on four
full-pelvis CTs that read 6.9 to 10.5 mm, which is the ligament, not the
joint.

**What is measured**, between those two anterior margins, at every level:

- the **gap**, across the joint (along the local joint plane's normal): how
  far apart the two bones are;
- the **step**, along that plane: how far the ilium's anterior margin sits
  in front of or behind the sacrum's, and how far above or below it.

A hemipelvis does not displace in one plane only, so the step is kept as a
vector, reported in both directions, and both numbers are taken over the
whole band rather than off a single slice.

On a pre-reduction CT a disrupted joint is not a measurement of anything,
so the reference comes from the intact side; with both disrupted there is
nothing to measure and a fixed 4 mm is used. Which side is disrupted is the
surgeon's call (2.4), and every automatic reference is capped at 4 mm
(2.3). What drives the bridging is the anterior gap covering
COVERAGE_PERCENTILE of the band (2.2), shown with how much of the joint it
covers, for the surgeon to check against the axial CT and correct.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np
from scipy import ndimage as ndi

from . import segmentation as seg
from .volume import Volume

MAX_BRIDGE_MM = 4.0  # DECISIONS 2.3: automatic references are capped here
AURICULAR_MAX_MM = 8.0  # wider than this is the ligamentous space behind the joint
COVERAGE_PERCENTILE = 90.0  # DECISIONS 2.2: the width covering 90% of the joint
ASYMMETRY_MM = 2.0  # DECISIONS 2.4: wider than this apart pre-selects a disrupted side
BAND_PAD_MM = 5.0  # the S1-S2 band is padded this far at each end
NEAR_JOINT_MM = 12.0  # bone this close to the other bone is at the joint
CORTEX_NEAR_JOINT_MM = 8.0  # cortex this close to the joint's front end is at it
ANTERIOR_EDGE_MM = 3.0  # the front of a joint margin, as deep as this
PLANE_FIT_MM = 12.0  # the joint's own plane is fitted within this of a level
MAX_SHIFT_MM = 20.0  # how far up or down a hemipelvis is looked for
PROFILE_RELIEF_MM = 2.0  # a joint margin flatter than this cannot show a shift
DISRUPTED_CHOICES = ("none", "right", "left", "both")


@dataclass
class JointWidth:
    side: str
    measured_mm: float  # anterior gap covering COVERAGE_PERCENTILE of the band, uncapped
    n_samples: int  # levels measured through the band
    band_z_mm: Tuple[float, float]  # the S1-S2 band it was measured in
    warning: str = ""
    gaps_mm: np.ndarray = field(default_factory=lambda: np.zeros(0))  # anterior gap per level
    steps_mm: np.ndarray = field(default_factory=lambda: np.zeros(0))  # step size per level
    step_mm: float = 0.0  # the step covering COVERAGE_PERCENTILE of the band
    # Where the ilium's anterior margin sits relative to the sacrum's, along
    # the joint: + anterior / - posterior, + cephalad / - caudad, in mm.
    step_anterior_mm: float = 0.0
    step_cephalad_mm: float = 0.0
    cephalad_known: bool = True  # False when the joint margin is too straight to tell

    def covers(self, width_mm: float) -> float:
        """The share of the joint that a bridge of this width covers. What a
        narrower bridge than the joint costs is exactly this: the rest of
        the joint stays a gap, and a screw crossing there reads as a
        breach."""
        if self.gaps_mm.size == 0:
            return 0.0
        return float(np.mean(self.gaps_mm <= width_mm + 1e-9))

    def step_sentence(self) -> str:
        """The step in words, naming both directions, since a hemipelvis
        does not displace in one plane only."""
        if self.n_samples == 0:
            return ""
        parts = []
        if abs(self.step_anterior_mm) >= 0.5:
            parts.append(f"{abs(self.step_anterior_mm):.1f} mm "
                         f"{'in front of' if self.step_anterior_mm > 0 else 'behind'}")
        if self.cephalad_known and abs(self.step_cephalad_mm) >= 0.5:
            parts.append(f"{abs(self.step_cephalad_mm):.1f} mm "
                         f"{'above' if self.step_cephalad_mm > 0 else 'below'}")
        unknown = "" if self.cephalad_known else " (whether it is also up or down cannot be told from this joint)"
        if not parts:
            return ("no step" if self.cephalad_known
                    else "no step across the joint; up or down cannot be told from it")
        return "the ilium " + " and ".join(parts) + " the sacrum" + unknown

    def sentence(self, bridge_mm: Optional[float] = None) -> str:
        if self.n_samples == 0:
            return f"{self.side} SI joint: not measured ({self.warning})"
        text = f"{self.side} SI joint: anterior gap {self.measured_mm:.1f} mm, step {self.step_mm:.1f} mm"
        step = self.step_sentence()
        if step and step != "no step":
            text += f" ({step})"
        if bridge_mm is not None:
            text += f"; bridging {bridge_mm:.1f} mm covers {100 * self.covers(bridge_mm):.0f}% of it"
        return text + (f" ({self.warning})" if self.warning else "")


def measure_joint_widths(labels_vol: Volume, landmarks: Dict[str, object]) -> Dict[str, JointWidth]:
    """Measure both SI joints at the S1-S2 level. ``landmarks`` is
    landmarks.detect_landmarks' result (it needs s1_body_center and
    s2_body_center)."""
    labels = labels_vol.array
    sacrum = labels == seg.SACRUM
    band = _band_z(landmarks)
    out: Dict[str, JointWidth] = {}
    for side, hip_label in (("right", seg.HIP_R), ("left", seg.HIP_L)):
        out[side] = _measure_one(labels_vol, sacrum, labels == hip_label, side, band)
    return out


def _band_z(landmarks) -> Optional[Tuple[float, float]]:
    centres = [landmarks[name].xyz[2] for name in ("s1_body_center", "s2_body_center") if name in landmarks]
    if len(centres) < 2:
        return None
    return (min(centres) - BAND_PAD_MM, max(centres) + BAND_PAD_MM)


def _front_cortex(bone_slice: np.ndarray, near_xy, box_origin, spacing) -> Optional[np.ndarray]:
    """This bone's anterior cortex beside the joint, on one level: of the
    bone within CORTEX_NEAR_JOINT_MM of the joint's front end, the mean of
    the voxels within ANTERIOR_EDGE_MM of its most anterior one. Keeping to
    the joint's own front end matters: the ilium reaches much further
    forward a centimetre away from the joint, and taking that would read as
    a step in every intact pelvis."""
    idx = np.argwhere(bone_slice)  # (y, x) within the box
    if idx.shape[0] == 0:
        return None
    x_mm = box_origin[0] + idx[:, 1] * spacing[0]
    y_mm = box_origin[1] + idx[:, 0] * spacing[1]
    near = np.hypot(x_mm - near_xy[0], y_mm - near_xy[1]) <= CORTEX_NEAR_JOINT_MM
    if not near.any():
        return None
    idx, x_mm, y_mm = idx[near], x_mm[near], y_mm[near]
    front = y_mm >= y_mm.max() - ANTERIOR_EDGE_MM
    return np.array([float(x_mm[front].mean()), float(y_mm[front].mean())])


def _joint_normal(joint_pts: np.ndarray, centre: np.ndarray, toward_hip: float) -> np.ndarray:
    """The local joint plane's normal, pointing from the sacrum toward the
    hip. Fitted to the joint's own voxels near ``centre``; where there are
    too few, the joint is taken as sagittal, which is what it is on
    average."""
    fallback = np.array([toward_hip, 0.0, 0.0])
    if joint_pts.shape[0] < 10:
        return fallback
    near = joint_pts[np.linalg.norm(joint_pts - centre, axis=1) <= PLANE_FIT_MM]
    if near.shape[0] < 10:
        return fallback
    normal = np.linalg.svd(near - near.mean(axis=0), full_matrices=False)[2][-1]
    if normal[0] * toward_hip < 0:
        normal = -normal
    return normal / np.linalg.norm(normal)


def _cephalad_offset(z_mm: np.ndarray, sacral_y: np.ndarray, iliac_y: np.ndarray, step_mm: float):
    """How far the ilium's anterior margin sits above or below the sacrum's:
    the shift along z that makes one margin's profile match the other's.
    Comparing a level with itself cannot show this, since both points are
    taken at that same level.

    A joint whose margin runs straight up and down has no profile to match,
    and then nothing can be said about a shift along it (the second return
    value); that is a fact about the anatomy, not a measurement of zero."""
    if z_mm.size < 5 or float(np.ptp(sacral_y)) < PROFILE_RELIEF_MM:
        return 0.0, False
    residual = iliac_y - np.median(iliac_y - sacral_y)  # the step across the joint comes off first
    shifts = np.arange(-MAX_SHIFT_MM, MAX_SHIFT_MM + step_mm, step_mm)
    cost = np.array([np.mean(np.abs(np.interp(z_mm - shift, z_mm, sacral_y) - residual)) for shift in shifts])
    if float(cost.max() - cost.min()) < 0.5:  # every shift fits about as well
        return 0.0, False
    return float(shifts[int(np.argmin(cost))]), True


def _measure_one(labels_vol: Volume, sacrum: np.ndarray, hip: np.ndarray, side: str, band) -> JointWidth:
    if band is None:
        return JointWidth(side, float("nan"), 0, (float("nan"), float("nan")), "S1 and S2 body centres were not detected")
    if not sacrum.any() or not hip.any():
        return JointWidth(side, float("nan"), 0, band, "the sacrum or this hip bone is missing")

    sx, sy, sz = labels_vol.spacing
    ox, oy, oz = labels_vol.origin
    sampling = np.array([sz, sy, sx], dtype=float)
    # Work in a box around the sacrum: the joint is within a centimetre of
    # it, and the distance transforms below are the expensive part.
    pad = np.ceil((NEAR_JOINT_MM + max(labels_vol.spacing)) / sampling).astype(int) + 1
    idx = np.argwhere(sacrum)
    lo = np.maximum(idx.min(axis=0) - pad, 0)
    hi = np.minimum(idx.max(axis=0) + pad + 1, labels_vol.array.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    box_origin = (ox + lo[2] * sx, oy + lo[1] * sy, oz + lo[0] * sz)

    to_sacrum, at_sacrum = ndi.distance_transform_edt(~sacrum[box], sampling=sampling, return_indices=True)
    to_hip, at_hip = ndi.distance_transform_edt(~hip[box], sampling=sampling, return_indices=True)
    # Where the joint runs: the empty space the two bones face each other
    # across, i.e. the nearest bit of sacrum and the nearest bit of hip lie
    # on opposite sides of it. Space past the joint's rims has both of them
    # to one side, and the ligament's space behind the joint is wider than a
    # joint. This only locates the joint; the numbers come from the two
    # anterior margins below.
    here = np.indices(to_sacrum.shape)
    to_sacrum_vec = (at_sacrum - here) * sampling[:, None, None, None]
    to_hip_vec = (at_hip - here) * sampling[:, None, None, None]
    facing = (to_sacrum_vec * to_hip_vec).sum(axis=0) <= -0.5 * np.maximum(to_sacrum * to_hip, 1e-9)

    z_index = np.arange(lo[0], hi[0]) * sz + oz
    in_band = (z_index >= band[0]) & (z_index <= band[1])
    joint = (
        (labels_vol.array[box] == 0)
        & in_band[:, None, None]
        & facing
        & (to_hip <= AURICULAR_MAX_MM)
        & (to_sacrum <= AURICULAR_MAX_MM)
    )
    joint_idx = np.argwhere(joint)
    if joint_idx.shape[0] == 0:
        return JointWidth(side, float("nan"), 0, band, "no joint surface found at the S1-S2 level")
    joint_pts = np.stack([box_origin[0] + joint_idx[:, 2] * sx,
                          box_origin[1] + joint_idx[:, 1] * sy,
                          box_origin[2] + joint_idx[:, 0] * sz], axis=1)

    # Level by level through the band: the joint's own front end gives the
    # gap, and the two cortices beside it give the step.
    sacrum_box, hip_box = sacrum[box], hip[box]
    gap_field = to_hip + to_sacrum
    toward_hip = 1.0 if side == "right" else -1.0  # the hip lies lateral to the sacrum
    gaps, steps, step_vectors = [], [], []
    levels_z, sacral_y, iliac_y = [], [], []
    for k in np.flatnonzero(in_band):
        joint_here = np.argwhere(joint[k])  # (y, x)
        if joint_here.shape[0] == 0 or not (sacrum_box[k].any() and hip_box[k].any()):
            continue
        front = joint_here[np.argmax(joint_here[:, 0])]  # the joint's anterior end
        front_xy = (box_origin[0] + front[1] * sx, box_origin[1] + front[0] * sy)
        s_edge = _front_cortex(sacrum_box[k], front_xy, box_origin, (sx, sy))
        i_edge = _front_cortex(hip_box[k], front_xy, box_origin, (sx, sy))
        if s_edge is None or i_edge is None:
            continue
        z_mm = box_origin[2] + k * sz
        s_point = np.array([s_edge[0], s_edge[1], z_mm])
        i_point = np.array([i_edge[0], i_edge[1], z_mm])
        normal = _joint_normal(joint_pts, np.array([front_xy[0], front_xy[1], z_mm]), toward_hip)
        d = i_point - s_point
        along = d - float(np.dot(d, normal)) * normal
        # The very tip of the joint space measures a corner, not a width, so
        # the gap is the middle of the joint over the front of it.
        joint_y = box_origin[1] + joint_here[:, 0] * sy
        joint_x = box_origin[0] + joint_here[:, 1] * sx
        at_front = joint_here[np.hypot(joint_x - front_xy[0], joint_y - front_xy[1]) <= CORTEX_NEAR_JOINT_MM]
        gaps.append(float(np.median(gap_field[k, at_front[:, 0], at_front[:, 1]])))
        steps.append(float(np.linalg.norm(along)))
        step_vectors.append(along)
        levels_z.append(z_mm)
        sacral_y.append(s_point[1])
        iliac_y.append(i_point[1])

    if not gaps:
        return JointWidth(side, float("nan"), 0, band, "no anterior joint margin found at the S1-S2 level")

    gaps = np.asarray(gaps)
    steps = np.asarray(steps)
    vectors = np.asarray(step_vectors)
    cephalad, cephalad_known = _cephalad_offset(np.asarray(levels_z), np.asarray(sacral_y), np.asarray(iliac_y), sz)
    # Each level shows the step across the joint; the shift along it is one
    # number for the whole joint. Together they are how far out of place the
    # hemipelvis is, along the joint.
    in_level = float(np.median(steps))
    measured = float(np.percentile(gaps, COVERAGE_PERCENTILE))
    warning = f"measured {measured:.1f} mm, capped at {MAX_BRIDGE_MM:.1f} mm" if measured > MAX_BRIDGE_MM else ""
    return JointWidth(
        side,
        measured,
        int(gaps.size),
        band,
        warning,
        gaps_mm=gaps,
        steps_mm=steps,
        step_mm=float(np.hypot(in_level, cephalad)),
        step_anterior_mm=float(np.median(vectors[:, 1])),  # + anterior, - posterior
        step_cephalad_mm=float(cephalad),
        cephalad_known=bool(cephalad_known),
    )


def bridging_widths(widths: Dict[str, JointWidth], disrupted: str) -> Dict[str, float]:
    """What to count as bone in each joint (DECISIONS 2.2), capped at
    MAX_BRIDGE_MM: a disrupted joint takes the intact side's width, both
    disrupted take MAX_BRIDGE_MM, and otherwise each takes its own."""
    if disrupted not in DISRUPTED_CHOICES:
        raise ValueError(f"disrupted must be one of {DISRUPTED_CHOICES}, got {disrupted!r}")
    capped = {side: min(w.measured_mm, MAX_BRIDGE_MM) for side, w in widths.items() if np.isfinite(w.measured_mm)}
    if disrupted == "both":
        return {side: MAX_BRIDGE_MM for side in widths}
    out = {}
    for side in widths:
        other = "left" if side == "right" else "right"
        reference = capped.get(other) if disrupted == side else capped.get(side)
        # A disrupted side with no intact measurement falls back to the cap,
        # which is what "nothing to measure" means (2.2).
        out[side] = float(reference if reference is not None else MAX_BRIDGE_MM)
    return out


def looks_disrupted(widths: Dict[str, JointWidth]) -> Optional[str]:
    """The side to pre-select as disrupted: the joint that is further out of
    place, by gap or by step, when the two differ by more than ASYMMETRY_MM
    (DECISIONS 2.4). A hemipelvis can slide along the joint without the gap
    opening at all, so the step counts here as much as the gap. None if the
    two are close, or if either could not be measured."""
    measured = {side: max(w.measured_mm, w.step_mm) for side, w in widths.items() if np.isfinite(w.measured_mm)}
    if len(measured) < 2:
        return None
    wide, narrow = sorted(measured, key=measured.get, reverse=True)
    return wide if measured[wide] - measured[narrow] > ASYMMETRY_MM else None
