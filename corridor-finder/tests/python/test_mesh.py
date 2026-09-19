import struct

import numpy as np

from corridor_engine.mesh import (
    decimate_mesh,
    extract_label_meshes,
    extract_mesh,
    write_stl_binary,
)
from corridor_engine.phantoms import pelvis_like
from corridor_engine.volume import Volume


def _sphere_mask(n=60, radius=20.0):
    zz, yy, xx = np.mgrid[0:n, 0:n, 0:n]
    c = n / 2.0
    d = np.sqrt((zz - c) ** 2 + (yy - c) ** 2 + (xx - c) ** 2)
    return d <= radius


def _triangle_area_total(vertices, faces):
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    return float(areas.sum())


def test_sphere_mesh_area_and_bounds():
    radius = 20.0
    mask = _sphere_mask(radius=radius)
    mesh = extract_mesh(mask, spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0))

    assert len(mesh.faces) > 1000

    bbox_min = mesh.vertices.min(axis=0)
    bbox_max = mesh.vertices.max(axis=0)
    span = bbox_max - bbox_min
    for s in span:
        assert abs(s - 2 * radius) < 3.0

    area = _triangle_area_total(mesh.vertices, mesh.faces)
    expected = 4.0 * np.pi * radius ** 2
    assert abs(area - expected) / expected < 0.20


def test_stl_binary_header_and_triangle_count(tmp_path):
    mask = _sphere_mask(n=40, radius=12.0)
    mesh = extract_mesh(mask, spacing=(1.0, 1.0, 1.0))
    path = tmp_path / "sphere.stl"
    write_stl_binary(mesh, path)

    data = path.read_bytes()
    n_faces = len(mesh.faces)
    assert len(data) == 84 + 50 * n_faces
    assert struct.unpack("<I", data[80:84])[0] == n_faces


def test_extract_label_meshes_covers_all_labels():
    labels, spacing = pelvis_like()
    vol = Volume(array=labels, spacing=spacing)
    meshes = extract_label_meshes(vol)

    present = set(int(v) for v in np.unique(labels) if v != 0)
    assert set(meshes.keys()) == present
    for mesh in meshes.values():
        assert len(mesh.faces) > 0


def test_decimate_reduces_faces_and_keeps_bounds():
    mask = _sphere_mask(n=60, radius=20.0)
    mesh = extract_mesh(mask, spacing=(1.0, 1.0, 1.0))
    original_faces = len(mesh.faces)

    target = 500
    decimated = decimate_mesh(mesh, target_faces=target)

    assert len(decimated.faces) < original_faces
    assert len(decimated.faces) <= target * 3

    orig_min = mesh.vertices.min(axis=0)
    orig_max = mesh.vertices.max(axis=0)
    dec_min = decimated.vertices.min(axis=0)
    dec_max = decimated.vertices.max(axis=0)
    assert np.all(np.abs(orig_min - dec_min) < 5.0)
    assert np.all(np.abs(orig_max - dec_max) < 5.0)


def test_stl_header_declares_ras_space(tmp_path):
    # Vertices are RAS. Slicer reads a binary STL without "SPACE=RAS" in its
    # header as LPS, which put an exported pelvis 180 degrees round the long
    # axis (y +28..+165 mm came back as -165..-28) when loaded back.
    path = tmp_path / "bones.stl"
    block = np.zeros((6, 6, 6), dtype=bool)
    block[1:5, 1:5, 1:5] = True
    write_stl_binary(extract_mesh(block, spacing=(1.0, 1.0, 1.0)), path)
    assert b"SPACE=RAS" in path.read_bytes()[:80]
