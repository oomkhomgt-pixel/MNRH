"""Anterior Pelvic Plane (APP) frame construction and angle reporting.

The APP is defined by both ASIS points and the midpoint of both pubic
tubercles (the classic definition used for cup anteversion/inclination
reporting). Screw trajectory angles are reported both relative to this
frame and relative to the raw scanner axes, since the surgeon may want
either depending on how the patient was positioned.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


@dataclass
class Frame:
    origin: np.ndarray
    x_hat: np.ndarray  # patient left
    y_hat: np.ndarray  # anterior
    z_hat: np.ndarray  # cephalad

    def to_local(self, xyz: np.ndarray) -> np.ndarray:
        rel = np.asarray(xyz, dtype=float) - self.origin
        return np.array([np.dot(rel, self.x_hat), np.dot(rel, self.y_hat), np.dot(rel, self.z_hat)])

    def to_world(self, local_xyz: np.ndarray) -> np.ndarray:
        lx, ly, lz = local_xyz
        return self.origin + lx * self.x_hat + ly * self.y_hat + lz * self.z_hat

    def as_matrix(self) -> np.ndarray:
        return np.stack([self.x_hat, self.y_hat, self.z_hat], axis=0)


def build_app(asis_right, asis_left, pubic_tubercle_right, pubic_tubercle_left, scanner_z_hint=(0.0, 0.0, 1.0)) -> Frame:
    """Build the APP frame from the four landmark points (world xyz).

    scanner_z_hint disambiguates the sign of z_hat (cephalad) so that, for a
    normally-oriented scan, z_hat points toward the head rather than the feet.
    """
    asis_right = np.asarray(asis_right, dtype=float)
    asis_left = np.asarray(asis_left, dtype=float)
    pt_right = np.asarray(pubic_tubercle_right, dtype=float)
    pt_left = np.asarray(pubic_tubercle_left, dtype=float)

    origin = (asis_right + asis_left) / 2.0
    pt_mid = (pt_right + pt_left) / 2.0

    x_hat = asis_left - asis_right
    x_hat = x_hat / np.linalg.norm(x_hat)

    v = pt_mid - origin
    n = np.cross(x_hat, v)
    norm_n = np.linalg.norm(n)
    if norm_n < 1e-9:
        raise ValueError("ASIS and pubic tubercle points are degenerate (collinear)")
    y_hat = n / norm_n
    # y_hat should point anterior, i.e. roughly toward pt_mid from origin along
    # the coronal-plane component; ensure sign by checking it points toward v.
    if np.dot(y_hat, v) < 0:
        y_hat = -y_hat

    z_hat = np.cross(x_hat, y_hat)
    z_hat = z_hat / np.linalg.norm(z_hat)
    if np.dot(z_hat, scanner_z_hint) < 0:
        z_hat = -z_hat
        # re-orthogonalize y_hat to keep a right-handed frame with the flipped z
        y_hat = np.cross(z_hat, x_hat)
        y_hat = y_hat / np.linalg.norm(y_hat)

    return Frame(origin=origin, x_hat=x_hat, y_hat=y_hat, z_hat=z_hat)


def pelvic_tilt_deg(app: Frame, scanner_z_hint=(0.0, 0.0, 1.0)) -> float:
    """Angle between the APP's z_hat and the scanner's z axis, i.e. how much
    the patient's pelvis is tilted relative to the scanner table."""
    z = np.asarray(scanner_z_hint, dtype=float)
    z = z / np.linalg.norm(z)
    cos_a = np.clip(np.dot(app.z_hat, z), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_a)))


def screw_angles(direction_world: np.ndarray, frame: Frame) -> Dict[str, float]:
    """Inclination/anteversion/axial angles of a screw direction in a frame.

    direction_world: unit vector, entry -> target.
    - inclination: angle from the frame's z axis (cephalad), measured in the
      x-z (coronal) plane -- how much the screw tilts up/down.
    - anteversion: angle of the direction out of the x-z plane, toward y
      (anterior) -- positive means directed anteriorly.
    - axial: angle in the x-y plane from the x axis, for reference.
    """
    d = np.asarray(direction_world, dtype=float)
    d = d / np.linalg.norm(d)
    local = frame.to_local(frame.origin + d) - frame.to_local(frame.origin)
    lx, ly, lz = local
    inclination = float(np.degrees(np.arctan2(lx, lz)))
    anteversion = float(np.degrees(np.arcsin(np.clip(ly, -1.0, 1.0))))
    axial = float(np.degrees(np.arctan2(ly, lx)))
    return {"inclination_deg": inclination, "anteversion_deg": anteversion, "axial_deg": axial}


def scanner_frame() -> Frame:
    """Identity frame representing the raw scanner axes, for reporting
    angles "relative to scanner axes" alongside the APP-relative angles."""
    return Frame(
        origin=np.zeros(3),
        x_hat=np.array([1.0, 0.0, 0.0]),
        y_hat=np.array([0.0, 1.0, 0.0]),
        z_hat=np.array([0.0, 0.0, 1.0]),
    )
