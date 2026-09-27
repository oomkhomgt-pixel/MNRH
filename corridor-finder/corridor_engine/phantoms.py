"""Synthetic volumes for unit testing the geometry engine without a real CT.

All phantoms use 1.0 mm isotropic spacing and return a plain (mask/labels,
spacing, origin) tuple rather than a Volume, since tests often want both the
HU-like array and a labelled version.
"""
from __future__ import annotations

import numpy as np

from . import segmentation as seg


def solid_rod(shape=(60, 60, 120), radius_mm: float = 8.0, axis: int = 2) -> np.ndarray:
    """A solid cylinder of the given radius running along ``axis`` (default z),
    centered in the other two dimensions. Returns a boolean mask, shape ZYX.
    """
    nz, ny, nx = shape
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    center = {0: (ny / 2.0, nx / 2.0), 1: (nz / 2.0, nx / 2.0), 2: (nz / 2.0, ny / 2.0)}
    if axis == 2:  # along x-index? we define axis=2 as the array's last axis (x)
        d = np.sqrt((zz - nz / 2.0) ** 2 + (yy - ny / 2.0) ** 2)
    elif axis == 1:
        d = np.sqrt((zz - nz / 2.0) ** 2 + (xx - nx / 2.0) ** 2)
    else:
        d = np.sqrt((yy - ny / 2.0) ** 2 + (xx - nx / 2.0) ** 2)
    return d <= radius_mm


def plate_with_hole(shape=(60, 60, 20), hole_radius_mm: float = 4.0) -> np.ndarray:
    """A solid slab (bone plate) filling the whole volume except a cylindrical
    hole (simulating a screw hole / foramen) running along the last axis (x).
    A corridor search along x should avoid the hole region.
    """
    nz, ny, nx = shape
    zz, yy, _xx = np.mgrid[0:nz, 0:ny, 0:nx]
    hole_center = (nz * 0.5, ny * 0.75)  # off-center so a "safe" path exists elsewhere
    d = np.sqrt((zz - hole_center[0]) ** 2 + (yy - hole_center[1]) ** 2)
    mask = np.ones(shape, dtype=bool)
    mask &= d[:, :, 0:1].repeat(nx, axis=2) > hole_radius_mm
    return mask


def pelvis_like(shape=(140, 160, 200)):
    """A crude pelvis-ring analogue: two curved "ilium" slabs, a central
    "sacrum" block bridging them, and a thin "anterior column" tube linking
    each ilium to a "pubic" region near the midline at the bottom.

    Returns (labels, spacing) with spacing=(1.5, 1.5, 1.5) mm, using the
    same label ids as corridor_engine.segmentation.
    """
    nz, ny, nx = shape
    labels = np.zeros(shape, dtype=np.uint8)
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    cx = nx / 2.0

    # Ilium: a curved shell (thick torus-like arc) on each side, spanning
    # most of the height, offset laterally.
    for side_label, sign in ((seg.HIP_L, -1), (seg.HIP_R, 1)):
        ring_cx = cx + sign * nx * 0.30
        ring_cy = ny * 0.55
        r_mid = nx * 0.22
        thickness = nx * 0.06
        dist = np.sqrt((xx - ring_cx) ** 2 + (yy - ring_cy) ** 2)
        # Restrict to this side of the true pelvic midline so the shell
        # doesn't wrap around into the opposite hemisphere (real ilia don't).
        own_side = (sign * (xx - cx)) > -nx * 0.02
        shell = (np.abs(dist - r_mid) < thickness) & (zz > nz * 0.15) & (zz < nz * 0.9) & own_side
        labels[shell & (labels == 0)] = side_label

        # A thin "anterior column" tube from near the pubis (bottom-medial)
        # up to the ilium (top-lateral), radius ~6mm at 1.5mm spacing (~4 vox).
        p0 = np.array([nz * 0.25, ny * 0.35, cx + sign * nx * 0.08])
        p1 = np.array([nz * 0.75, ny * 0.55, ring_cx])
        n_steps = 200
        radius_vox = 4.0
        for t in np.linspace(0.0, 1.0, n_steps):
            c = p0 + t * (p1 - p0)
            zlo, zhi = int(c[0] - radius_vox - 1), int(c[0] + radius_vox + 2)
            ylo, yhi = int(c[1] - radius_vox - 1), int(c[1] + radius_vox + 2)
            xlo, xhi = int(c[2] - radius_vox - 1), int(c[2] + radius_vox + 2)
            zlo, ylo, xlo = max(zlo, 0), max(ylo, 0), max(xlo, 0)
            zhi, yhi, xhi = min(zhi, nz), min(yhi, ny), min(xhi, nx)
            sub_z, sub_y, sub_x = zz[zlo:zhi, ylo:yhi, xlo:xhi], yy[zlo:zhi, ylo:yhi, xlo:xhi], xx[zlo:zhi, ylo:yhi, xlo:xhi]
            d = np.sqrt((sub_z - c[0]) ** 2 + (sub_y - c[1]) ** 2 + (sub_x - c[2]) ** 2)
            region = labels[zlo:zhi, ylo:yhi, xlo:xhi]
            region[(d <= radius_vox) & (region == 0)] = side_label

    # Sacrum: a central block bridging both ilia in the middle third of x,
    # touching (but not identical to) both hip labels — simulates the SI joints.
    sacrum_mask = (
        (np.abs(xx - cx) < nx * 0.10)
        & (yy > ny * 0.40) & (yy < ny * 0.70)
        & (zz > nz * 0.30) & (zz < nz * 0.80)
    )
    labels[sacrum_mask & (labels == 0)] = seg.SACRUM

    return labels, (1.5, 1.5, 1.5)


