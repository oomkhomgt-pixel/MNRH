"""Plain-language guidance for a planned screw direction.

The engine already reports a trajectory as APP-frame angles
(``app_frame.screw_angles``) and renders a fixed set of named fluoroscopy
views (``drr``). Neither says the two things a surgeon says out loud while
aiming a guidewire: how far the wire runs up or down the patient, how far it
is swung anterior or posterior of straight medial, and where the C-arm has
to sit to look straight down the wire.

``describe_direction`` produces those words for a direction expressed in an
anatomical frame (``app_frame.Frame``: x_hat = patient left, y_hat =
anterior, z_hat = cephalad), and ``down_the_barrel_view`` produces the
``drr`` view angles (``rotate_x``/``rotate_z``, as in corridors.json's
``views_deg``) whose beam runs along the screw, so the screw projects to a
point. Exact floats are kept on the returned objects; only the sentences are
rounded, to whole degrees. The DRR is a parallel projection, so a barrel
view is a C-arm starting position, not an exact intra-operative readout.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# A direction within this of the transverse plane is called "in the axial
# plane" rather than given a tiny cephalad/caudad angle; the same tolerance
# decides when an in-plane angle is "straight" and when a direction runs too
# close to the long axis to have an in-plane direction at all.
AXIAL_PLANE_TOLERANCE_DEG = 1.0

SIDES = ("left", "right", "midline")


@dataclass
class DirectionDescription:
    """A screw direction in words. Angles in degrees, exact (unrounded)."""

    side: str
    elevation_deg: float  # + cephalad, - caudad, 0 in the transverse plane
    elevation_word: str  # "cephalad" | "caudad" | "in the axial plane"
    in_plane_deg: float  # + anterior of the reference, - posterior; 0 if undefined
    in_plane_word: str  # "anterior" | "posterior" | "" when straight along the reference
    in_plane_reference: str  # "medial" | "lateral" | "toward the patient's left/right"
    in_plane_defined: bool  # False when the direction runs along the long axis
    sentence: str


@dataclass
class BarrelView:
    """C-arm angles for looking straight down a direction, in ``drr``'s convention."""

    rotate_x_deg: float
    rotate_z_deg: float
    reading: str


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def _degrees(value: float) -> str:
    n = int(round(abs(value)))
    return f"{n} degree" if n == 1 else f"{n} degrees"


def describe_direction(direction_world, frame, side: str) -> DirectionDescription:
    """Describe a screw direction (unit vector, entry -> tip, RAS world) as an
    elevation out of the transverse plane plus an in-plane (axial) swing.

    ``frame`` is the anatomical frame the angles are measured in (usually the
    APP frame). ``side`` is the screw's own side, since medial and lateral are
    opposite world directions on the two sides: "left" or "right", or
    "midline" for a screw belonging to neither, which is then described as
    running toward the patient's left or right instead.
    """
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}, got {side!r}")

    d = _unit(direction_world)
    lx = float(np.dot(d, frame.x_hat))  # toward the patient's left
    ly = float(np.dot(d, frame.y_hat))  # anterior
    lz = float(np.dot(d, frame.z_hat))  # cephalad

    elevation = float(np.degrees(np.arcsin(np.clip(lz, -1.0, 1.0))))
    if abs(elevation) <= AXIAL_PLANE_TOLERANCE_DEG:
        elevation_word = "in the axial plane"
    else:
        elevation_word = "cephalad" if elevation > 0 else "caudad"

    # The horizontal (axial) component is measured from whichever of the
    # side's medial/lateral axis it is nearer, so the angle is never more than
    # 90 degrees and the reference is the one the surgeon would name. Close to
    # the long axis there is no meaningful in-plane direction at all.
    horizontal = float(np.hypot(lx, ly))
    defined = horizontal > np.sin(np.radians(AXIAL_PLANE_TOLERANCE_DEG))

    if side == "midline":
        toward_left = lx >= 0.0
        reference = "toward the patient's left" if toward_left else "toward the patient's right"
        along_reference = lx if toward_left else -lx
    else:
        medial = lx if side == "right" else -lx  # medial is toward the other side
        reference = "medial" if medial >= 0.0 else "lateral"
        along_reference = abs(medial)

    in_plane = float(np.degrees(np.arctan2(ly, along_reference))) if defined else 0.0
    ap_word = "anterior" if in_plane > 0 else "posterior"

    if not defined:
        reference = ""
        in_plane_word = ""
        in_plane_phrase = "no in-plane direction"
    elif abs(in_plane) <= AXIAL_PLANE_TOLERANCE_DEG:
        in_plane_word = ""
        in_plane_phrase = f"straight {reference}"
    elif abs(abs(in_plane) - 90.0) <= AXIAL_PLANE_TOLERANCE_DEG:
        in_plane_word = ap_word
        in_plane_phrase = f"straight {ap_word}"
    else:
        in_plane_word = ap_word
        in_plane_phrase = f"{_degrees(in_plane)} {ap_word} of straight {reference}"

    if elevation_word == "in the axial plane":
        sentence = f"in the axial plane, {in_plane_phrase}"
    elif not defined:
        sentence = f"{_degrees(elevation)} {elevation_word}, with no in-plane direction"
    else:
        sentence = f"{_degrees(elevation)} {elevation_word}, and in the axial plane {in_plane_phrase}"

    return DirectionDescription(
        side=side,
        elevation_deg=elevation,
        elevation_word=elevation_word,
        in_plane_deg=in_plane,
        in_plane_word=in_plane_word,
        in_plane_reference=reference,
        in_plane_defined=defined,
        sentence=sentence,
    )


