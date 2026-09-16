"""Surface mesh extraction, decimation, and STL export.

Meshes are stored with vertices in world xyz mm (matching the (x, y, z)
spacing/origin convention used by corridor_engine.volume.Volume), even
though the source masks are numpy arrays in ZYX order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import struct

from . import segmentation as seg


@dataclass
class Mesh:
    vertices: np.ndarray  # (V, 3) float32, world xyz mm
    faces: np.ndarray  # (F, 3) int32
    label: int = 0
    name: str = ""


def _laplacian_smooth(vertices: np.ndarray, faces: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0 or len(vertices) == 0:
        return vertices
    n = len(vertices)
    neighbors: List[set] = [set() for _ in range(n)]
    for f in faces:
        a, b, c = int(f[0]), int(f[1]), int(f[2])
        neighbors[a].update((b, c))
        neighbors[b].update((a, c))
        neighbors[c].update((a, b))
    verts = vertices.astype(np.float64).copy()
    for _ in range(iterations):
        new_verts = verts.copy()
        for i, nbrs in enumerate(neighbors):
            if not nbrs:
                continue
            nbr_arr = np.array(list(nbrs), dtype=np.int64)
            new_verts[i] = 0.5 * verts[i] + 0.5 * verts[nbr_arr].mean(axis=0)
        verts = new_verts
    return verts.astype(np.float32)


def extract_mesh(
    mask: np.ndarray,
    spacing,
    origin=(0.0, 0.0, 0.0),
    *,
    step_size: int = 1,
    smooth_iterations: int = 0,
    name: str = "",
    label: int = 0,
) -> Mesh:
    """Marching cubes surface of a boolean mask (array ZYX) into world xyz mm.

    ``spacing`` is (sx, sy, sz) mm, matching the Volume convention.
    """
    from skimage import measure

    sx, sy, sz = spacing
    ox, oy, oz = origin
    mask_arr = np.asarray(mask, dtype=bool)
    if mask_arr.sum() == 0:
        return Mesh(
            vertices=np.zeros((0, 3), dtype=np.float32),
            faces=np.zeros((0, 3), dtype=np.int32),
            label=label,
            name=name,
        )

    # marching_cubes expects ``spacing`` in the same axis order as the
    # array (z, y, x).
    verts_zyx, faces, _normals, _values = measure.marching_cubes(
        mask_arr.astype(np.float32),
        level=0.5,
        spacing=(sz, sy, sx),
        step_size=step_size,
    )

    if smooth_iterations > 0:
        verts_zyx = _laplacian_smooth(verts_zyx, faces, smooth_iterations)

    # verts_zyx columns are (z, y, x) mm offsets from the mask origin.
    z = verts_zyx[:, 0] + oz
    y = verts_zyx[:, 1] + oy
    x = verts_zyx[:, 2] + ox
    vertices = np.stack([x, y, z], axis=1).astype(np.float32)
    faces = faces.astype(np.int32)

    return Mesh(vertices=vertices, faces=faces, label=label, name=name)


def extract_label_meshes(labels_vol, labels: Optional[Iterable[int]] = None, **kw) -> Dict[int, Mesh]:
    """One Mesh per non-zero label present in ``labels_vol.array`` (or the
    explicitly given ``labels`` list). ``labels_vol`` is a Volume-like object
    with ``.array``, ``.spacing`` and ``.origin`` attributes.
    """
    array = labels_vol.array
    spacing = labels_vol.spacing
    origin = getattr(labels_vol, "origin", (0.0, 0.0, 0.0))

    if labels is None:
        present = sorted(int(v) for v in np.unique(array) if v != 0)
    else:
        present = list(labels)

    result: Dict[int, Mesh] = {}
    for label_id in present:
        mask = array == label_id
        name = seg.LABEL_NAMES.get(label_id, f"label_{label_id}")
        result[label_id] = extract_mesh(mask, spacing, origin, name=name, label=label_id, **kw)
    return result


def _estimate_cell_size(mesh: Mesh, target_faces: int) -> float:
    """Rough closed-form guess: assume decimated face count scales roughly
    like (bbox_volume / cell_size^3), pick a cell size to land near
    target_faces vertices worth of grid cells.
    """
    if len(mesh.vertices) == 0 or target_faces <= 0:
        return 1.0
    bbox_min = mesh.vertices.min(axis=0)
    bbox_max = mesh.vertices.max(axis=0)
    dims = np.maximum(bbox_max - bbox_min, 1e-6)
    bbox_volume = float(dims[0] * dims[1] * dims[2])
    # Aim for roughly target_faces/2 vertices (each interior vertex tends to
    # produce ~2 faces on a closed manifold surface).
    target_cells = max(target_faces / 2.0, 1.0)
    cell_size = (bbox_volume / target_cells) ** (1.0 / 3.0)
    return max(cell_size, 1e-3)


def _decimate_once(mesh: Mesh, cell_size: float) -> Mesh:
    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        return mesh

    verts = mesh.vertices
    bbox_min = verts.min(axis=0)
    grid_idx = np.floor((verts - bbox_min) / cell_size).astype(np.int64)

    # Map each grid cell to a single representative vertex (the centroid of
    # the vertices that fall in it).
    cell_keys, inverse = np.unique(grid_idx, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    n_cells = len(cell_keys)

    new_verts = np.zeros((n_cells, 3), dtype=np.float64)
    counts = np.zeros(n_cells, dtype=np.int64)
    np.add.at(new_verts, inverse, verts.astype(np.float64))
    np.add.at(counts, inverse, 1)
    new_verts /= counts[:, None]
    new_verts = new_verts.astype(np.float32)

    new_faces = inverse[mesh.faces.reshape(-1)].reshape(-1, 3).astype(np.int64)

    # Drop degenerate faces: repeated vertex index, or (near-)zero area.
    a, b, c = new_faces[:, 0], new_faces[:, 1], new_faces[:, 2]
    distinct = (a != b) & (b != c) & (a != c)
    new_faces = new_faces[distinct]
    if len(new_faces) > 0:
        v0 = new_verts[new_faces[:, 0]]
        v1 = new_verts[new_faces[:, 1]]
        v2 = new_verts[new_faces[:, 2]]
        cross = np.cross(v1 - v0, v2 - v0)
        area2 = np.sum(cross * cross, axis=1)
        new_faces = new_faces[area2 > 1e-12]

    # Drop duplicate faces (can arise after welding).
    if len(new_faces) > 0:
        sorted_faces = np.sort(new_faces, axis=1)
        _, unique_idx = np.unique(sorted_faces, axis=0, return_index=True)
        new_faces = new_faces[np.sort(unique_idx)]

    # Drop vertices no longer referenced by any face, remapping indices.
    if len(new_faces) > 0:
        used = np.unique(new_faces.reshape(-1))
        remap = -np.ones(n_cells, dtype=np.int64)
        remap[used] = np.arange(len(used))
        final_verts = new_verts[used]
        final_faces = remap[new_faces].astype(np.int32)
    else:
        final_verts = np.zeros((0, 3), dtype=np.float32)
        final_faces = np.zeros((0, 3), dtype=np.int32)

    return Mesh(vertices=final_verts, faces=final_faces, label=mesh.label, name=mesh.name)


def decimate_mesh(mesh: Mesh, target_faces: int) -> Mesh:
    """Vertex-clustering decimation, aiming near ``target_faces`` triangles."""
    if len(mesh.faces) <= target_faces or target_faces <= 0:
        return mesh

    cell_size = _estimate_cell_size(mesh, target_faces)
    result = _decimate_once(mesh, cell_size)

    # One adjustment pass if we badly overshot or undershot.
    attempts = 0
    while attempts < 4 and len(result.faces) > 0:
        ratio = len(result.faces) / float(target_faces)
        if 0.2 <= ratio <= 3.0:
            break
        if ratio > 3.0:
            cell_size *= (ratio ** (1.0 / 3.0)) * 1.05
        else:
            cell_size /= max((1.0 / ratio) ** (1.0 / 3.0), 1.01)
        result = _decimate_once(mesh, cell_size)
        attempts += 1

    return result


def _face_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    lengths = np.linalg.norm(n, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    return (n / lengths).astype(np.float32)


def write_stl_binary(mesh: Mesh, path, *, header: str = "MNRH Corridor Finder") -> None:
    write_stl_binary_multi([mesh], path, header=header)


def write_stl_binary_multi(meshes: Iterable[Mesh], path, *, header: str = "MNRH Corridor Finder") -> None:
    meshes = list(meshes)
    total_faces = sum(len(m.faces) for m in meshes)

    header_bytes = header.encode("utf-8")[:80]
    header_bytes = header_bytes + b"\x00" * (80 - len(header_bytes))

    with open(path, "wb") as fh:
        fh.write(header_bytes)
        fh.write(struct.pack("<I", total_faces))
        for mesh in meshes:
            if len(mesh.faces) == 0:
                continue
            normals = _face_normals(mesh.vertices, mesh.faces)
            for i, face in enumerate(mesh.faces):
                v0 = mesh.vertices[face[0]]
                v1 = mesh.vertices[face[1]]
                v2 = mesh.vertices[face[2]]
                n = normals[i]
                fh.write(struct.pack("<3f", *n))
                fh.write(struct.pack("<3f", *v0))
                fh.write(struct.pack("<3f", *v1))
                fh.write(struct.pack("<3f", *v2))
                fh.write(struct.pack("<H", 0))


def mesh_to_arrays(mesh: Mesh) -> Tuple[np.ndarray, np.ndarray]:
    """(flat float32 vertex array, flat uint32 face-index array)."""
    verts = np.asarray(mesh.vertices, dtype=np.float32).reshape(-1)
    faces = np.asarray(mesh.faces, dtype=np.uint32).reshape(-1)
    return verts, faces