# --------------------------------------------------------------------------
# A fractured pelvis with a known displacement (displacement-finder DECISIONS
# 6.2): the only exact ground truth there is. Everything below is added for
# the displacement finder; the phantoms above are unchanged.

from dataclasses import dataclass as _dataclass  # noqa: E402


def _segment_distance(p, a, b):
    """Distance from each point (px, py, pz arrays) to the segment a-b."""
    a = np.asarray(a, dtype=float)
    ab = np.asarray(b, dtype=float) - a
    t = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1] + (p[2] - a[2]) * ab[2]) / float(ab @ ab)
    t = np.clip(t, 0.0, 1.0)
    return np.sqrt((p[0] - a[0] - t * ab[0]) ** 2 + (p[1] - a[1] - t * ab[1]) ** 2 + (p[2] - a[2] - t * ab[2]) ** 2)


def _ellipsoid(p, centre, radii):
    return np.sqrt(sum(((p[i] - centre[i]) / radii[i]) ** 2 for i in range(3)))


# The acetabular centre and the femoral head's (lateral, anterior, cephalad).
_ACETABULUM = (78.0, 12.0, -12.0)
_HEAD = (86.0, 16.0, -16.0)


def _sacral_half_width(z):
    return 22.0 + 0.25 * (z + 15.0)


