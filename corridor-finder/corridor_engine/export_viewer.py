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

from . import cortex, phi
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


# How far (mm) the viewer can follow a dragged handle and still check the
# screw exactly: each crop covers everything validate.py can look at for the
# screw as exported, plus this much in every direction. Beyond it the viewer
# says "not checked".
VIEWER_DRAG_MM = 15.0


def crop_box_for_screw(edt_vol: Volume, entry_xyz, target_xyz, diameter_mm: float, margin_mm: float):
    """(lo, hi) voxel indices (x, y, z; inclusive, clipped to the CT) of the
    part of a screw's distance field validate.py can look at: its axis
    extended by twice cortex.MAX_SEARCH_MM beyond both handles (a crossing
    is searched for up to that far from a handle, and checked for bone that
    far beyond it; a far-cortex tip lies within), widened by the exemption
    box (cortex.box_half_mm, which also covers the cortex normal) plus
    VIEWER_DRAG_MM."""
    entry = np.asarray(entry_xyz, dtype=float)
    target = np.asarray(target_xyz, dtype=float)
    u = cortex.unit3(target - entry)
    reach_axis = 2.0 * cortex.MAX_SEARCH_MM
    ends = np.array([entry - reach_axis * u, target + reach_axis * u])
    reach = cortex.box_half_mm(diameter_mm / 2.0, margin_mm, edt_vol.spacing) + VIEWER_DRAG_MM
    lo = np.floor(edt_vol.world_to_ijk(ends.min(axis=0) - reach)).astype(int)
    hi = np.ceil(edt_vol.world_to_ijk(ends.max(axis=0) + reach)).astype(int)
    nz, ny, nx = edt_vol.array.shape
    return np.maximum(lo, 0), np.minimum(hi, np.array([nx, ny, nz]) - 1)


def crop_edt_for_screw(edt_vol: Volume, entry_xyz, target_xyz, diameter_mm: float, margin_mm: float):
    """The part of a screw's distance field the viewer needs (see
    crop_box_for_screw), aligned to the source grid so every embedded value
    is exactly one validate.py samples. Returns (crop, index offset (i, j, k)
    of the crop's first voxel in the full grid); the crop is empty when the
    screw is nowhere near the CT."""
    lo, hi = crop_box_for_screw(edt_vol, entry_xyz, target_xyz, diameter_mm, margin_mm)
    size = np.maximum(hi - lo + 1, 0)
    sub = edt_vol.array[lo[2]:lo[2] + size[2], lo[1]:lo[1] + size[1], lo[0]:lo[0] + size[0]]
    return Volume(sub, edt_vol.spacing, tuple(float(v) for v in edt_vol.ijk_to_world(lo))), tuple(int(v) for v in lo)


def screw_field_header(screw_id: str, edt_vol: Volume, crop: Volume, index_offset) -> dict:
    """What viewer/clearance.js needs to know about a screw's field besides
    its bytes: the crop and where it sits in the CT-sized grid."""
    return {
        "screw_id": screw_id,
        "shape": list(crop.array.shape),
        "spacing": [float(v) for v in crop.spacing],
        "origin": [float(v) for v in crop.origin],
        "full_origin": [float(v) for v in edt_vol.origin],
        "full_shape": list(edt_vol.array.shape),
        "index_offset": [int(v) for v in index_offset],
        "scale_mm": VIEWER_EDT_SCALE_MM,
    }


def quantized_screw_field(screw_id: str, crop: Volume) -> np.ndarray:
    """The crop in the viewer's uint8 steps. The viewer reads bone as
    "steps > 0", so a bone value below one step would change its bone mask
    (a real distance field is 0 or at least one voxel spacing): refuse."""
    q = quantize_edt_floor(crop.array, VIEWER_EDT_SCALE_MM)
    if not np.array_equal(q > 0, crop.array > 0):
        raise ValueError(f"screw {screw_id}: distance field has bone values below {VIEWER_EDT_SCALE_MM} mm")
    return q


def build_payload(plan, meshes: Dict[int, Mesh], *, screw_edts: Optional[Dict[str, Volume]] = None) -> bytes:
    """Pack meshes and, per screw, the distance field validate.py uses for
    that screw into a gzip blob.

    Layout (before gzip):
      [4 bytes little-endian uint32 header_length]
      [header_length bytes of UTF-8 JSON header]
      [raw payload bytes: for each mesh in order, float32 vertices then
       uint32 faces; then each screw's distance field as uint8 steps of
       scale_mm (C order), cropped around the screw and rounded down; its
       header entry says where the crop sits in the CT-sized grid]
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
        crop, index_offset = crop_edt_for_screw(edt_vol, screw["entry_xyz"], screw["target_xyz"], screw["diameter_mm"], screw["margin_mm"])
        data = quantized_screw_field(screw_id, crop).tobytes(order="C")
        header_edts.append({**screw_field_header(screw_id, edt_vol, crop, index_offset), "offset": offset, "n_bytes": len(data)})
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
