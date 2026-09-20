import numpy as np

from corridor_engine.drr import (
    load_views,
    view_rotation,
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


def _bright_points_volume(points_xyz_mm, shape=(80, 80, 80)):
    """1 mm voxels, origin 0: a bright 3x3x3 voxel block at each world point
    (thick enough to survive trilinear resampling at any sub-voxel offset)."""
    hu = np.full(shape, -1000.0, dtype=np.float32)
    for x, y, z in points_xyz_mm:
        i, j, k = int(round(x)), int(round(y)), int(round(z))
        hu[k - 1:k + 2, j - 1:j + 2, i - 1:i + 2] = 1500.0
    return Volume(array=hu, spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0))


def test_named_views_have_anatomical_beam_directions():
    """World coordinates are RAS (x = patient right, y = anterior,
    z = superior). With the angles in corridors.json, each named view's beam
    must run the way that view is taken of a supine patient. (Before this was
    fixed, AP, lateral and all Judet views projected along the long axis.)"""
    views = load_views()
    s = np.sqrt(0.5)
    expected_beam = {
        "ap": (0, -1, 0),  # anterior to posterior
        "lateral": (-1, 0, 0),  # enters on the patient's right
        "lateral_sacral": (-1, 0, 0),
        "inlet": (0, -s, -s),  # tilted caudally
        "outlet": (0, -s, s),  # tilted cranially
        "iliac_oblique_right": (s, -s, 0),  # perpendicular to the right iliac wing
        "obturator_oblique_right": (-s, -s, 0),  # right obturator foramen en face
        "iliac_oblique_left": (-s, -s, 0),
        "obturator_oblique_left": (s, -s, 0),
    }
    views = {k: v for k, v in views.items() if not k.startswith("posterior_column_triangle")}
    assert set(expected_beam) == set(views)
    for name, beam in expected_beam.items():
        assert np.allclose(view_rotation(*views[name])[2], beam, atol=1e-9), name


def test_posterior_column_triangle_view_is_an_inlet_with_a_little_obturator_tilt():
    """Sikarinkul et al. (Bangkok Med J 2025;21(2):116-122) take the
    posterior column in one view: obturator oblique 10 degrees with inlet
    25 degrees. The beam must therefore run mostly back and down, tilted a
    little toward the side being drilled."""
    views = load_views()
    for side, sign in (("right", -1.0), ("left", 1.0)):
        beam = view_rotation(*views[f"posterior_column_triangle_{side}"])[2]
        assert abs(beam[1]) > abs(beam[0]) and abs(beam[1]) > abs(beam[2]), "mostly posterior"
        assert beam[2] < 0, "tilted caudally, as an inlet is"
        assert np.isclose(np.degrees(np.arcsin(abs(beam[2]))), 25.0, atol=1.0), "25 degrees of inlet"
        # The obturator oblique of one side enters from the other, so 10
        # degrees of it puts that much of the beam across the patient.
        assert np.sign(beam[0]) == sign and np.isclose(
            np.degrees(np.arctan2(abs(beam[0]), abs(beam[1]))), 10.0, atol=1.0)


def test_ap_view_is_read_like_a_radiograph():
    vol = _bright_points_volume([(40, 40, 40)])
    view = render_view(vol, rotate_x_deg=0.0, rotate_z_deg=0.0, name="ap", pixel_mm=1.0)
    right, left = project_point(view, (50, 40, 40)), project_point(view, (30, 40, 40))
    up, down = project_point(view, (40, 40, 50)), project_point(view, (40, 40, 30))
    front, back = project_point(view, (40, 50, 40)), project_point(view, (40, 30, 40))
    assert right[0] < left[0]  # patient's right on the image's left
    assert up[1] < down[1]  # superior at the top
    assert np.allclose(front, back)  # anterior and posterior overlap


def test_rendered_image_is_a_projection_along_the_beam():
    """Checks render_view itself, not just the basis vectors: a rod lying
    along a view's beam must render as a compact spot, and the same rod is a
    long streak in the AP view when it is perpendicular to the AP beam."""
    views = load_views()
    center = np.array([40.0, 40.0, 40.0])
    for name in ("ap", "lateral", "inlet", "outlet", "iliac_oblique_right", "obturator_oblique_right"):
        beam = view_rotation(*views[name])[2]
        vol = _bright_points_volume([center + t * beam for t in np.arange(-25.0, 26.0)])
        spot = render_view(vol, *views[name], name=name, pixel_mm=1.0).image
        assert (spot > 0.5 * spot.max()).sum() <= 30, name
        if abs(beam[1]) < 0.9:  # rod not along the AP beam
            streak = render_view(vol, 0.0, 0.0, name="ap", pixel_mm=1.0).image
            assert (streak > 0.5 * streak.max()).sum() >= 60, name


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


def test_draw_points_marks_where_the_points_project():
    from corridor_engine.drr import draw_points

    vol = _rod_volume()
    view = render_view(vol, rotate_x_deg=0.0, rotate_z_deg=0.0, name="ap", pixel_mm=1.0)
    points = np.array([vol.ijk_to_world((40, 30, 30)), vol.ijk_to_world((60, 30, 30))])

    rgb = draw_points(view, points, radius_px=1.0)
    for point in points:
        col, row = project_point(view, point)
        assert tuple(rgb[int(round(row)), int(round(col))]) != tuple(rgb[0, 0])
    # The tint is blended with the image, so look for greenish pixels.
    tinted = (rgb[..., 1].astype(int) > rgb[..., 0].astype(int) + 20) & (rgb[..., 1].astype(int) > rgb[..., 2].astype(int) + 20)
    assert 4 <= tinted.sum() <= 30  # two small discs, nothing else

    # A screw drawn afterwards goes on top of the area, not under it.
    over = draw_screw(view, points[0], points[1], rgb=rgb)
    col, row = project_point(view, points[0])
    assert tuple(over[int(round(row)), int(round(col))]) == MNRH_ORANGE

    # Points outside the image are skipped rather than wrapping around.
    plain = draw_points(view, np.zeros((0, 3)))
    far = np.array([[1e4, 1e4, 1e4]])
    assert np.array_equal(draw_points(view, far, radius_px=1.0), plain)


def test_crop_around_zooms_in_on_a_point_and_keeps_its_scale_bar():
    from corridor_engine.drr import crop_around

    vol = _rod_volume()
    view = render_view(vol, rotate_x_deg=0.0, rotate_z_deg=0.0, name="ap", pixel_mm=1.0)
    centre = vol.ijk_to_world((60, 30, 30))
    rgb = draw_screw(view, vol.ijk_to_world((10, 30, 30)), vol.ijk_to_world((110, 30, 30)))

    cut = crop_around(view, rgb, centre, half_mm=20.0, zoom=3)
    assert cut.shape[0] == cut.shape[1] == (2 * 20 + 1) * 3
    # The screw runs through the middle of the cut-out, and a 50 mm bar at
    # this zoom is 150 px wide, so it spans it.
    middle = cut[cut.shape[0] // 2]
    assert np.any(np.all(middle == np.array(MNRH_ORANGE, dtype=np.uint8), axis=-1))
    white = np.all(cut == np.array([255, 255, 255], dtype=np.uint8), axis=-1)
    assert white[-8:, :].sum() > 100
