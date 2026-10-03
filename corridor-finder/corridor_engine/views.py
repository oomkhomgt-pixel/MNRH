"""Where to put the C-arm for THIS patient, view by view.

DECISIONS.md 7.6. A fluoroscopic view is a definition, not an angle: an
inlet is the beam that projects the pelvic brim as a ring, an iliac oblique
is the one that shows that iliac wing face-on. The textbook numbers (45
degrees of rotation, 40-45 of tilt) are the average of those definitions
over many pelvises, and a given patient is not the average: pelvic tilt,
sacral slope and the flare of the wings all differ. So each view here is
computed from this patient's own bones, and the textbook angle is kept
beside it so the difference can be seen.

Every view is returned as the beam direction (unit vector, RAS, running the
way the x-rays travel) and the C-arm angles that produce it in drr.py's
convention, which is the same pair guidance.down_the_barrel_view returns.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
from scipy import ndimage as ndi

from . import segmentation as seg
from .volume import Volume

# A wing, a ring or a sacral face is fitted from bone within these bounds.
WING_ABOVE_BRIM_MM = 10.0  # iliac wing: bone this far above the brim and up
SACRAL_FACE_MM = 6.0  # how deep the sacrum's front face is taken
OBLIQUE_ROTATION_DEG = 45.0  # the Judet rotation, taken about the patient's own axis
MIN_FIT_POINTS = 50
# The obturator oblique (Judet) is a roll about the patient's long axis, no
# tilt, to where that side's obturator foramen shows most open. It is found
# the way a radiographer finds it: rolling the beam either side of the
# classic 45 degrees and keeping the roll at which the hole in that hip
# bone's projection is largest. Tilt is left out on purpose: letting it
# vary, the foramen opened most at about 26 degrees of outlet tilt on all
# four CLINIC pelves, which is an outlet-obturator, not a Judet view, and
# would put the outlet into the composed outlet-obturator twice.
FORAMEN_SEARCH_ROLL_DEG = 30.0  # either side of the classic rotation
FORAMEN_COARSE_STEP_DEG = 5.0
FORAMEN_FINE_STEP_DEG = 1.0
FORAMEN_PIXEL_MM = 1.0
FORAMEN_MIN_AREA_MM2 = 300.0  # a smaller hole is not the foramen


@dataclass
class View:
    name: str
    beam: np.ndarray  # unit vector, the way the x-rays travel (RAS)
    rotate_x_deg: float
    rotate_z_deg: float
    definition: str  # what the view is, in words
    textbook_x_deg: Optional[float] = None
    textbook_z_deg: Optional[float] = None

    @property
    def off_textbook_deg(self) -> Optional[float]:
        """How far this patient's view is from the textbook angles, as one
        angle between the two beams."""
        if self.textbook_x_deg is None or self.textbook_z_deg is None:
            return None
        textbook = beam_from_angles(self.textbook_x_deg, self.textbook_z_deg)
        return float(np.degrees(np.arccos(np.clip(float(np.dot(self.beam, textbook)), -1.0, 1.0))))

    def sentence(self) -> str:
        text = (f"{self.name.replace('_', ' ')}: {self.definition}; "
                f"{_tilt_words(self.rotate_x_deg)}, {_roll_words(self.rotate_z_deg)}")
        off = self.off_textbook_deg
        if off is not None:
            text += f" ({off:.0f} degrees off the textbook angles)"
        return text


def angles_from_beam(beam) -> tuple:
    """The (rotate_x, rotate_z) that make drr.py project along ``beam``.
    Same inversion as guidance.down_the_barrel_view, kept here so a view can
    be computed without a screw."""
    d = _unit(beam)
    rotate_x = float(np.degrees(np.arcsin(np.clip(d[2], -1.0, 1.0))))
    horizontal = float(np.hypot(d[0], d[1]))
    rotate_z = float(np.degrees(np.arctan2(-d[0], -d[1]))) if horizontal > 0.0 else 0.0
    return rotate_x, rotate_z


def beam_from_angles(rotate_x_deg: float, rotate_z_deg: float) -> np.ndarray:
    """The beam those angles give (drr.py's convention)."""
    rx, rz = np.radians(rotate_x_deg), np.radians(rotate_z_deg)
    return np.array([-np.sin(rz) * np.cos(rx), -np.cos(rz) * np.cos(rx), np.sin(rx)])


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def _tilt_words(rotate_x_deg: float) -> str:
    if abs(rotate_x_deg) < 3.0:
        return "no tilt"
    return f"{abs(rotate_x_deg):.0f} degrees of {'outlet (cephalad)' if rotate_x_deg > 0 else 'inlet (caudad)'} tilt"


def _roll_words(rotate_z_deg: float) -> str:
    if abs(rotate_z_deg) < 3.0:
        return "square to the patient"
    side = "the patient's right" if rotate_z_deg > 0 else "the patient's left"
    return f"{abs(rotate_z_deg):.0f} degrees rolled toward {side}"


def _plane_normal(points: np.ndarray) -> Optional[np.ndarray]:
    """The normal of the plane that best fits these points."""
    points = np.asarray(points, dtype=float)
    if points.shape[0] < 3:
        return None
    return _unit(np.linalg.svd(points - points.mean(axis=0), full_matrices=False)[2][-1])


def _orient(normal: np.ndarray, toward) -> np.ndarray:
    """Point a plane's normal the way the beam travels."""
    return normal if float(np.dot(normal, toward)) >= 0 else -normal


def _view(name: str, beam, definition: str, textbook: Optional[tuple] = None) -> View:
    beam = _unit(beam)
    rotate_x, rotate_z = angles_from_beam(beam)
    return View(name=name, beam=beam, rotate_x_deg=rotate_x, rotate_z_deg=rotate_z, definition=definition,
                textbook_x_deg=None if textbook is None else float(textbook[0]),
                textbook_z_deg=None if textbook is None else float(textbook[1]))


def _rotate_about(vector, axis, degrees: float) -> np.ndarray:
    """``vector`` turned about ``axis`` by ``degrees`` (Rodrigues)."""
    v, k = _unit(vector), _unit(axis)
    a = np.radians(degrees)
    return _unit(v * np.cos(a) + np.cross(k, v) * np.sin(a) + k * float(np.dot(k, v)) * (1.0 - np.cos(a)))


def _sacral_face(labels_vol: Volume, landmarks: Dict[str, object]):
    """The sacrum's anterior face between the S1 and S2 bodies: the front
    few millimetres of bone at each level of that band."""
    s1, s2 = landmarks.get("s1_body_center"), landmarks.get("s2_body_center")
    if s1 is None or s2 is None:
        return None
    lo, hi = sorted((float(s1.xyz[2]), float(s2.xyz[2])))
    pts = labels_vol.mask_voxel_centers_world(labels_vol.array == seg.SACRUM)
    band = pts[(pts[:, 2] >= lo) & (pts[:, 2] <= hi)]
    if band.shape[0] == 0:
        return None
    face = []
    for z in np.unique(band[:, 2]):
        level = band[band[:, 2] == z]
        face.append(level[level[:, 1] >= level[:, 1].max() - SACRAL_FACE_MM])
    return np.concatenate(face) if face else None


def _visible_foramen_mm2(hip: np.ndarray, bone: np.ndarray, beam: np.ndarray, centre: np.ndarray) -> float:
    """How much of the obturator foramen an image along ``beam`` shows: the
    hole in the hip bone's own projection nearest ``centre`` (its ring is
    that bone), less whatever other bone in the CT lies across it."""
    u = _unit(np.cross(beam, [0.0, 0.0, 1.0]) if abs(beam[2]) < 0.95 else np.cross(beam, [1.0, 0.0, 0.0]))
    v = np.cross(beam, u)
    half = int(np.ceil(FORAMEN_FIELD_MM / FORAMEN_PIXEL_MM))
    size = 2 * half + 1

    def project(points: np.ndarray) -> np.ndarray:
        rel = points - centre
        i = np.floor(rel @ u / FORAMEN_PIXEL_MM).astype(int) + half
        j = np.floor(rel @ v / FORAMEN_PIXEL_MM).astype(int) + half
        ok = (i >= 0) & (i < size) & (j >= 0) & (j < size)
        image = np.zeros((size, size), dtype=bool)
        image[i[ok], j[ok]] = True
        # Close the gaps between projected voxel centres, so the grid does
        # not make holes of its own.
        return ndi.binary_closing(image, iterations=max(1, int(np.ceil(BONE_GRID_MM / FORAMEN_PIXEL_MM))))

    ring = project(hip)
    holes = ndi.binary_fill_holes(ring) & ~ring
    pieces, n = ndi.label(holes)
    if n == 0:
        return 0.0
    k = pieces[half, half]
    if k == 0:  # the centre is on bone: take the largest hole instead
        k = int(np.argmax(np.bincount(pieces.ravel())[1:])) + 1
    foramen = pieces == k
    covered = project(bone) if bone is not None and len(bone) else np.zeros_like(foramen)
    return float((foramen & ~covered).sum()) * FORAMEN_PIXEL_MM ** 2


# What a C-arm image shows is all the bone along each ray: on CLINIC_0023
# the roll that opened the hip bone's own hole most put the femoral shaft
# across it. So the foramen is found from the hip bone, and what counts is
# the part of it no other bone (CT voxels above BONE_HU) covers.
BONE_HU = 150.0
BONE_GRID_MM = 2.0
FORAMEN_FIELD_MM = 60.0  # half-width of the image looked at, around the foramen
FORAMEN_BONE_REACH_MM = 200.0  # bone farther than this from the foramen is left out (speed)


def bone_points(hu_vol: Volume, centre, reach_mm: float = FORAMEN_BONE_REACH_MM) -> np.ndarray:
    """World points of CT bone (above BONE_HU) within ``reach_mm`` of
    ``centre``, on a grid of about BONE_GRID_MM."""
    centre = np.asarray(centre, dtype=float)
    stride = np.maximum(1, np.round(BONE_GRID_MM / np.array([hu_vol.spacing[2], hu_vol.spacing[1], hu_vol.spacing[0]])).astype(int))
    corners = np.array([hu_vol.world_to_zyx_index(centre - reach_mm), hu_vol.world_to_zyx_index(centre + reach_mm)])
    lo = np.maximum(np.floor(corners.min(axis=0)).astype(int), 0)
    hi = np.minimum(np.ceil(corners.max(axis=0)).astype(int) + 1, hu_vol.array.shape)
    sub = hu_vol.array[lo[0]:hi[0]:stride[0], lo[1]:hi[1]:stride[1], lo[2]:hi[2]:stride[2]]
    return hu_vol.zyx_indices_to_world(np.argwhere(sub > BONE_HU) * stride + lo)


def obturator_beam(labels_vol: Volume, hip_label: int, pubic_tubercle, ischial_tuberosity,
                   classic: np.ndarray, cephalad: np.ndarray, hu_vol: Optional[Volume] = None):
    """The roll, near the classic obturator oblique, at which this side's
    obturator foramen shows most (open, and not covered by other bone), and
    that visible area (mm2); None when no hole of foramen size shows, or
    the best roll is at the edge of the search. Without the CT, the other
    labelled bones stand in for what covers it."""
    a, b = np.asarray(pubic_tubercle, dtype=float), np.asarray(ischial_tuberosity, dtype=float)
    centre = 0.5 * (a + b)
    pad = FORAMEN_FIELD_MM
    corners = np.array([labels_vol.world_to_zyx_index(centre - pad), labels_vol.world_to_zyx_index(centre + pad)])
    lo = np.maximum(np.floor(corners.min(axis=0)).astype(int), 0)
    hi = np.minimum(np.ceil(corners.max(axis=0)).astype(int) + 1, labels_vol.array.shape)
    if (hi - lo < 3).any():
        return None
    box = labels_vol.array[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
    idx = np.argwhere(box == hip_label)
    if len(idx) < MIN_FIT_POINTS:
        return None
    hip = labels_vol.zyx_indices_to_world(idx + lo)
    if hu_vol is not None:
        bone = bone_points(hu_vol, centre)
    else:
        others = np.argwhere(labels_vol.array != 0)
        others = others[labels_vol.array[others[:, 0], others[:, 1], others[:, 2]] != hip_label]
        bone = labels_vol.zyx_indices_to_world(others)

    def beam_at(roll: float) -> np.ndarray:
        return _rotate_about(classic, cephalad, roll)

    best = (0.0, 0.0)
    for step, half_roll, around in ((FORAMEN_COARSE_STEP_DEG, FORAMEN_SEARCH_ROLL_DEG, 0.0),
                                    (FORAMEN_FINE_STEP_DEG, FORAMEN_COARSE_STEP_DEG, None)):
        r0 = around if around is not None else best[1]
        for roll in np.arange(r0 - half_roll, r0 + half_roll + 1e-6, step):
            area = _visible_foramen_mm2(hip, bone, beam_at(roll), centre)
            if area > best[0]:
                best = (area, float(roll))
    if best[0] < FORAMEN_MIN_AREA_MM2:
        return None
    # A best roll at the edge of the search is not a peak: the foramen was
    # not seen opening and closing again, so the classic view is the
    # honest answer.
    if abs(best[1]) > FORAMEN_SEARCH_ROLL_DEG - FORAMEN_COARSE_STEP_DEG:
        return None
    return beam_at(best[1]), best[0]


def patient_views(labels_vol: Volume, landmarks: Dict[str, object], frame=None,
                  textbook: Optional[Dict[str, dict]] = None, hu_vol: Optional[Volume] = None) -> Dict[str, View]:
    """Every named view, computed from this patient. Views whose anatomy is
    missing are left out, and the caller falls back to the textbook angles
    for those."""
    textbook = textbook or {}
    out: Dict[str, View] = {}

    def mark(name: str) -> Optional[np.ndarray]:
        lm = landmarks.get(name)
        return None if lm is None else np.asarray(lm.xyz, dtype=float)

    def book(name: str) -> Optional[tuple]:
        """The textbook angles for this view, however the caller holds them
        (drr.load_views gives pairs, corridors.json holds dicts)."""
        spec = textbook.get(name)
        if spec is None:
            return None
        if isinstance(spec, dict):
            return float(spec.get("rotate_x", 0.0)), float(spec.get("rotate_z", 0.0))
        return float(spec[0]), float(spec[1])

    posterior = -frame.y_hat if frame is not None else np.array([0.0, -1.0, 0.0])
    left_right = frame.x_hat if frame is not None else np.array([1.0, 0.0, 0.0])
    cephalad = frame.z_hat if frame is not None else np.array([0.0, 0.0, 1.0])

    # AP: square to the front of the pelvis, i.e. along the anterior pelvic
    # plane's own normal, so this patient's tilt is taken out of it.
    out["ap"] = _view("ap", posterior,
                      "square to the front of the pelvis (the anterior pelvic plane)", book("ap"))

    # Inlet: the beam perpendicular to the plane of the pelvic brim, which
    # is what makes the brim project as a ring and the front of S1 land on
    # S2. The ring is taken from the two pubic tubercles, the two brim
    # points and the sacral promontory.
    ring = [mark(n) for n in ("pubic_tubercle_right", "pubic_tubercle_left",
                              "pelvic_brim_right", "pelvic_brim_left", "sacral_promontory")]
    ring = [p for p in ring if p is not None]
    inlet_normal = _plane_normal(np.asarray(ring)) if len(ring) >= 4 else None
    if inlet_normal is not None:
        inlet_beam = _orient(inlet_normal, posterior - cephalad)
        out["inlet"] = _view("inlet", inlet_beam,
                             "perpendicular to this patient's pelvic brim, so the brim is a ring and the "
                             "front of S1 lands on S2", book("inlet"))
    # Outlet: the front of the sacrum face-on, which is what opens both
    # sacral foramina and brings the symphysis to the S2 foramen. Taken from
    # the sacrum's own anterior face between the S1 and S2 bodies, so the
    # patient's sacral slope sets it rather than a fixed tilt.
    face = _sacral_face(labels_vol, landmarks)
    outlet_normal = _plane_normal(face) if face is not None and face.shape[0] >= MIN_FIT_POINTS else None
    if outlet_normal is not None:
        out["outlet"] = _view("outlet", _orient(-outlet_normal, posterior + cephalad),
                              "square to the front of this patient's sacrum, which opens both sacral "
                              "foramina and brings the symphysis to the S2 foramen", book("outlet"))

    # Iliac oblique: that iliac wing face-on, so the beam runs along the
    # wing's own plane normal. The wing is the bone above the brim.
    for side, hip_label, sign in (("right", seg.HIP_R, 1.0), ("left", seg.HIP_L, -1.0)):
        brim = mark(f"pelvic_brim_{side}")
        if brim is None:
            continue
        pts = labels_vol.mask_voxel_centers_world(labels_vol.array == hip_label)
        wing = pts[pts[:, 2] >= brim[2] + WING_ABOVE_BRIM_MM]
        normal = _plane_normal(wing) if wing.shape[0] >= MIN_FIT_POINTS else None
        if normal is not None:
            # The wing of one side is opened by a beam entering from the
            # other, and the frame's x_hat points to the patient's left.
            beam = _orient(normal, posterior - sign * left_right)
            out[f"iliac_oblique_{side}"] = _view(
                f"iliac_oblique_{side}", beam,
                f"square to this patient's {side} iliac wing, which opens the posterior column and the "
                f"anterior wall", book(f"iliac_oblique_{side}"))

        # Obturator oblique: the roll about this patient's own upright axis,
        # within 30 degrees of the classic 45, that shows his obturator
        # foramen most open. Where no hole of foramen size shows, the
        # classic view is used and says so.
        classic = _rotate_about(posterior, cephalad, -sign * OBLIQUE_ROTATION_DEG)
        beam, definition = classic, (
            f"{OBLIQUE_ROTATION_DEG:.0f} degrees around this patient's own upright axis (his obturator foramen "
            f"could not be measured), which opens the {side} obturator ring, the anterior column and the "
            f"posterior wall")
        tubercle, tuberosity = mark(f"pubic_tubercle_{side}"), mark(f"ischial_tuberosity_{side}")
        found = (obturator_beam(labels_vol, hip_label, tubercle, tuberosity, classic, cephalad, hu_vol)
                 if tubercle is not None and tuberosity is not None else None)
        if found is not None:
            beam, area = found
            definition = (f"rolled about this patient's own upright axis to where most of his {side} obturator foramen shows "
                          f"open "
                          f"({area:.0f} mm2), which opens the {side} obturator ring, the anterior column and the "
                          f"posterior wall")
        out[f"obturator_oblique_{side}"] = _view(
            f"obturator_oblique_{side}", beam, definition, book(f"obturator_oblique_{side}"))

    # Lateral of the sacrum: along the line joining the two sacroiliac
    # joints, which is what superimposes the two sides.
    si_right, si_left = mark("si_joint_center_right"), mark("si_joint_center_left")
    if si_right is not None and si_left is not None:
        beam = _orient(si_left - si_right, left_right)
        out["lateral_sacral"] = _view("lateral_sacral", beam,
                                      "along the line between this patient's two sacroiliac joints, so the "
                                      "two sides superimpose and the alar slope (the iliac cortical density) "
                                      "shows", book("lateral_sacral"))
    out["lateral"] = _view("lateral", left_right,
                           "across the patient, square to the anterior pelvic plane", book("lateral"))

    # Combined views, built on this patient's own inlet, outlet and
    # obliques rather than on fixed numbers.
    for side in ("right", "left"):
        obturator = out.get(f"obturator_oblique_{side}")
        if obturator is None:
            continue
        if "outlet" in out:
            out[f"outlet_obturator_oblique_{side}"] = _view(
                f"outlet_obturator_oblique_{side}", _unit(obturator.beam + out["outlet"].beam),
                f"this patient's outlet and {side} obturator oblique together, which is the anterior column "
                f"corridor seen down its length")
        if "inlet" in out:
            # Sikarinkul et al.: the posterior column triangle in one view,
            # a tenth of the way to the obturator oblique with a quarter of
            # the inlet tilt.
            ap_beam = out["ap"].beam
            toward_obturator = _unit(obturator.beam - ap_beam)
            toward_inlet = _unit(out["inlet"].beam - ap_beam)
            beam = _unit(ap_beam + np.tan(np.radians(10.0)) * toward_obturator
                         + np.tan(np.radians(25.0)) * toward_inlet)
            out[f"posterior_column_triangle_{side}"] = _view(
                f"posterior_column_triangle_{side}", beam,
                f"10 degrees toward this patient's {side} obturator oblique with 25 degrees of his own inlet "
                f"tilt, which opens the posterior column triangle (Sikarinkul et al.)",
                book(f"posterior_column_triangle_{side}"))
    return out
