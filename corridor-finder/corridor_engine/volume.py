"""Volume container and resampling.

World coordinates throughout corridor_engine are RAS, the same as 3D
Slicer's: x = patient Right+, y = Anterior+, z = Superior+ (a right-handed
frame, so exported meshes are never mirror images).

Arrays are stored ZYX (numpy convention). ``spacing`` and ``origin`` are
(x, y, z) mm tuples; spacing is always positive, so increasing array index
moves toward patient right, anterior and superior. The Slicer module
reorders each CT's voxels to guarantee this (a DICOM CT usually runs the
other way along x and y).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Tuple

import numpy as np
from scipy.ndimage import zoom as _zoom

Vec3 = Tuple[float, float, float]


@dataclass
class Volume:
    """A 3D array with physical spacing/origin.

    array: numpy array, shape (nz, ny, nx).
    spacing: (sx, sy, sz) mm per voxel.
    origin: (ox, oy, oz) mm, world position of voxel (0, 0, 0).
    """

    array: np.ndarray
    spacing: Vec3
    origin: Vec3 = (0.0, 0.0, 0.0)

    @property
    def shape_xyz(self) -> Tuple[int, int, int]:
        nz, ny, nx = self.array.shape
        return (nx, ny, nz)

    def ijk_to_world(self, ijk) -> np.ndarray:
        """ijk = (i, j, k) matching array axes order (x=i, y=j, z=k)."""
        i, j, k = ijk
        sx, sy, sz = self.spacing
        ox, oy, oz = self.origin
        return np.array([ox + i * sx, oy + j * sy, oz + k * sz], dtype=float)

    def world_to_ijk(self, xyz) -> np.ndarray:
        x, y, z = xyz
        sx, sy, sz = self.spacing
        ox, oy, oz = self.origin
        return np.array([(x - ox) / sx, (y - oy) / sy, (z - oz) / sz], dtype=float)

    def world_to_zyx_index(self, xyz) -> np.ndarray:
        """Return (k, j, i) = (z_idx, y_idx, x_idx) matching array.shape order."""
        i, j, k = self.world_to_ijk(xyz)
        return np.array([k, j, i], dtype=float)

    def world_to_zyx_indices(self, xyz_points: np.ndarray) -> np.ndarray:
        """Vectorized form of world_to_zyx_index for an (N, 3) array of points."""
        pts = np.atleast_2d(np.asarray(xyz_points, dtype=float))
        sx, sy, sz = self.spacing
        ox, oy, oz = self.origin
        i = (pts[:, 0] - ox) / sx
        j = (pts[:, 1] - oy) / sy
        k = (pts[:, 2] - oz) / sz
        return np.stack([k, j, i], axis=0)

    def zyx_indices_to_world(self, zyx_indices: np.ndarray) -> np.ndarray:
        """Vectorized inverse of world_to_zyx_indices.

        zyx_indices: array shape (N, 3) of (k, j, i) i.e. (z_idx, y_idx, x_idx).
        Returns an (N, 3) array of (x, y, z) world coordinates.
        """
        idx = np.atleast_2d(zyx_indices)
        sx, sy, sz = self.spacing
        ox, oy, oz = self.origin
        k, j, i = idx[:, 0], idx[:, 1], idx[:, 2]
        x = ox + i * sx
        y = oy + j * sy
        z = oz + k * sz
        return np.stack([x, y, z], axis=1)

    def mask_voxel_centers_world(self, mask: np.ndarray) -> np.ndarray:
        """World-space coordinates of every True voxel in a boolean mask that
        shares this volume's grid. Returns an (N, 3) array of (x, y, z)."""
        zyx = np.argwhere(mask)
        return self.zyx_indices_to_world(zyx)

    def sample_trilinear(self, xyz_points: np.ndarray, order: int = 1, cval: float = 0.0) -> np.ndarray:
        """Sample the volume at an array of world-space points, shape (N, 3)."""
        from scipy.ndimage import map_coordinates

        zyx = self.world_to_zyx_indices(xyz_points)
        return map_coordinates(self.array, zyx, order=order, cval=cval, mode="constant")


def resample_to(vol: Volume, target_spacing_mm: float, order: int = 1) -> Volume:
    """Resample to isotropic ``target_spacing_mm``.

    Use order=1 for continuous (HU) volumes, order=0 for integer label
    volumes so label ids are never blended into fractional values.
    """
    sx, sy, sz = vol.spacing
    zoom_factors = (sz / target_spacing_mm, sy / target_spacing_mm, sx / target_spacing_mm)
    resampled = _zoom(vol.array, zoom_factors, order=order, mode="nearest" if order == 0 else "constant")
    new_spacing = (target_spacing_mm, target_spacing_mm, target_spacing_mm)
    return Volume(array=resampled, spacing=new_spacing, origin=vol.origin)


def clone_with(vol: Volume, array: np.ndarray) -> Volume:
    return replace(vol, array=array)
