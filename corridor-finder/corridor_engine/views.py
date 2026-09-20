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

from . import segmentation as seg
from .volume import Volume

# A wing, a ring or a sacral face is fitted from bone within these bounds.
WING_ABOVE_BRIM_MM = 10.0  # iliac wing: bone this far above the brim and up
SACRAL_FACE_MM = 6.0  # how deep the sacrum's front face is taken
OBLIQUE_ROTATION_DEG = 45.0  # the Judet rotation, taken about the patient's own axis
MIN_FIT_POINTS = 50


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


def patient_views(labels_vol: Volume, landmarks: Dict[str, object], frame=None,
                  textbook: Optional[Dict[str, dict]] = None) -> Dict[str, View]:
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

        # Obturator oblique: the ring of that side face-on. The ring itself
        # is not segmented, so this is the classic 45 degrees of rotation,
        # but taken about THIS patient's cephalad axis and from HIS square
        # AP, so his pelvic tilt and any rotation on the table are already
        # in it. The rotation itself is still the textbook one.
        beam = _rotate_about(posterior, cephalad, -sign * OBLIQUE_ROTATION_DEG)
        out[f"obturator_oblique_{side}"] = _view(
            f"obturator_oblique_{side}", beam,
            f"{OBLIQUE_ROTATION_DEG:.0f} degrees around this patient's own upright axis, entering from the "
            f"other side, which opens the {side} obturator ring, the anterior column and the posterior wall",
            book(f"obturator_oblique_{side}"))

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
