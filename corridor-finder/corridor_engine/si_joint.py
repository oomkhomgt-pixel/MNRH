"""How wide each sacroiliac joint is, in this patient.

DECISIONS.md section 2. Iliosacral and transiliac screws cross the SI
joint, which a bone segmentation shows as a gap; the clearance rule counts
that gap as bone up to a width (segmentation.sacroiliac_gap_fill). A fixed
2 mm was too narrow: in the sample CT the gap's median was about 4 mm, so
no sacral screw fitted. The width is therefore measured per patient.

On a pre-reduction CT a disrupted joint is not a measurement of anything,
so the reference comes from the intact side; with both disrupted there is
nothing to measure and a fixed 4 mm is used. Which side is disrupted is the
surgeon's call (2.4), and every measurement is capped at 4 mm (2.3).

What is measured, per side, is the space the hip and the sacrum face each
other across, in the band between the S1 and S2 body centres: for each
empty voxel between them, the distance from one bone to the other through
it, which is the same quantity the bridging uses. Space past the joint's
rims does not have the two bones on opposite sides of it, and space wider
than AURICULAR_MAX_MM is the interosseous ligament's, not the joint's;
neither is counted. The reported width is the one covering
COVERAGE_PERCENTILE of the rest, with how much of the joint a given bridge
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
DISRUPTED_CHOICES = ("none", "right", "left", "both")


@dataclass
class JointWidth:
    side: str
    measured_mm: float  # the width covering COVERAGE_PERCENTILE of the joint, uncapped
    n_samples: int
    band_z_mm: Tuple[float, float]  # the S1-S2 band it was measured in
    warning: str = ""
    gaps_mm: np.ndarray = field(default_factory=lambda: np.zeros(0))  # every sampled gap

    def covers(self, width_mm: float) -> float:
        """The share of the joint that a bridge of this width covers. What a
        narrower bridge than the joint costs is exactly this: the rest of
        the joint stays a gap, and a screw crossing there reads as a
        breach."""
        if self.gaps_mm.size == 0:
            return 0.0
        return float(np.mean(self.gaps_mm <= width_mm + 1e-9))

    def sentence(self, bridge_mm: Optional[float] = None) -> str:
        if self.n_samples == 0:
            return f"{self.side} SI joint: not measured ({self.warning})"
        text = f"{self.side} SI joint {self.measured_mm:.1f} mm"
        if bridge_mm is not None:
            text += f", bridging {bridge_mm:.1f} mm covers {100 * self.covers(bridge_mm):.0f}% of it"
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


def _measure_one(labels_vol: Volume, sacrum: np.ndarray, hip: np.ndarray, side: str, band) -> JointWidth:
    if band is None:
        return JointWidth(side, float("nan"), 0, (float("nan"), float("nan")), "S1 and S2 body centres were not detected")
    if not sacrum.any() or not hip.any():
        return JointWidth(side, float("nan"), 0, band, "the sacrum or this hip bone is missing")

    sx, sy, sz = labels_vol.spacing
    sampling = np.array([sz, sy, sx], dtype=float)
    # Work in a box around the sacrum: the joint is within a centimetre of
    # it, and the distance transforms below are the expensive part.
    pad = np.ceil((AURICULAR_MAX_MM + max(labels_vol.spacing)) / sampling).astype(int) + 1
    idx = np.argwhere(sacrum)
    lo = np.maximum(idx.min(axis=0) - pad, 0)
    hi = np.minimum(idx.max(axis=0) + pad + 1, labels_vol.array.shape)
    box = tuple(slice(a, b) for a, b in zip(lo, hi))

    to_sacrum, at_sacrum = ndi.distance_transform_edt(~sacrum[box], sampling=sampling, return_indices=True)
    to_hip, at_hip = ndi.distance_transform_edt(~hip[box], sampling=sampling, return_indices=True)
    # The joint is the empty space the two bones face each other across: the
    # nearest bit of sacrum and the nearest bit of hip lie on opposite sides
    # of it. Space past the joint's rims has both of them to one side, and
    # the ligament's space behind the joint is wider than a joint.
    here = np.indices(to_sacrum.shape)
    to_sacrum_vec = (at_sacrum - here) * sampling[:, None, None, None]
    to_hip_vec = (at_hip - here) * sampling[:, None, None, None]
    facing = (to_sacrum_vec * to_hip_vec).sum(axis=0) <= -0.5 * np.maximum(to_sacrum * to_hip, 1e-9)

    z_index = np.arange(lo[0], hi[0]) * sz + labels_vol.origin[2]
    in_band = (z_index >= band[0]) & (z_index <= band[1])
    gap = to_hip + to_sacrum
    joint = (
        (labels_vol.array[box] == 0)
        & in_band[:, None, None]
        & facing
        & (to_hip <= AURICULAR_MAX_MM)
        & (to_sacrum <= AURICULAR_MAX_MM)
    )
    widths = gap[joint]
    if widths.size == 0:
        return JointWidth(side, float("nan"), 0, band, "no joint surface found at the S1-S2 level")

    measured = float(np.percentile(widths, COVERAGE_PERCENTILE))
    warning = f"measured {measured:.1f} mm, capped at {MAX_BRIDGE_MM:.1f} mm" if measured > MAX_BRIDGE_MM else ""
    return JointWidth(side, measured, int(widths.size), band, warning, gaps_mm=widths)


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
    """The side to pre-select as disrupted: the wider joint, when the two
    differ by more than ASYMMETRY_MM (DECISIONS 2.4). None if they are
    close, or if either could not be measured."""
    measured = {side: w.measured_mm for side, w in widths.items() if np.isfinite(w.measured_mm)}
    if len(measured) < 2:
        return None
    wide, narrow = sorted(measured, key=measured.get, reverse=True)
    return wide if measured[wide] - measured[narrow] > ASYMMETRY_MM else None
