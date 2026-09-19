import gzip
import json
import struct

import numpy as np
import pytest

from corridor_engine import cortex
from corridor_engine.export_viewer import (
    assert_self_contained,
    build_payload,
    crop_box_for_screw,
    export_viewer,
)
from corridor_engine.mesh import extract_mesh
from corridor_engine.volume import Volume


def _sphere_mask(n=24, radius=8.0):
    zz, yy, xx = np.mgrid[0:n, 0:n, 0:n]
    c = n / 2.0
    d = np.sqrt((zz - c) ** 2 + (yy - c) ** 2 + (xx - c) ** 2)
    return d <= radius


def _small_plan():
    return {
        "schema": "mnrh-corridor-plan/1",
        "case_alias": "test-case",
        "software": {"name": "corridor-finder", "version": "test"},
        "disclaimer": "for testing only",
        "case": {},
        "frame": {},
        "landmarks": {},
        "screws": [
            {
                "screw_id": "s1",
                "corridor_id": "c1",
                "side": "left",
                "entry_xyz": [0.0, 0.0, 0.0],
                "target_xyz": [10.0, 10.0, 10.0],
                "diameter_mm": 6.0,
                "length_mm": 17.3,
                "margin_mm": 2.0,
            }
        ],
        "screw_library": {},
        "audit": [],
    }


def _small_meshes():
    mask = _sphere_mask()
    mesh = extract_mesh(mask, spacing=(1.0, 1.0, 1.0), name="sphere", label=1)
    return {1: mesh}


def test_exported_html_is_self_contained_and_small(tmp_path):
    plan = _small_plan()
    meshes = _small_meshes()

    out_path = tmp_path / "viewer.html"
    result = export_viewer(plan, meshes, out_path)

    assert result == out_path
    assert out_path.exists()

    html = out_path.read_text(encoding="utf-8")
    size = out_path.stat().st_size
    assert size < 8 * 1024 * 1024

    assert "https://" not in html
    assert "http://" not in html
    assert "noindex" in html
    assert 'id="plan"' in html
    assert 'id="payload"' in html


def _decode(payload):
    raw = gzip.decompress(payload)
    header_len = struct.unpack("<I", raw[0:4])[0]
    header = json.loads(raw[4 : 4 + header_len].decode("utf-8"))
    return header, raw[4 + header_len :]


def test_payload_roundtrip_in_python():
    meshes = _small_meshes()
    plan = _small_plan()
    edt = Volume(np.full((5, 6, 7), 3.0), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0))

    header, _body = _decode(build_payload(plan, meshes, screw_edts={"s1": edt}))

    assert header["version"] == 2
    assert len(header["meshes"]) == len(meshes)
    for entry in header["meshes"]:
        mesh = meshes[entry["label"]]
        assert entry["n_vertices"] == len(mesh.vertices)
        assert entry["n_faces"] == len(mesh.faces)
    assert [e["screw_id"] for e in header["edts"]] == ["s1"]


def _edt_like_field(shape=(60, 80, 100), seed=3):
    """Random values shaped like a distance field: 0 (not bone) or at least
    one voxel spacing."""
    field = np.random.default_rng(seed).uniform(-10.0, 30.0, size=shape)
    return np.where(field < 0.8, 0.0, field)


def test_each_screw_gets_its_own_field_cropped_on_grid_and_rounded_down():
    # The viewer must check each screw against the same field validate.py
    # used for it: the crop keeps the source grid (origin moves by whole
    # voxels), says where it sits in the CT-sized grid, and values are only
    # ever rounded down.
    spacing, origin = (0.8, 0.9, 1.25), (-40.0, 12.5, 101.0)
    field = _edt_like_field()
    edt = Volume(field, spacing, origin)
    plan = _small_plan()
    plan["screws"][0]["entry_xyz"] = [-10.0, 40.0, 130.0]
    plan["screws"][0]["target_xyz"] = [5.0, 45.0, 140.0]

    header, body = _decode(build_payload(plan, {}, screw_edts={"s1": edt}))
    e = header["edts"][0]
    assert e["full_shape"] == list(field.shape)
    assert e["full_origin"] == list(origin)
    i0, j0, k0 = e["index_offset"]
    assert np.allclose(np.array(e["origin"]), np.array(origin) + np.array([i0, j0, k0]) * np.array(spacing))
    nz, ny, nx = e["shape"]
    embedded = np.frombuffer(body[e["offset"] : e["offset"] + e["n_bytes"]], dtype=np.uint8).reshape(nz, ny, nx) * e["scale_mm"]
    source = np.minimum(field[k0 : k0 + nz, j0 : j0 + ny, i0 : i0 + nx], 25.5)
    assert np.all(embedded <= source + 1e-9)
    assert np.all(embedded >= source - e["scale_mm"] - 1e-9)
    assert np.array_equal(embedded > 0, source > 0)  # same bone mask


def test_crop_covers_what_validate_can_look_at():
    # A crossing is searched for up to MAX_SEARCH_MM beyond either handle and
    # checked for bone MAX_SEARCH_MM beyond itself; the exemption box reaches
    # box_half_mm around a crossing on that stretch.
    spacing, origin = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)
    edt = Volume(_edt_like_field((200, 200, 400)), spacing, origin)
    entry, target = np.array([150.0, 100.0, 100.0]), np.array([250.0, 100.0, 100.0])
    lo, hi = crop_box_for_screw(edt, entry, target, 7.3, 2.0)
    half = cortex.box_half_mm(3.65, 2.0, spacing)
    assert lo[0] <= 150 - 2 * cortex.MAX_SEARCH_MM - half and hi[0] >= 250 + 2 * cortex.MAX_SEARCH_MM + half
    assert lo[1] <= 100 - half and hi[1] >= 100 + half


def test_export_refuses_a_field_the_viewer_would_misread():
    # A bone value below one 0.1 mm step would read as "not bone" in the viewer.
    field = _edt_like_field()
    field[30, 40, 50] = 0.05
    edt = Volume(field, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0))
    plan = _small_plan()
    plan["screws"][0]["entry_xyz"] = [45.0, 35.0, 25.0]
    plan["screws"][0]["target_xyz"] = [55.0, 45.0, 35.0]
    with pytest.raises(ValueError, match="below"):
        build_payload(plan, {}, screw_edts={"s1": edt})


def test_export_viewer_rejects_phi(tmp_path):
    plan = _small_plan()
    plan["case"] = {"PatientName": "Jane Doe"}
    meshes = _small_meshes()

    out_path = tmp_path / "viewer.html"

    with pytest.raises(ValueError):
        export_viewer(plan, meshes, out_path)

    assert not out_path.exists()


def test_export_viewer_allows_check_phi_disabled(tmp_path):
    plan = _small_plan()
    plan["case"] = {"PatientName": "Jane Doe"}
    meshes = _small_meshes()

    out_path = tmp_path / "viewer.html"

    result = export_viewer(plan, meshes, out_path, check_phi=False)

    assert result == out_path
    assert out_path.exists()


def test_assert_self_contained_rejects_external_asset():
    html = '<html><head><meta name="robots" content="noindex"></head><body><script src="https://cdn.example.com/x.js"></script></body></html>'
    try:
        assert_self_contained(html)
        assert False, "expected ValueError"
    except ValueError:
        pass
