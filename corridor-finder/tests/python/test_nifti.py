import itertools

import numpy as np
import pytest

from corridor_engine.nifti import NotAxisAligned, load_volume

nib = pytest.importorskip("nibabel", reason="nibabel is a development dependency (requirements-dev.txt)")


def _write(tmp_path, array_ijk, affine, name="case.nii.gz"):
    path = tmp_path / name
    nib.save(nib.Nifti1Image(array_ijk, affine), str(path))
    return str(path)


def _affine(order, signs, spacing, corner):
    """A NIfTI affine whose image axes run along the given world axes."""
    affine = np.zeros((4, 4))
    affine[3, 3] = 1.0
    for axis, (world, sign, step) in enumerate(zip(order, signs, spacing)):
        affine[world, axis] = sign * step
    affine[:3, 3] = corner
    return affine


def test_every_axis_aligned_layout_lands_in_the_same_place(tmp_path):
    """The same block of bone, written out in all 48 axis-aligned layouts,
    must read back as the same world geometry. A CT arrives in whatever
    layout the scanner used, and getting this wrong mirrors the patient."""
    spacing = (0.8, 0.9, 1.1)  # along world x, y, z
    shape_world = (7, 5, 3)  # x, y, z
    corner = np.array([10.0, -20.0, 300.0])

    # The block, in world index space (x, y, z), marked so any flip shows.
    world = np.zeros(shape_world, dtype=np.int16)
    world[1, 0, 0] = 1
    world[0, 2, 0] = 2
    world[0, 0, 1] = 3

    for order in itertools.permutations((0, 1, 2)):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            # Lay the world array out on this file's axes.
            array = np.transpose(world, order)
            flips = [axis for axis, sign in enumerate(signs) if sign < 0]
            array_ijk = np.flip(array, axis=flips) if flips else array
            file_spacing = [spacing[world_axis] for world_axis in order]
            file_corner = corner.copy()
            for axis, (world_axis, sign) in enumerate(zip(order, signs)):
                if sign < 0:  # the file starts at the far end of that axis
                    file_corner[world_axis] += spacing[world_axis] * (shape_world[world_axis] - 1)
            path = _write(tmp_path, np.ascontiguousarray(array_ijk),
                          _affine(order, signs, file_spacing, file_corner), name=f"{order}{signs}.nii.gz")

            vol = load_volume(path)
            assert vol.array.shape == (shape_world[2], shape_world[1], shape_world[0])
            # NIfTI stores its affine in single precision, so a micrometre
            # of slack; anything clinical is far above that.
            assert vol.spacing == pytest.approx(spacing, abs=1e-3)
            assert vol.origin == pytest.approx(tuple(corner), abs=1e-3)
            # And every marked voxel is at the world position it started at.
            for marker, (x, y, z) in ((1, (1, 0, 0)), (2, (0, 2, 0)), (3, (0, 0, 1))):
                assert vol.array[z, y, x] == marker, f"{order} {signs}"


def test_an_oblique_image_is_refused_rather_than_resampled(tmp_path):
    affine = np.eye(4)
    affine[:3, :3] = np.array([[0.9, 0.3, 0.0], [-0.3, 0.9, 0.0], [0.0, 0.0, 1.0]])
    path = _write(tmp_path, np.zeros((4, 4, 4), dtype=np.int16), affine)
    with pytest.raises(NotAxisAligned):
        load_volume(path)


def test_the_array_is_the_files_own_values(tmp_path):
    array = (np.arange(2 * 3 * 4).reshape(2, 3, 4) - 500).astype(np.int16)
    path = _write(tmp_path, array, _affine((0, 1, 2), (1.0, 1.0, 1.0), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)))
    vol = load_volume(path)
    assert vol.array.dtype == array.dtype
    assert int(vol.array.min()) == int(array.min()) and int(vol.array.max()) == int(array.max())