def _pelvis_parts(p):
    """Each bone of the phantom, in its own patient frame (x = patient
    right, y = anterior, z = cephalad, mm, midline at x = 0). Built from
    shapes with no symmetry of their own beyond left-right, so a rigid fit
    cannot slide along any of them. Returns boolean masks by name."""
    x, y, z = p
    u = np.abs(x)
    q = (u, y, z)

    # Sacrum: widening toward S1, curving back toward its tip, with a canal.
    yc = np.where(z < 22.0, -42.0 - 0.15 * (22.0 - z), -42.0)
    sacrum = ((u < _sacral_half_width(z)) & ((y - yc) ** 2 / 20.0 ** 2 + (z - 22.0) ** 2 / 38.0 ** 2 <= 1.0)
              & ~((x ** 2 + (y - yc + 8.0) ** 2 < 6.0 ** 2) & (z > 0.0)))

    # Hip bone: a curved iliac wing, the thick posterior ilium at the SI
    # joint, the acetabulum as a cup, the columns and both rami.
    r = _ellipsoid(q, (15.0, 5.0, 35.0), (80.0, 62.0, 68.0))
    hip = (r > 0.87) & (r <= 1.0) & (u > 42.0) & (z > 5.0) & (y > -60.0) & (y < 45.0)
    hip |= _ellipsoid(q, (42.0, -38.0, 35.0), (16.0, 22.0, 32.0)) <= 1.0
    cup = _ellipsoid(q, _HEAD, (25.0, 25.0, 25.0)) <= 1.0
    hip |= (_ellipsoid(q, _ACETABULUM, (30.0, 30.0, 30.0)) <= 1.0) & ~cup
    for a, b, radius in (
        ((80.0, 5.0, 0.0), (75.0, -5.0, 40.0), 14.0),  # the pillar above the acetabulum
        ((45.0, -35.0, 20.0), (72.0, 0.0, -10.0), 11.0),  # posterior column
        ((62.0, 32.0, -8.0), (4.0, 55.0, -28.0), 9.0),  # superior ramus
        ((4.0, 52.0, -40.0), (50.0, -2.0, -62.0), 7.0),  # inferior ramus
        ((72.0, -2.0, -25.0), (52.0, -6.0, -64.0), 12.0),  # ischium
    ):
        hip |= _segment_distance(q, a, b) <= radius
    hip |= _ellipsoid(q, (10.0, 54.0, -33.0), (10.0, 10.0, 10.0)) <= 1.0  # symphyseal body
    # A 6 mm symphysis, and a 3 mm SI joint along the sacrum's lateral face.
    hip &= (u >= 3.0) & ~((u < _sacral_half_width(z) + 3.0) & (y < -15.0) & (z > -20.0) & (z < 65.0))
    hip &= ~sacrum

    head = (_ellipsoid(q, _HEAD, (22.0, 22.0, 22.0)) <= 1.0) & ~hip

    # L5, wedged (taller in front) with its arch sloping down, and L4 above.
    top = 96.0 + 0.2 * (y + 30.0)
    lumbar = ((x / 24.0) ** 2 + ((y + 30.0) / 16.0) ** 2 <= 1.0) & (z >= 68.0) & (z <= top)
    for a, b, radius in (
        ((12.0, -44.0, 84.0), (12.0, -56.0, 84.0), 5.0),  # pedicle
        ((12.0, -56.0, 84.0), (0.0, -62.0, 82.0), 4.0),  # lamina
        ((12.0, -46.0, 88.0), (48.0, -42.0, 94.0), 5.0),  # transverse process
    ):
        lumbar |= _segment_distance(q, a, b) <= radius
    lumbar |= _segment_distance(p, (0.0, -62.0, 82.0), (0.0, -82.0, 74.0)) <= 5.0  # spinous process
    lumbar |= ((x / 23.0) ** 2 + ((y + 28.0) / 15.0) ** 2 <= 1.0) & (z >= 104.0) & (z <= 130.0)  # L4
    lumbar |= _segment_distance(p, (0.0, -58.0, 117.0), (0.0, -80.0, 108.0)) <= 5.0

    return {"sacrum": sacrum, "hip": hip, "head": head, "lumbar": lumbar}


def _rotation(axis, angle_deg):
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    a = np.radians(angle_deg)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(a) * k + (1 - np.cos(a)) * (k @ k)


@_dataclass
class FracturedPelvis:
    labels: np.ndarray  # ZYX, segmentation ids, the fragment moved
    spacing: tuple
    origin: tuple
    intact_labels: np.ndarray  # the same pelvis before the fragment moved
    fragment: np.ndarray  # where the fragment is now, in ``labels``
    fragment_before: np.ndarray  # where it was, in ``intact_labels``
    moved_by: np.ndarray  # 4x4 world transform that displaced it
    side: str

    @property
    def to_reference(self) -> np.ndarray:
        """The exact transform home. The phantom is symmetric, so home is
        also where the mirrored other side puts it."""
        return np.linalg.inv(self.moved_by)