def down_the_barrel_view(direction_world) -> BarrelView:
    """C-arm angles at which ``drr`` looks straight down ``direction_world``.

    The beam row of ``drr.view_rotation(rx, rz)`` is the AP beam (0, -1, 0)
    tilted by -rx about x and then rolled by -rz about z, which works out to

        beam = (-sin(rz) cos(rx), -cos(rz) cos(rx), sin(rx)).

    Setting that equal to the direction d gives sin(rx) = d_z, and then
    cos(rx) scales (-sin(rz), -cos(rz)) onto (d_x, d_y). Two solutions exist,
    (rx, rz) and (180 - rx, rz + 180); rx = arcsin(d_z) picks the one within
    +-90 degrees of tilt, the C-arm position reachable over a supine patient.
    Exactly along the long axis the roll does nothing, so it is 0; just off
    the axis it still aims the beam, so it is kept exact there and only the
    wording falls back.
    """
    d = _unit(direction_world)
    rotate_x = float(np.degrees(np.arcsin(np.clip(d[2], -1.0, 1.0))))
    horizontal = float(np.hypot(d[0], d[1]))
    rotate_z = float(np.degrees(np.arctan2(-d[0], -d[1]))) if horizontal > 0.0 else 0.0
    along_long_axis = horizontal <= np.sin(np.radians(AXIAL_PLANE_TOLERANCE_DEG))

    if abs(rotate_x) <= AXIAL_PLANE_TOLERANCE_DEG:
        tilt = "no cranio-caudal tilt"
    elif rotate_x > 0:
        tilt = f"{_degrees(rotate_x)} of outlet (cephalad) tilt"
    else:
        tilt = f"{_degrees(rotate_x)} of inlet (caudad) tilt"

    # Positive rotate_z brings the beam in from the patient's right (drr's
    # module docstring); 0 is the beam from in front, +-180 from behind.
    roll = abs(rotate_z)
    from_side = "right" if rotate_z > 0 else "left"
    if along_long_axis:
        entry = "the beam along the patient's long axis, from the " + ("feet" if rotate_x > 0 else "head")
    elif roll <= AXIAL_PLANE_TOLERANCE_DEG:
        entry = "the beam straight from in front (AP)"
    elif abs(roll - 180.0) <= AXIAL_PLANE_TOLERANCE_DEG:
        entry = "the beam straight from behind (PA)"
    elif abs(roll - 90.0) <= AXIAL_PLANE_TOLERANCE_DEG:
        entry = f"a lateral, the beam entering from the patient's {from_side}"
    elif roll < 90.0:
        entry = f"{_degrees(roll)} oblique, the beam entering from the patient's {from_side}"
    else:
        entry = f"{_degrees(180.0 - roll)} oblique, the beam entering from behind on the patient's {from_side}"

    return BarrelView(rotate_x_deg=rotate_x, rotate_z_deg=rotate_z, reading=f"{tilt}, {entry}")
