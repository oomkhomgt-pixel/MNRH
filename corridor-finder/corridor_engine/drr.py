"""Digitally-reconstructed-radiograph (DRR) rendering for corridor views.

Renders parallel-projection DRRs of an HU volume for a fixed set of named
view angles (AP, lateral, inlet, outlet, obliques, ...) defined in
``corridors.json``'s ``views_deg`` key. Also provides simple 2D overlay
helpers (projecting a 3D point onto a rendered view, drawing a planned
screw trajectory) and a dependency-light PNG writer.

Geometry convention
--------------------
A view is defined by two rotations applied to the *world* frame:

- ``rotate_x_deg``: rotation about the world x axis
- ``rotate_z_deg``: rotation about the world z axis (applied first)

``view_rotation`` returns the 3x3 matrix ``R`` such that ``v_view = R @
v_world`` maps a world vector into the view frame, where the view frame's
axes are (row-image-x, row-image-y, ray/beam). Concretely we treat the
view's local +x as the detector's "column" direction, local +y as the
detector's "row" direction (pointing down the image, i.e. increasing row
index goes "up" the patient unless flipped), and local +z as the ray
(projection) direction -- the volume is summed along this axis.

The DRR image is produced by resampling the HU volume onto a grid aligned
with the view frame (via ``scipy.ndimage.affine_transform``) and summing
along the ray axis, so ``project_point`` -- which maps a world point to
pixel coordinates via a pure dot product against ``u_hat``/``v_hat``/
``origin_mm`` -- is guaranteed to agree with what actually got rendered.
"""
from __future__ import annotations

import json
import os
import struct
import zlib
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import numpy as np
from scipy.ndimage import affine_transform

MNRH_ORANGE = (242, 142, 19)  # #F28E13


@dataclass
class DrrView:
    name: str
    rotate_x_deg: float
    rotate_z_deg: float
    image: np.ndarray  # float32 (H, W) in [0, 1], bone bright on dark field
    origin_mm: tuple  # world xyz of pixel (0, 0) corner on the detector plane
    u_hat: np.ndarray  # unit world vector along +column (image x)
    v_hat: np.ndarray  # unit world vector along +row (image y)
    pixel_mm: float


def _rotation_x(deg: float) -> np.ndarray:
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)


def _rotation_z(deg: float) -> np.ndarray:
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


def view_rotation(rotate_x_deg: float, rotate_z_deg: float) -> np.ndarray:
    """3x3 world->view rotation matrix.

    Applies the z rotation first, then the x rotation, matching the naming
    order (rotate_x, rotate_z) as sequential intrinsic rotations of the
    world frame: ``R = Rx(rotate_x_deg) @ Rz(rotate_z_deg)``.
    """
    return _rotation_x(rotate_x_deg) @ _rotation_z(rotate_z_deg)