def fractured_pelvis(translate_mm=(0.0, 0.0, 0.0), rotate_deg: float = 0.0, rotate_axis=(0.0, 0.0, 1.0),
                     side: str = "right", cut_point=(75.0, 0.0, 45.0), cut_normal=(0.2, 0.3, 1.0),
                     yaw_deg: float = 0.0, spacing_mm: float = 1.5) -> FracturedPelvis:
    """A symmetric pelvis with a lumbar spine, one hemipelvis cut along a
    plane and the piece beyond it moved rigidly: rotated by ``rotate_deg``
    about ``rotate_axis`` through its own centroid, then translated.

    ``cut_point`` and ``cut_normal`` are in the patient frame with x
    lateral toward ``side``; the default cuts off the upper iliac wing and
    the top of the posterior ilium. ``yaw_deg`` turns the whole patient
    about the scanner's z axis, so the mirror plane is not a grid plane.
    With no motion the result is the intact pelvis, as the null test needs.
    The motion is applied analytically, point by point, not by resampling
    a voxel mask, so the truth is exact to the grid."""
    if side not in ("right", "left"):
        raise ValueError(f"side must be 'right' or 'left', got {side!r}")
    sign = 1.0 if side == "right" else -1.0
    s = float(spacing_mm)
    half = np.array([135.0, 95.0, 110.0]) + 10.0 * abs(np.sin(np.radians(yaw_deg)))
    n = np.ceil(2.0 * half / s).astype(int) // 2 * 2  # even, so voxel centres are symmetric about x = 0
    origin = (-(n[0] - 1) * s / 2.0, -(n[1] - 1) * s / 2.0 - 5.0, -(n[2] - 1) * s / 2.0 + 25.0)
    zz, yy, xx = np.meshgrid(*(o + np.arange(k) * s for o, k in zip(origin[::-1], n[::-1])), indexing="ij")
    world = np.stack([xx, yy, zz])

    yaw = _rotation((0.0, 0.0, 1.0), yaw_deg)  # patient frame -> world

    def to_patient(w):
        return np.einsum("ji,j...->i...", yaw, w)

    def label(parts, px):
        out = np.zeros(xx.shape, dtype=np.uint8)
        out[parts["lumbar"]] = seg.LUMBAR
        out[parts["sacrum"]] = seg.SACRUM
        out[parts["hip"] & (px > 0)] = seg.HIP_R
        out[parts["hip"] & (px < 0)] = seg.HIP_L
        out[parts["head"] & (px > 0)] = seg.FEMUR_R
        out[parts["head"] & (px < 0)] = seg.FEMUR_L
        return out

    def beyond_cut(pp):
        c = np.array([sign * cut_point[0], cut_point[1], cut_point[2]])
        nrm = np.array([sign * cut_normal[0], cut_normal[1], cut_normal[2]])
        return sum((pp[i] - c[i]) * nrm[i] for i in range(3)) > 0.0

    patient = to_patient(world)
    intact = label(_pelvis_parts(patient), patient[0])
    hip_id = seg.HIP_R if side == "right" else seg.HIP_L
    before = (intact == hip_id) & beyond_cut(patient)

    centroid = np.array([xx[before].mean(), yy[before].mean(), zz[before].mean()])
    moved_by = np.eye(4)
    moved_by[:3, :3] = _rotation(rotate_axis, rotate_deg)
    moved_by[:3, 3] = centroid - moved_by[:3, :3] @ centroid + np.asarray(translate_mm, dtype=float)

    # Where each voxel was before the move, and whether that was fragment.
    inverse = np.linalg.inv(moved_by)
    source = np.einsum("ij,j...->i...", inverse[:3, :3], world) + inverse[:3, 3][:, None, None, None]
    source_patient = to_patient(source)
    now = _pelvis_parts(source_patient)["hip"] & (source_patient[0] * sign > 0) & beyond_cut(source_patient)

    labels = intact.copy()
    labels[before] = 0
    labels[now] = hip_id
    return FracturedPelvis(labels, (s, s, s), tuple(float(v) for v in origin), intact, now, before, moved_by, side)
