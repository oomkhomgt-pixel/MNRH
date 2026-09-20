"""Digitally-reconstructed-radiograph (DRR) rendering for corridor views.

Renders parallel-projection DRRs of an HU volume for a fixed set of named
view angles (AP, lateral, inlet, outlet, obliques, ...) defined in
``corridors.json``'s ``views_deg`` key. Also provides simple 2D overlay
helpers (projecting a 3D point onto a rendered view, drawing a planned
screw trajectory) and a dependency-light PNG writer.

Geometry convention
--------------------
World coordinates are RAS (x = patient right, y = anterior, z = superior)
and the patient is supine. A view is a C-arm position given by two angles
(``views_deg`` in corridors.json):

- (0, 0) is the AP view: the beam runs anterior to posterior (-y), image
  columns increase toward the patient's left (-x, so the patient's right
  is on the image's left, as a radiograph is read) and rows increase
  caudally (-z, superior at the top).
- ``rotate_x_deg`` tilts the beam cranio-caudally: negative aims it
  caudally (inlet), positive cranially (outlet).
- ``rotate_z_deg`` rolls the C-arm about the patient's long axis: positive
  brings the beam in from the patient's right (+90 is a lateral; the right
  iliac oblique is -45, the right obturator oblique +45).

The tilt is applied first, then the roll. ``view_rotation`` returns the
3x3 matrix ``R`` with ``v_view = R @ v_world``: its rows are the world
directions of the image columns (u), image rows (v) and the beam, and the
volume is summed along the beam.

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
SAFE_AREA_GREEN = (34, 197, 94)  # where a screw's entry may still sit


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


# AP view basis in RAS world coordinates: image columns toward the patient's
# left, image rows toward the feet, beam from anterior to posterior.
_AP_U = np.array([-1.0, 0.0, 0.0])
_AP_V = np.array([0.0, 0.0, -1.0])
_AP_BEAM = np.array([0.0, -1.0, 0.0])


def view_rotation(rotate_x_deg: float, rotate_z_deg: float) -> np.ndarray:
    """3x3 world->view matrix whose rows are the world directions of the
    image columns, image rows and beam for this C-arm position (see the
    module docstring for the angle conventions).

    The AP basis is tilted about the patient's left-right axis, then rolled
    about the long axis; the signs make a negative tilt caudal (inlet) and a
    positive roll bring the beam in from the patient's right.
    """
    carm = _rotation_z(-rotate_z_deg) @ _rotation_x(-rotate_x_deg)
    return np.stack([carm @ _AP_U, carm @ _AP_V, carm @ _AP_BEAM], axis=0)


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
    # Only voxels above 150 HU (bone, and calcium or contrast) contribute, so
    # bony landmarks show the way a C-arm image shows them; with soft tissue
    # included the body outline washed the bone out on real CTs.
    hu_clip: Tuple[float, float] = (150.0, 2000.0),
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


def _as_rgb(view: DrrView, rgb: Optional[np.ndarray]) -> np.ndarray:
    """The view as an RGB image to draw on, or the one passed in."""
    if rgb is not None:
        return rgb
    grey = (np.clip(view.image, 0.0, 1.0) * 255.0).astype(np.uint8)
    return np.stack([grey, grey, grey], axis=-1).astype(np.uint8)


def draw_points(view: DrrView, points_xyz, *, rgb: Optional[np.ndarray] = None, radius_px: float = 1.5, color=SAFE_AREA_GREEN, value: float = 0.65) -> np.ndarray:
    """Tint where a set of world points projects. On a view looking down a
    screw (guidance.down_the_barrel_view) the safe entry area drawn this way
    is what the surgeon is aiming inside of. Draws into ``rgb`` when given,
    so overlays can be stacked (this one first, the screw over it)."""
    from scipy.ndimage import binary_dilation

    rgb = _as_rgb(view, rgb)
    pts = np.atleast_2d(np.asarray(points_xyz, dtype=float))
    if pts.shape[0] == 0:
        return rgb
    h, w = rgb.shape[:2]
    cols, rows = np.atleast_2d(project_point(view, pts)).T
    cols, rows = np.round(cols).astype(int), np.round(rows).astype(int)
    on_image = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
    mask = np.zeros((h, w), dtype=bool)
    mask[rows[on_image], cols[on_image]] = True
    reach = int(np.ceil(radius_px))
    if reach:
        dy, dx = np.mgrid[-reach:reach + 1, -reach:reach + 1]
        mask = binary_dilation(mask, structure=dy ** 2 + dx ** 2 <= radius_px ** 2)
    tint = np.array(color, dtype=float)
    rgb[mask] = (tint * value + rgb[mask].astype(float) * (1.0 - value)).astype(np.uint8)
    return rgb


def draw_screw(view: DrrView, entry_xyz, target_xyz, *, rgb: Optional[np.ndarray] = None, width_px: float = 3.0, value: float = 1.0) -> np.ndarray:
    """Return an RGB uint8 overlay: greyscale DRR (or ``rgb``, to draw over
    something already drawn) + orange screw axis + scale bar."""
    rgb = _as_rgb(view, rgb)
    h, w = rgb.shape[:2]

    p0 = project_point(view, entry_xyz)
    p1 = project_point(view, target_xyz)
    mask = _bresenham_ish_line_mask((h, w), p0, p1, width_px)

    orange = np.array(MNRH_ORANGE, dtype=np.uint8)
    rgb[mask] = (orange.astype(float) * value + rgb[mask].astype(float) * (1.0 - value)).astype(np.uint8)

    _draw_scale_bar(rgb, view.pixel_mm)
    return rgb


def _draw_scale_bar(rgb: np.ndarray, pixel_mm: float) -> None:
    """A 50 mm white bar, bottom-left, so any view can be measured by eye."""
    h, w = rgb.shape[:2]
    bar_len_px = max(1, int(round(50.0 / pixel_mm)))
    margin = max(4, int(0.02 * min(h, w)))
    bar_row0 = max(0, h - margin - 3)
    bar_row1 = min(h, bar_row0 + 3)
    bar_col1 = min(w, margin + bar_len_px)
    if bar_row1 > bar_row0 and bar_col1 > margin:
        rgb[bar_row0:bar_row1, margin:bar_col1] = np.array([255, 255, 255], dtype=np.uint8)


def crop_around(view: DrrView, rgb: np.ndarray, center_xyz, *, half_mm: float = 60.0, zoom: int = 3) -> np.ndarray:
    """A zoomed cut-out of a drawn view around a world point, with its own
    scale bar. A view looking down a screw is mostly empty field; what the
    surgeon needs is the few centimetres around the entry."""
    col, row = project_point(view, center_xyz)
    half_px = max(1, int(round(half_mm / view.pixel_mm)))
    h, w = rgb.shape[:2]
    row0, row1 = max(0, int(round(row)) - half_px), min(h, int(round(row)) + half_px + 1)
    col0, col1 = max(0, int(round(col)) - half_px), min(w, int(round(col)) + half_px + 1)
    if row1 <= row0 or col1 <= col0:
        return rgb  # the point is off the image; the whole view is still true
    cut = np.kron(rgb[row0:row1, col0:col1], np.ones((zoom, zoom, 1), dtype=np.uint8))
    _draw_scale_bar(cut, view.pixel_mm / zoom)
    return cut


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
