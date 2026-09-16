"""Export a single self-contained HTML file: an interactive 3D viewer for a
plan plus its bone meshes and (optionally) the coarse EDT volume, with no
external network dependencies (three.js is inlined as a data: URI).
"""
from __future__ import annotations

import base64
import gzip
import json
import struct
from pathlib import Path
from typing import Dict, Optional

from .mesh import Mesh, mesh_to_arrays

MAX_OUTPUT_BYTES = 8 * 1024 * 1024

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_VIEWER_DIR = _PACKAGE_ROOT / "viewer"


def _plan_to_dict(plan) -> dict:
    if hasattr(plan, "to_dict"):
        return plan.to_dict()
    return dict(plan)


def build_payload(
    plan,
    meshes: Dict[int, Mesh],
    *,
    edt_uint8=None,
    edt_spacing=None,
    edt_origin=None,
) -> bytes:
    """Pack meshes (and optionally a quantized EDT volume) into a gzip blob.

    Layout (before gzip):
      [4 bytes little-endian uint32 header_length]
      [header_length bytes of UTF-8 JSON header]
      [raw payload bytes: for each mesh in order, float32 vertices then
       uint32 faces; then, if edt_uint8 is given, its raw bytes (C order)]
    """
    mesh_items = list(meshes.items())

    header_meshes = []
    raw_chunks = []
    offset = 0
    for label_id, mesh in mesh_items:
        verts, faces = mesh_to_arrays(mesh)
        n_vertices = len(mesh.vertices)
        n_faces = len(mesh.faces)
        header_meshes.append(
            {
                "label": int(label_id),
                "name": mesh.name,
                "n_vertices": int(n_vertices),
                "n_faces": int(n_faces),
                "offset": offset,
            }
        )
        vert_bytes = verts.tobytes()
        face_bytes = faces.tobytes()
        raw_chunks.append(vert_bytes)
        raw_chunks.append(face_bytes)
        offset += len(vert_bytes) + len(face_bytes)

    edt_header = None
    if edt_uint8 is not None:
        edt_bytes = edt_uint8.tobytes(order="C")
        edt_header = {
            "shape": list(edt_uint8.shape),
            "spacing": list(edt_spacing) if edt_spacing is not None else None,
            "origin": list(edt_origin) if edt_origin is not None else None,
            "offset": offset,
            "n_bytes": len(edt_bytes),
        }
        raw_chunks.append(edt_bytes)
        offset += len(edt_bytes)

    header = {
        "version": 1,
        "meshes": header_meshes,
        "edt": edt_header,
    }
    header_bytes = json.dumps(header).encode("utf-8")

    body = bytearray()
    body += struct.pack("<I", len(header_bytes))
    body += header_bytes
    for chunk in raw_chunks:
        body += chunk

    return gzip.compress(bytes(body))


def assert_self_contained(html: str) -> None:
    """Raise ValueError if the page references any external network asset."""
    import re

    for attr in ("src", "href"):
        for match in re.finditer(rf'{attr}\s*=\s*["\']([^"\']*)["\']', html):
            value = match.group(1)
            if value.startswith("http://") or value.startswith("https://"):
                raise ValueError(
                    f"external {attr!r} reference found: {value!r} "
                    "(viewer export must be fully self-contained)"
                )

    if not re.search(
        r'<meta[^>]*name=["\']robots["\'][^>]*content=["\'][^"\']*noindex',
        html,
        re.IGNORECASE,
    ):
        raise ValueError("missing <meta name=\"robots\" content=\"noindex\"> tag")


def export_viewer(
    plan,
    meshes: Dict[int, Mesh],
    path,
    *,
    edt_uint8=None,
    edt_spacing=None,
    edt_origin=None,
    template_dir: Optional[Path] = None,
    title: str = "Corridor Finder plan",
) -> Path:
    viewer_dir = Path(template_dir) if template_dir is not None else _DEFAULT_VIEWER_DIR

    template_html = (viewer_dir / "template.html").read_text(encoding="utf-8")
    style_css = (viewer_dir / "style.css").read_text(encoding="utf-8")
    app_js = (viewer_dir / "app.js").read_text(encoding="utf-8")
    three_js_bytes = (viewer_dir / "vendor" / "three.module.min.js").read_bytes()

    three_b64 = base64.b64encode(three_js_bytes).decode("ascii")
    importmap = (
        '<script type="importmap">'
        + json.dumps(
            {"imports": {"three": f"data:text/javascript;base64,{three_b64}"}}
        )
        + "</script>"
    )

    payload_bytes = build_payload(
        plan, meshes, edt_uint8=edt_uint8, edt_spacing=edt_spacing, edt_origin=edt_origin
    )
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")

    plan_dict = _plan_to_dict(plan)
    plan_json = json.dumps(plan_dict)

    html = template_html
    html = html.replace("{{TITLE}}", title)
    html = html.replace("{{STYLE}}", style_css)
    html = html.replace("{{IMPORTMAP}}", importmap)
    html = html.replace("{{APP_JS}}", app_js)
    html = html.replace("{{PLAN_JSON}}", plan_json)
    html = html.replace("{{PAYLOAD_B64}}", payload_b64)

    assert_self_contained(html)

    encoded = html.encode("utf-8")
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise ValueError(
            f"exported viewer is {len(encoded)} bytes, exceeds MAX_OUTPUT_BYTES={MAX_OUTPUT_BYTES}"
        )

    out_path = Path(path)
    out_path.write_text(html, encoding="utf-8")
    return out_path