def load_views(corridors_json_path: Optional[str] = None) -> Dict[str, Tuple[float, float]]:
    """Return {name: (rotate_x_deg, rotate_z_deg)} from corridors.json's views_deg."""
    if corridors_json_path is None:
        corridors_json_path = os.path.join(os.path.dirname(__file__), "..", "corridors.json")
    with open(corridors_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    views = {}
    for name, spec in data["views_deg"].items():
        views[name] = (float(spec["rotate_x"]), float(spec["rotate_z"]))
    return views


def _volume_center_world(hu_vol) -> np.ndarray:
    nz, ny, nx = hu_vol.array.shape
    # center in ijk (x, y, z) space, converted to world via ijk_to_world
    return hu_vol.ijk_to_world(((nx - 1) / 2.0, (ny - 1) / 2.0, (nz - 1) / 2.0))


def render_view(
    hu_vol,
    rotate_x_deg: float,
    rotate_z_deg: float,
    *,
    name: str = "",
    pixel_mm: float = 1.0,
    hu_clip: Tuple[float, float] = (-200.0, 2000.0),
    attenuation_k: float = 2.5e-4,
    percentiles: Tuple[float, float] = (1.0, 99.5),
) -> DrrView:
    """Render a parallel-projection DRR of ``hu_vol`` for the given view angles."""
    R = view_rotation(rotate_x_deg, rotate_z_deg)  # world -> view: v_view = R @ v_world
    # We need the view-frame basis vectors expressed in WORLD coordinates,
    # i.e. the world vector w such that R @ w = e_k (the k-th view axis).
    # Since R is a rotation matrix (orthogonal), R^{-1} = R^T, so
    # w = R^T @ e_k = the k-th ROW of R (as a column vector). Concretely:
    # the world vector that maps to view +x is ROW 0 of R, not column 0.
    u_hat = R[0, :].copy()  # world vector that maps to view +x (column dir)
    v_hat = R[1, :].copy()  # world vector that maps to view +y (row dir)
    ray_hat = R[2, :].copy()  # world vector that maps to view +z (ray/beam dir)

    sx, sy, sz = hu_vol.spacing
    nz, ny, nx = hu_vol.array.shape
    center_world = _volume_center_world(hu_vol)

    # Physical extents of the volume along each world axis (approximate,
    # using the axis-aligned bounding box) to size the view-aligned grid
    # generously enough to contain the rotated volume.
    extent_x = nx * sx
    extent_y = ny * sy
    extent_z = nz * sz
    diag = np.sqrt(extent_x ** 2 + extent_y ** 2 + extent_z ** 2)

    n_u = max(2, int(np.ceil(diag / pixel_mm)))
    n_v = max(2, int(np.ceil(diag / pixel_mm)))
    n_ray = max(2, int(np.ceil(diag / pixel_mm)))

    # World position of the (0, 0, 0) corner of the view-aligned grid: the
    # corner such that grid index (0,0,0) is farthest in the -u,-v,-ray
    # direction from the volume center.
    half_u = (n_u - 1) / 2.0 * pixel_mm
    half_v = (n_v - 1) / 2.0 * pixel_mm
    half_ray = (n_ray - 1) / 2.0 * pixel_mm
    corner_world = center_world - half_u * u_hat - half_v * v_hat - half_ray * ray_hat

    # affine_transform maps output index -> input index via:
    #   input_index = matrix @ output_index + offset
    # Output grid axes are (u_idx, v_idx, ray_idx); output array shape
    # (n_u, n_v, n_ray) will be built, then we transpose/sum as needed.
    # World point for output index (a, b, c):
    #   world = corner_world + a*pixel_mm*u_hat + b*pixel_mm*v_hat + c*pixel_mm*ray_hat
    # Convert that world point to input array (k, j, i) = (z_idx, y_idx, x_idx)
    # via hu_vol.world_to_ijk (gives i, j, k) then reorder.
    ox, oy, oz = hu_vol.origin

    # Build the 3x3 matrix mapping (a, b, c) -> (k, j, i) input index deltas,
    # plus the offset for output index (0,0,0).
    basis_world = np.stack([u_hat, v_hat, ray_hat], axis=1) * pixel_mm  # (3,3), columns are world deltas per output-index unit
    # world delta -> ijk delta (i=x/sx, j=y/sy, k=z/sz)
    inv_spacing = np.array([1.0 / sx, 1.0 / sy, 1.0 / sz])
    ijk_basis = basis_world * inv_spacing[:, None]  # rows: i,j,k ; cols: a,b,c
    # reorder rows to k,j,i for array indexing
    kji_basis = ijk_basis[[2, 1, 0], :]

    corner_ijk = hu_vol.world_to_ijk(corner_world)  # (i, j, k)
    corner_kji = np.array([corner_ijk[2], corner_ijk[1], corner_ijk[0]])

    matrix = kji_basis  # (3,3)
    offset = corner_kji

    output_shape = (n_u, n_v, n_ray)
    resampled = affine_transform(
        hu_vol.array,
        matrix=matrix,
        offset=offset,
        output_shape=output_shape,
        order=1,
        cval=hu_clip[0],
        prefilter=False,
    )

    clipped = np.clip(resampled, hu_clip[0], hu_clip[1]) - hu_clip[0]
    proj = clipped.sum(axis=2)  # sum along ray axis -> shape (n_u, n_v)

    attenuated = 1.0 - np.exp(-attenuation_k * proj)

    lo, hi = np.percentile(attenuated, percentiles)
    if hi <= lo:
        hi = lo + 1e-6
    normed = np.clip((attenuated - lo) / (hi - lo), 0.0, 1.0)

    # Bone has higher HU -> higher `proj` -> higher `attenuated` -> higher
    # `normed`. We want bone BRIGHT, so `normed` is used as-is.
    image = normed

    # image array is indexed [u_idx, v_idx]; convention: image[row, col] so
    # transpose to (n_v, n_u) = (row=v, col=u).
    image_hw = np.transpose(image, (1, 0)).astype(np.float32)

    return DrrView(
        name=name,
        rotate_x_deg=rotate_x_deg,
        rotate_z_deg=rotate_z_deg,
        image=image_hw,
        origin_mm=tuple(corner_world.tolist()),
        u_hat=u_hat,
        v_hat=v_hat,
        pixel_mm=pixel_mm,
    )


def project_point(view: DrrView, xyz_world) -> Tuple:
    """Project world point(s) onto the view's pixel grid.

    Accepts a single (3,) point or an (N, 3) array. Returns (column, row)
    as floats, or an (N, 2) array of (column, row) for multiple points.
    """
    pts = np.asarray(xyz_world, dtype=float)
    single = pts.ndim == 1
    pts2 = np.atleast_2d(pts)
    origin = np.asarray(view.origin_mm, dtype=float)
    rel = pts2 - origin[None, :]
    col = rel @ view.u_hat / view.pixel_mm
    row = rel @ view.v_hat / view.pixel_mm
    out = np.stack([col, row], axis=1)
    if single:
        return (float(out[0, 0]), float(out[0, 1]))
    return out


def render_corridor_views(hu_vol, view_names: Iterable[str], **kw) -> Dict[str, DrrView]:
    """Render several named views, looking up angles via ``load_views``."""
    views = load_views(kw.pop("corridors_json_path", None))
    result = {}
    for name in view_names:
        rx, rz = views[name]
        result[name] = render_view(hu_vol, rx, rz, name=name, **kw)
    return result


def _bresenham_ish_line_mask(shape, p0, p1, width_px: float) -> np.ndarray:
    """Boolean mask, True within ``width_px/2`` of the segment p0-p1 (col,row)."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = (x1 - x0), (y1 - y0)
    seg_len2 = dx * dx + dy * dy
    if seg_len2 < 1e-9:
        dist2 = (xx - x0) ** 2 + (yy - y0) ** 2
    else:
        t = ((xx - x0) * dx + (yy - y0) * dy) / seg_len2
        t = np.clip(t, 0.0, 1.0)
        proj_x = x0 + t * dx
        proj_y = y0 + t * dy
        dist2 = (xx - proj_x) ** 2 + (yy - proj_y) ** 2
    return dist2 <= (width_px / 2.0) ** 2


def draw_screw(view: DrrView, entry_xyz, target_xyz, *, width_px: float = 3.0, value: float = 1.0) -> np.ndarray:
    """Return an RGB uint8 overlay: greyscale DRR + orange screw axis + scale bar."""
    img = np.clip(view.image, 0.0, 1.0)
    h, w = img.shape
    grey = (img * 255.0).astype(np.uint8)
    rgb = np.stack([grey, grey, grey], axis=-1).astype(np.uint8)

    p0 = project_point(view, entry_xyz)
    p1 = project_point(view, target_xyz)
    mask = _bresenham_ish_line_mask((h, w), p0, p1, width_px)
    orange = np.array(MNRH_ORANGE, dtype=np.uint8)
    rgb[mask] = (orange.astype(float) * value + rgb[mask].astype(float) * (1.0 - value)).astype(np.uint8)

    # 50mm scale bar, bottom-left, with a small margin.
    bar_len_px = max(1, int(round(50.0 / view.pixel_mm)))
    margin = max(4, int(0.02 * min(h, w)))
    bar_row0 = max(0, h - margin - 3)
    bar_row1 = min(h, bar_row0 + 3)
    bar_col0 = margin
    bar_col1 = min(w, bar_col0 + bar_len_px)
    if bar_row1 > bar_row0 and bar_col1 > bar_col0:
        rgb[bar_row0:bar_row1, bar_col0:bar_col1] = np.array([255, 255, 255], dtype=np.uint8)

    return rgb


def _write_png_minimal(path: str, arr: np.ndarray) -> None:
    """Minimal pure-Python PNG writer (zlib + struct), no external deps."""
    if arr.ndim == 2:
        h, w = arr.shape
        color_type = 0  # greyscale
        channels = 1
        data8 = arr
    else:
        h, w, c = arr.shape
        assert c == 3
        color_type = 2  # RGB
        channels = 3
        data8 = arr

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)

    raw = bytearray()
    for row in range(h):
        raw.append(0)  # filter type: none
        raw.extend(data8[row].astype(np.uint8).tobytes())
    compressed = zlib.compress(bytes(raw), 9)

    with open(path, "wb") as f:
        f.write(sig)
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", compressed))
        f.write(chunk(b"IEND", b""))


def write_png(path, image: np.ndarray, *, invert: bool = False) -> None:
    """Write a float [0,1] (H,W) greyscale image or a uint8 (H,W,3) RGB image."""
    arr = np.asarray(image)
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0.0, 1.0)
        if invert:
            arr = 1.0 - arr
        arr8 = (arr * 255.0).round().astype(np.uint8)
    else:
        arr8 = arr
        if invert and arr8.ndim == 2:
            arr8 = 255 - arr8

    try:
        from PIL import Image

        if arr8.ndim == 2:
            im = Image.fromarray(arr8, mode="L")
        else:
            im = Image.fromarray(arr8, mode="RGB")
        im.save(path)
    except ImportError:
        _write_png_minimal(str(path), arr8)
