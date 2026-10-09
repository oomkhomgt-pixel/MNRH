"""This patient's true axial, coronal and sagittal planes, from intact
anatomy first (the surgeon, 2026-10-05; Corridor Finder DECISIONS.md 8.5,
shared with the displacement measurement under 8.4).

A measurement compared left against right is only fair on a cut that is
truly symmetrical: on the scanner's own axial slices a pelvis lying rolled
on the table has its left and right sacroiliac joints cut at different
heights, and the difference reads as asymmetry. So the planes are built
from the patient's anatomy, in the order the surgeon set:

1. The FIRST plane is the mid-sagittal plane, fitted to the sacral midline:
   the S1 and S2 (and S3) vertebral body centres and the centre of the
   sacral canal at those levels. The sacral body and canal are usually
   intact in zone I and II fractures, and depend on neither hemipelvis.
2. The true coronal contains the left-right axis that plane gives and is
   tilted parallel to the anterior pelvic plane of the INTACT hemipelvis
   (its ASIS and pubic tubercle; both sides when both are intact). A
   displaced hemipelvis's ASIS is not used.
3. The true axial is square to both.
4. The surgeon may then turn the frame himself: tilt (about the left-right
   axis), roll (about the front-back axis) and yaw (about the long axis),
   in degrees.

The frame is an app_frame.Frame, so everything that reads the anterior
pelvic plane frame (views, screw angles) reads this one the same way:
x_hat toward the patient's LEFT, y_hat anterior, z_hat cephalad.

``reslice`` resamples a volume onto the true planes. Its world coordinates
are anatomical millimetres -- x toward the patient's right, y anterior, z
cephalad, from the frame's origin -- so code written for an RAS volume
(the sacroiliac joint measurement) runs on it unchanged, and every axial
cut of it crosses left and right at the same anatomical level.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage as ndi

from .app_frame import Frame
from .volume import Volume

MIN_SPREAD_MM = 3.0  # the midline points must span a plane, not a line
CANAL_LEVEL_MM = 3.0  # the canal centre is taken within this of each body centre's height
CANAL_BEHIND_MM = 5.0  # and at least this far behind the body centre
CANAL_LATERAL_MM = 12.0  # and no further than this to either side of it (a foramen is further)
CANAL_MIN_AREA_MM2 = 30.0  # smaller holes are not the canal


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        raise ValueError("zero-length direction")
    return v / n


def _rotate(v: np.ndarray, axis: np.ndarray, degrees: float) -> np.ndarray:
    k = _unit(axis)
    a = np.radians(degrees)
    return v * np.cos(a) + np.cross(k, v) * np.sin(a) + k * float(k @ v) * (1.0 - np.cos(a))


def canal_centres(labels: Volume, landmarks: Dict[str, object], canal: np.ndarray) -> Dict[str, np.ndarray]:
    """The centre of the sacral canal at the height of each sacral body
    centre (s1/s2/s3_body_center): of the holes the canal mask has on the
    axial slices within CANAL_LEVEL_MM of that height, the largest that lies
    behind the body and within CANAL_LATERAL_MM of it from side to side (on
    CLINIC_0023 the nearest hole was an S1 foramen 23 mm to the side, and it
    turned the planes by 40 degrees)."""
    out: Dict[str, np.ndarray] = {}
    sx, sy, sz = labels.spacing
    ox, oy, oz = labels.origin
    for name in ("s1_body_center", "s2_body_center", "s3_body_center"):
        lm = landmarks.get(name)
        if lm is None:
            continue
        body = np.asarray(lm.xyz, dtype=float)
        k0 = int(round((body[2] - oz) / sz))
        reach = max(1, int(round(CANAL_LEVEL_MM / sz)))
        found = []
        for k in range(max(k0 - reach, 0), min(k0 + reach + 1, canal.shape[0])):
            pieces, n = ndi.label(canal[k])
            best = None
            for p in range(1, n + 1):
                jj, ii = np.nonzero(pieces == p)
                area = len(jj) * sx * sy
                x, y = ox + ii.mean() * sx, oy + jj.mean() * sy
                if (y > body[1] - CANAL_BEHIND_MM or abs(x - body[0]) > CANAL_LATERAL_MM
                        or area < CANAL_MIN_AREA_MM2):
                    continue
                if best is None or area > best[2]:
                    best = (x, y, area)
            if best is not None:
                found.append((best[0], best[1], oz + k * sz))
        if found:
            out[name.replace("body_center", "canal_center")] = np.mean(np.asarray(found), axis=0)
    return out


def pelvic_frame(midline_points: Optional[Sequence[Sequence[float]]], origin, asis_pubis_pairs: Sequence[Tuple] = (),
                 adjust_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0), anterior_hint=(0.0, 1.0, 0.0),
                 superior_hint=(0.0, 0.0, 1.0), sagittal_normal=None, long_axis=None) -> Frame:
    """The frame from the mid-sagittal plane -- its normal ``sagittal_normal``
    when it was fitted elsewhere (the sacrum's symmetry plane), or else the
    plane through the sacral midline points (3 or more) -- the intact
    hemipelves' (ASIS, pubic tubercle) pairs, and the surgeon's own (tilt,
    roll, yaw) in degrees. Without any intact pair the coronal follows
    ``long_axis`` (the sacrum's long direction; the points' own when not
    given). The hints only choose which way the axes point (RAS: +y
    anterior, +z cephalad for a supine scan)."""
    vt = None
    if sagittal_normal is not None:
        x_hat = _unit(sagittal_normal)
    else:
        pts = np.asarray(midline_points, dtype=float).reshape(-1, 3)
        if len(pts) < 3:
            raise ValueError("the mid-sagittal plane needs 3 or more sacral midline points")
        centre = pts.mean(axis=0)
        _, spread, vt = np.linalg.svd(pts - centre, full_matrices=False)
        if spread[1] / np.sqrt(len(pts)) < MIN_SPREAD_MM:
            raise ValueError("the sacral midline points lie nearly on one line: they do not fix a plane")
        x_hat = _unit(vt[2])
    if x_hat[0] > 0:  # toward the patient's left (-x in RAS)
        x_hat = -x_hat
    if asis_pubis_pairs:
        v = np.mean([_unit(np.asarray(a, float) - np.asarray(p, float)) for a, p in asis_pubis_pairs], axis=0)
    elif long_axis is not None:
        v = np.asarray(long_axis, dtype=float)
    elif vt is not None:
        v = vt[0]  # the midline's long direction
    else:
        raise ValueError("no intact anterior pelvic plane and no long axis to tilt the coronal by")
    v = _unit(v - float(v @ x_hat) * x_hat)
    y_hat = _unit(np.cross(x_hat, v))
    if float(y_hat @ np.asarray(anterior_hint, float)) < 0:
        y_hat = -y_hat
    z_hat = _unit(np.cross(x_hat, y_hat))
    if float(z_hat @ np.asarray(superior_hint, float)) < 0:
        z_hat = -z_hat
    return turned(Frame(origin=np.asarray(origin, dtype=float), x_hat=x_hat, y_hat=y_hat, z_hat=z_hat), adjust_deg)


def turned(frame: Frame, adjust_deg: Tuple[float, float, float]) -> Frame:
    """The frame turned about its own axes, in degrees: a tilt about its
    left-right axis, then a roll about its front-back axis, then a yaw about
    its long axis -- the surgeon's turn of the planes."""
    x_hat, y_hat, z_hat = frame.x_hat, frame.y_hat, frame.z_hat
    tilt, roll, yaw = (float(a) for a in adjust_deg)
    if tilt:
        y_hat, z_hat = _rotate(y_hat, x_hat, tilt), _rotate(z_hat, x_hat, tilt)
    if roll:
        x_hat, z_hat = _rotate(x_hat, y_hat, roll), _rotate(z_hat, y_hat, roll)
    if yaw:
        x_hat, y_hat = _rotate(x_hat, z_hat, yaw), _rotate(y_hat, z_hat, yaw)
    return Frame(origin=frame.origin, x_hat=x_hat, y_hat=y_hat, z_hat=z_hat)


# Turns of the planes a measurement must survive before anything is decided
# on it: 3 degrees each way about each axis, about what two careful readers
# setting up the planes by hand differ by.
STEADINESS_TURNS_DEG = ((-3.0, 0.0, 0.0), (3.0, 0.0, 0.0), (0.0, -3.0, 0.0), (0.0, 3.0, 0.0),
                        (0.0, 0.0, -3.0), (0.0, 0.0, 3.0))


def to_anatomical(frame: Frame, xyz) -> np.ndarray:
    """World (RAS) points -> anatomical mm: (toward the patient's right,
    anterior, cephalad) from the frame's origin."""
    rel = np.asarray(xyz, dtype=float).reshape(-1, 3) - frame.origin
    out = np.stack([-(rel @ frame.x_hat), rel @ frame.y_hat, rel @ frame.z_hat], axis=1)
    return out if np.ndim(xyz) > 1 else out[0]


def from_anatomical(frame: Frame, uvw) -> np.ndarray:
    u = np.asarray(uvw, dtype=float).reshape(-1, 3)
    out = frame.origin + (-u[:, :1]) * frame.x_hat + u[:, 1:2] * frame.y_hat + u[:, 2:3] * frame.z_hat
    return out if np.ndim(uvw) > 1 else out[0]


def anatomical_box(vol: Volume, frame: Frame, mask: np.ndarray, pad_mm: float = 10.0,
                   stride: int = 2) -> Tuple[np.ndarray, np.ndarray]:
    """The anatomical-mm box around ``mask`` (on ``vol``'s grid), padded."""
    idx = np.argwhere(mask[::stride, ::stride, ::stride]) * stride
    if not len(idx):
        raise ValueError("nothing to put a box around")
    u = to_anatomical(frame, vol.zyx_indices_to_world(idx))
    return u.min(axis=0) - pad_mm, u.max(axis=0) + pad_mm


def reslice(vol: Volume, frame: Frame, box_min, box_max, spacing_mm: Optional[float] = None, order: int = 0,
            cval: float = 0.0, slab: int = 16) -> Volume:
    """``vol`` resampled onto the true planes, over the anatomical box
    [box_min, box_max] (mm, as to_anatomical gives), at isotropic
    ``spacing_mm`` (default: the finest of ``vol``'s). order 0 for labels,
    1 for a CT. The result's world coordinates are anatomical mm."""
    s = float(spacing_mm or min(vol.spacing))
    box_min = np.asarray(box_min, dtype=float)
    box_max = np.asarray(box_max, dtype=float)
    n = np.maximum(np.ceil((box_max - box_min) / s).astype(int) + 1, 1)  # x, y, z
    out = np.empty((n[2], n[1], n[0]), dtype=vol.array.dtype)
    sx, sy, sz = vol.spacing
    ox, oy, oz = vol.origin
    ii, jj = np.meshgrid(np.arange(n[0]), np.arange(n[1]), indexing="xy")
    for k0 in range(0, n[2], slab):
        ks = np.arange(k0, min(k0 + slab, n[2]))
        u = np.stack([np.broadcast_to(box_min[0] + ii * s, (len(ks),) + ii.shape),
                      np.broadcast_to(box_min[1] + jj * s, (len(ks),) + ii.shape),
                      np.broadcast_to((box_min[2] + ks * s)[:, None, None], (len(ks),) + ii.shape)], axis=-1)
        world = from_anatomical(frame, u.reshape(-1, 3))
        coords = np.stack([(world[:, 2] - oz) / sz, (world[:, 1] - oy) / sy, (world[:, 0] - ox) / sx])
        out[ks[0]:ks[-1] + 1] = ndi.map_coordinates(vol.array, coords, order=order, cval=cval,
                                                     mode="constant").reshape(len(ks), n[1], n[0])
    return Volume(array=out, spacing=(s, s, s), origin=(float(box_min[0]), float(box_min[1]), float(box_min[2])))


def anatomical_landmarks(frame: Frame, landmarks: Dict[str, object]) -> Dict[str, object]:
    """The landmarks in anatomical mm (same names, same kind of object)."""
    return {name: dataclasses.replace(lm, xyz=to_anatomical(frame, np.asarray(lm.xyz, dtype=float)))
            for name, lm in landmarks.items()}


def turn_from_scanner(frame: Frame) -> Tuple[float, float, float]:
    """How far the frame is turned from the scanner's axes: (tilt, roll,
    yaw) in degrees."""
    tilt = float(np.degrees(np.arcsin(np.clip(float(frame.y_hat[2]), -1.0, 1.0))))
    roll = float(np.degrees(np.arcsin(np.clip(float(-frame.x_hat[2]), -1.0, 1.0))))
    yaw = float(np.degrees(np.arctan2(float(-frame.x_hat[1]), float(-frame.x_hat[0]))))
    return tilt, roll, yaw


# A patient lies on the CT table turned by less than this about any axis
# (the five pilot CLINIC cases: at most 10.6 degrees). Planes built turned
# further are taken to rest on a misplaced landmark: on the Panoramix sample
# CT, pubic tubercles found 99 mm apart tilted them 52 degrees.
MAX_PLAUSIBLE_TURN_DEG = 25.0


def implausible_turn(frame: Frame) -> Optional[str]:
    """Why the frame, as built from the anatomy (before the surgeon's own
    turn), cannot be how this patient lies; None if it can."""
    worst = max(zip(("tilt", "roll", "yaw"), turn_from_scanner(frame)), key=lambda t: abs(t[1]))
    if abs(worst[1]) <= MAX_PLAUSIBLE_TURN_DEG:
        return None
    return (f"the planes came out turned {abs(worst[1]):.0f} degrees ({worst[0]}) from the scanner, more than a "
            f"patient lies turned on the table: check the ASIS and pubic tubercle landmarks")


def describe(frame: Frame, built_from: List[str]) -> str:
    """One line for the panel: what the frame was built from and how far it
    is turned from the scanner's axes."""
    tilt, roll, yaw = turn_from_scanner(frame)
    return (f"true planes from {', '.join(built_from)}; turned from the scanner by tilt {tilt:+.1f}, roll "
            f"{roll:+.1f}, yaw {yaw:+.1f} degrees")
