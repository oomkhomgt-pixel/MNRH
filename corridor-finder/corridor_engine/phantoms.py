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
