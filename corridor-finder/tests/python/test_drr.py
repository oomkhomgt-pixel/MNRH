import numpy as np

from corridor_engine.drr import (
    render_view,
    project_point,
    draw_screw,
    write_png,
    MNRH_ORANGE,
)
from corridor_engine.phantoms import solid_rod
from corridor_engine.volume import Volume


def _rod_volume(radius_mm=8.0, shape=(60, 60, 120)):
    mask = solid_rod(shape=shape, radius_mm=radius_mm, axis=2)
    hu = np.full(shape, -1000.0, dtype=np.float32)
    hu[mask] = 800.0
    spacing = (1.0, 1.0, 1.0)
    vol = Volume(array=hu, spacing=spacing, origin=(0.0, 0.0, 0.0))
    return vol


def test_ap_view_projects_point_to_expected_pixel():
    vol = _rod_volume()
    nz, ny, nx = vol.array.shape
    center_world = vol.ijk_to_world(((nx - 1) / 2.0, (ny - 1) / 2.0, (nz - 1) / 2.0))

    view = render_view(vol, rotate_x_deg=0.0, rotate_z_deg=0.0, name="ap", pixel_mm=1.0)
    h, w = view.image.shape

    col, row = project_point(view, center_world)
    assert abs(col - w / 2.0) < 2.0
    assert abs(row - h / 2.0) < 2.0

    ci, ri = int(round(col)), int(round(row))
    center_val = view.image[ri, ci]
    corner_val = view.image[2, 2]
    assert center_val - corner_val > 0.2


def test_projection_scales_with_rotation():
    vol = _rod_volume()
    view = render_view(vol, rotate_x_deg=-45.0, rotate_z_deg=0.0, name="inlet", pixel_mm=1.0)

    center_world = vol.ijk_to_world(
        ((vol.array.shape[2] - 1) / 2.0, (vol.array.shape[1] - 1) / 2.0, (vol.array.shape[0] - 1) / 2.0)
    )

    # Two points 100mm apart along the view's row direction (v_hat), which
    # is perpendicular to the ray direction by construction.
    p0 = center_world - 50.0 * view.v_hat
    p1 = center_world + 50.0 * view.v_hat

    c0, r0 = project_point(view, p0)
    c1, r1 = project_point(view, p1)

    dist_px = np.hypot(c1 - c0, r1 - r0)
    expected_px = 100.0 / view.pixel_mm
    assert abs(dist_px - expected_px) < 2.0


def test_write_png_roundtrip(tmp_path):
    vol = _rod_volume(shape=(30, 30, 40))
    view = render_view(vol, rotate_x_deg=0.0, rotate_z_deg=0.0, name="ap", pixel_mm=1.0)

    out_path = tmp_path / "drr.png"
    write_png(out_path, view.image)

    with open(out_path, "rb") as f:
        header = f.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"

    try:
        from PIL import Image

        im = Image.open(out_path)
        h, w = view.image.shape
        assert im.size == (w, h)
    except ImportError:
        pass


def test_draw_screw_marks_orange_pixels():
    vol = _rod_volume()
    view = render_view(vol, rotate_x_deg=0.0, rotate_z_deg=0.0, name="ap", pixel_mm=1.0)

    nz, ny, nx = vol.array.shape
    entry = vol.ijk_to_world((nx / 2.0, ny / 2.0, 0.0))
    target = vol.ijk_to_world((nx / 2.0, ny / 2.0, nz - 1.0))

    rgb = draw_screw(view, entry, target, width_px=3.0)
    assert rgb.dtype == np.uint8
    assert rgb.shape == (view.image.shape[0], view.image.shape[1], 3)

    orange = np.array(MNRH_ORANGE)
    dist = np.abs(rgb.astype(int) - orange[None, None, :]).sum(axis=-1)
    close_mask = dist < 15
    assert close_mask.any()

    # Check the orange pixels lie near the projected screw axis (center column/row).
    col_e, row_e = project_point(view, entry)
    col_t, row_t = project_point(view, target)
    rows, cols = np.nonzero(close_mask)
    mid_col = (col_e + col_t) / 2.0
    mid_row = (row_e + row_t) / 2.0
    # at least one orange pixel should be close to the segment midpoint
    dmin = np.min(np.hypot(cols - mid_col, rows - mid_row))
    assert dmin < 5.0
