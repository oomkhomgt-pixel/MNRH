"""Read a NIfTI image into an engine Volume, off Slicer.

Slicer is how a case reaches the module in theatre, and volume.py's
convention comes from there: array[z, y, x] laid out along +x (patient
right), +y (anterior) and +z (cephalad), with ``origin`` the world position
of voxel [0, 0, 0] and positive spacing. This reads a .nii/.nii.gz into
exactly that, so batch work -- a sweep over a public dataset, the blinded
validation of DECISIONS.md section 5 -- can run without starting Slicer.

Only axis-aligned images are accepted, the same restriction the Slicer path
applies: an oblique image would need resampling, and silently resampling a
CT under a plan is not something this should do quietly.

nibabel is required, and is not needed by the module itself; it is a
development and batch dependency (requirements-dev.txt).
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

from .volume import Volume

# An axis of the image counts as running along a world axis when the other
# two components of its direction are this small.
OFF_AXIS_TOLERANCE = 1e-3


class NotAxisAligned(ValueError):
    """The image's axes do not run along the world axes."""


def _axis_order(affine: np.ndarray) -> Tuple[Tuple[int, int, int], np.ndarray, np.ndarray]:
    """Which world axis each image axis runs along, with the sign and the
    spacing. Raises when an image axis is not along one."""
    direction = affine[:3, :3]
    spacing = np.linalg.norm(direction, axis=0)
    if np.any(spacing <= 0):
        raise NotAxisAligned("an image axis has zero length")
    unit = direction / spacing
    world_of_axis, signs = [], []
    for axis in range(3):
        column = unit[:, axis]
        world = int(np.argmax(np.abs(column)))
        others = np.delete(np.abs(column), world)
        if np.any(others > OFF_AXIS_TOLERANCE):
            raise NotAxisAligned(
                f"image axis {axis} points {np.round(column, 3).tolist()}, which is not along a world axis; "
                "this image would have to be resampled first")
        world_of_axis.append(world)
        signs.append(1.0 if column[world] >= 0 else -1.0)
    if sorted(world_of_axis) != [0, 1, 2]:
        raise NotAxisAligned("two image axes point along the same world axis")
    return tuple(world_of_axis), np.asarray(signs, dtype=float), spacing


def load_volume(path: str, dtype=None) -> Volume:
    """Read a NIfTI file into an engine Volume in RAS world coordinates.

    NIfTI's affine already maps voxel indices to RAS millimetres, so the
    work is to put the array on the engine's own axis order and direction.
    """
    import nibabel as nib

    image = nib.load(path)
    affine = np.asarray(image.affine, dtype=float)
    world_of_axis, signs, spacing = _axis_order(affine)

    array = np.asanyarray(image.dataobj)
    if dtype is not None:
        array = array.astype(dtype, copy=False)
    # The file's axes are (i, j, k); the engine wants (z, y, x) = world
    # (2, 1, 0), so move each image axis to where its world axis belongs.
    to_world = [world_of_axis.index(w) for w in (2, 1, 0)]
    array = np.transpose(array, to_world)
    flip = [n for n, w in enumerate((2, 1, 0)) if signs[world_of_axis.index(w)] < 0]
    if flip:
        array = np.flip(array, axis=flip)
    array = np.ascontiguousarray(array)

    # The origin is the world position of the engine's first voxel, which is
    # the image corner along each axis that now comes first.
    corner = affine[:3, 3].copy()
    shape = image.shape
    for axis, world in enumerate(world_of_axis):
        if signs[axis] < 0:  # that axis was flipped, so the far end is now first
            corner[world] += signs[axis] * spacing[axis] * (shape[axis] - 1)
    engine_spacing = tuple(float(spacing[world_of_axis.index(w)]) for w in (0, 1, 2))
    return Volume(array=array, spacing=engine_spacing, origin=tuple(float(v) for v in corner))
