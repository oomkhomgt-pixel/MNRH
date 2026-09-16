import gzip
import json
import struct

import numpy as np

from corridor_engine.export_viewer import (
    assert_self_contained,
    build_payload,
    export_viewer,
)
from corridor_engine.mesh import extract_mesh


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


def test_payload_roundtrip_in_python():
    meshes = _small_meshes()
    plan = _small_plan()

    edt_uint8 = np.zeros((5, 6, 7), dtype=np.uint8)
    edt_uint8[:] = 3

    payload = build_payload(
        plan,
        meshes,
        edt_uint8=edt_uint8,
        edt_spacing=(1.0, 1.0, 1.0),
        edt_origin=(0.0, 0.0, 0.0),
    )

    raw = gzip.decompress(payload)
    header_len = struct.unpack("<I", raw[0:4])[0]
    header = json.loads(raw[4 : 4 + header_len].decode("utf-8"))

    assert header["version"] == 1
    assert len(header["meshes"]) == len(meshes)
    for entry in header["meshes"]:
        mesh = meshes[entry["label"]]
        assert entry["n_vertices"] == len(mesh.vertices)
        assert entry["n_faces"] == len(mesh.faces)

    assert header["edt"] is not None
    assert header["edt"]["shape"] == list(edt_uint8.shape)


def test_assert_self_contained_rejects_external_asset():
    html = '<html><head><meta name="robots" content="noindex"></head><body><script src="https://cdn.example.com/x.js"></script></body></html>'
    try:
        assert_self_contained(html)
        assert False, "expected ValueError"
    except ValueError:
        pass
