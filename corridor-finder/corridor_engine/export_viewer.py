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

import numpy as np

from . import phi
from .edt import VIEWER_EDT_SCALE_MM, quantize_edt_floor
from .mesh import Mesh, mesh_to_arrays
from .volume import Volume

MAX_OUTPUT_BYTES = 8 * 1024 * 1024

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_VIEWER_DIR = _PACKAGE_ROOT / "viewer"


def _plan_to_dict(plan) -> dict:
    if hasattr(plan, "to_dict"):
        return plan.to_dict()
    return dict(plan)


# How far around a screw's axis (mm) its distance field is embedded, which
# bounds how far a handle can be dragged in the viewer and still be checked.
VIEWER_EDT_MARGIN_MM = 30.0


def crop_edt_for_screw(edt_vol: Volume, entry_xyz, target_xyz, margin_mm: float = VIEWER_EDT_MARGIN_MM) -> Volume:
    """The part of a screw's distance field within ``margin_mm`` of the box
    spanned by its entry and target. The crop is aligned to the source grid,
    so every embedded value is exactly the one validate.py samples."""
    pts = np.array([entry_xyz, target_xyz], dtype=float)
    lo = np.floor(edt_vol.world_to_ijk(pts.min(axis=0) - margin_mm)).astype(int)
    hi = np.ceil(edt_vol.world_to_ijk(pts.max(axis=0) + margin_mm)).astype(int)
    nz, ny, nx = edt_vol.array.shape
    lo = np.maximum(lo, 0)
    hi = np.minimum(hi, np.array([nx, ny, nz]) - 1)
    if np.any(hi < lo):  # the screw lies entirely outside the CT
        return Volume(np.zeros((1, 1, 1)), edt_vol.spacing, tuple(edt_vol.ijk_to_world((0, 0, 0))))
    sub = edt_vol.array[lo[2]:hi[2] + 1, lo[1]:hi[1] + 1, lo[0]:hi[0] + 1]
    return Volume(sub, edt_vol.spacing, tuple(float(v) for v in edt_vol.ijk_to_world(lo)))


def build_payload(plan, meshes: Dict[int, Mesh], *, screw_edts: Optional[Dict[str, Volume]] = None) -> bytes:
    """Pack meshes and, per screw, the distance field validate.py uses for
    that screw into a gzip blob.

    Layout (before gzip):
      [4 bytes little-endian uint32 header_length]
      [header_length bytes of UTF-8 JSON header]
      [raw payload bytes: for each mesh in order, float32 vertices then
       uint32 faces; then each screw's distance field as uint8 steps of
       scale_mm (C order), cropped around the screw and rounded down]
    """
    header_meshes = []
    raw_chunks = []
    offset = 0
    for label_id, mesh in meshes.items():
        verts, faces = mesh_to_arrays(mesh)
        header_meshes.append(
            {
                "label": int(label_id),
                "name": mesh.name,
                "n_vertices": int(len(mesh.vertices)),
                "n_faces": int(len(mesh.faces)),
                "offset": offset,
            }
        )
        raw_chunks += [verts.tobytes(), faces.tobytes()]
        offset += len(raw_chunks[-2]) + len(raw_chunks[-1])

    header_edts = []
    screws = {s["screw_id"]: s for s in _plan_to_dict(plan).get("screws", [])}
    for screw_id, edt_vol in (screw_edts or {}).items():
        screw = screws[screw_id]
        crop = crop_edt_for_screw(edt_vol, screw["entry_xyz"], screw["target_xyz"])
        data = quantize_edt_floor(crop.array, VIEWER_EDT_SCALE_MM).tobytes(order="C")
        header_edts.append(
            {
                "screw_id": screw_id,
                "shape": list(crop.array.shape),
                "spacing": [float(v) for v in crop.spacing],
                "origin": [float(v) for v in crop.origin],
                "scale_mm": VIEWER_EDT_SCALE_MM,
                "offset": offset,
                "n_bytes": len(data),
            }
        )
        raw_chunks.append(data)
        offset += len(data)

    header_bytes = json.dumps({"version": 2, "meshes": header_meshes, "edts": header_edts}).encode("utf-8")
    body = bytearray(struct.pack("<I", len(header_bytes)))
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
    screw_edts: Optional[Dict[str, Volume]] = None,
    template_dir: Optional[Path] = None,
    title: str = "Corridor Finder plan",
    check_phi: bool = True,
) -> Path:
    """Write the self-contained viewer. ``screw_edts`` maps each screw id to
    the distance field (mm) that validate.py checks that screw against; a
    screw without one is shown as not checked, never as safe."""
    if check_phi:
        phi.assert_no_phi(_plan_to_dict(plan))

    viewer_dir = Path(template_dir) if template_dir is not None else _DEFAULT_VIEWER_DIR

    template_html = (viewer_dir / "template.html").read_text(encoding="utf-8")
    style_css = (viewer_dir / "style.css").read_text(encoding="utf-8")
    app_js = (viewer_dir / "app.js").read_text(encoding="utf-8")
    modules = {
        "three": (viewer_dir / "vendor" / "three.module.min.js").read_bytes(),
        "clearance": (viewer_dir / "clearance.js").read_bytes(),
    }
    importmap = (
        '<script type="importmap">'
        + json.dumps(
            {"imports": {name: "data:text/javascript;base64," + base64.b64encode(src).decode("ascii") for name, src in modules.items()}}
        )
        + "</script>"
    )

    payload_bytes = build_payload(plan, meshes, screw_edts=screw_edts)
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
