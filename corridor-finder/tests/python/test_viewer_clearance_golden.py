"""Golden test: the exported viewer's screw check (viewer/clearance.js, run
under Node) against corridor_engine/validate.py on identical screws.

The viewer gets each screw's distance field cropped and rounded down to
0.1 mm (export_viewer.py). Everything that decides where the screw is and
which rule applies where (cortex crossings, normals, zones, catalogue
length, the exemption distance transform) must come out identical; the
clearance may only be up to 0.1 mm lower in the viewer, never higher, and
the viewer must never call safe a screw validate.py calls a breach. A
screw moved too far from where it was exported must be refused, not
guessed. Skipped when Node is not installed.
"""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from scipy.ndimage import binary_erosion, distance_transform_edt

from corridor_engine import cortex
from corridor_engine.edt import VIEWER_EDT_SCALE_MM, bone_edt_mm, quantize_edt_floor
from corridor_engine.export_viewer import crop_box_for_screw
from corridor_engine.validate import validate_screw
from corridor_engine.volume import Volume

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "node" / "clearance_golden.mjs"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")

CATALOG = [float(v) for v in range(10, 105, 5)]


def _bone():
    """An anisotropic, off-origin ellipsoidal 'bone' with a tunnel through
    it and a groove cut into its top, so screws see a range of clearances,
    side walls next to their entry, and breaches."""
    spacing = (0.8, 0.9, 1.25)
    origin = (-40.0, 12.5, 101.0)
    nz, ny, nx = 60, 70, 110
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    x = xx * spacing[0]
    y = yy * spacing[1]
    z = zz * spacing[2]
    mask = ((x - 44) / 40) ** 2 + ((y - 31) / 22) ** 2 + ((z - 37) / 26) ** 2 <= 1.0
    mask &= ~(((y - 31) ** 2 + (z - 37) ** 2) <= 5.0 ** 2)  # tunnel along x
    mask &= ~((np.abs(y - 25) <= 1.6) & (z >= 55))  # groove along x in the top
    edt = Volume(bone_edt_mm(mask, spacing), spacing, origin)
    labels = Volume(mask.astype(np.uint8), spacing, origin)
    return edt, labels, mask


def _run_node(tmp_path, payload):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    run = subprocess.run(["node", str(RUNNER), str(path)], capture_output=True, text=True, check=True)
    return json.loads(run.stdout)


def _volume_payload(edt):
    q = quantize_edt_floor(edt.array, VIEWER_EDT_SCALE_MM)
    assert np.array_equal(q > 0, edt.array > 0)
    return {
        "full_shape": list(edt.array.shape),
        "full_origin": list(edt.origin),
        "spacing": list(edt.spacing),
        "scale_mm": VIEWER_EDT_SCALE_MM,
        "data_b64": base64.b64encode(q.tobytes(order="C")).decode("ascii"),
    }


def _case(edt, entry, target, diameter, margin, tip_rule, catalog, crop_for=None):
    """The viewer's input for a screw: its handles plus the crop exported
    for it (or for ``crop_for``, the handles it was exported with)."""
    ce, ct = crop_for if crop_for is not None else (entry, target)
    lo, hi = crop_box_for_screw(edt, ce, ct, diameter, margin)
    return {
        "entry": [float(v) for v in entry],
        "target": [float(v) for v in target],
        "diameter_mm": diameter,
        "margin_mm": margin,
        "tip_rule": tip_rule,
        "catalog_lengths_mm": catalog,
        "index_offset": [int(v) for v in lo],
        "shape": [int(v) for v in np.maximum(hi - lo + 1, 0)[::-1]],
    }


def _random_screws(edt, mask, rng, n):
    """Screws entering the bone from outside at up to 70 degrees to its
    surface normal, with the entry handle inside it, and at random."""
    kk, jj, ii = np.nonzero(mask & ~binary_erosion(mask))
    org, sp = np.array(edt.origin), np.array(edt.spacing)
    lo = org + 3.0
    hi = org + (np.array(mask.shape[::-1]) - 1) * sp - 3.0
    screws = []
    while len(screws) < n:
        kind = rng.choice(["outside", "inside", "random"], p=[0.5, 0.25, 0.25])
        if kind == "random":
            entry = rng.uniform(lo, hi)
            target = entry + rng.normal(size=3) * rng.uniform(8.0, 45.0)
        else:
            idx = rng.integers(len(ii))
            p = org + np.array([ii[idx], jj[idx], kk[idx]]) * sp
            n_in = cortex.inward_normal(edt, p)
            if n_in is None:
                continue
            a = rng.normal(size=3)
            a -= a.dot(n_in) * n_in
            a /= np.linalg.norm(a)
            tilt = np.radians(rng.uniform(0.0, 70.0))
            u = np.cos(tilt) * n_in + np.sin(tilt) * a
            if kind == "outside":
                entry = p - rng.uniform(0.0, 5.0) * u
            else:
                entry = p + rng.uniform(0.5, 25.0) * u
            target = entry + rng.uniform(10.0, 70.0) * u
        diameter = float(rng.choice([3.5, 4.5, 6.5, 7.3]))
        margin = float(rng.choice([0.0, 1.0, 2.0, 3.0]))
        tip_rule = str(rng.choice(["inside", "through"]))
        catalog = CATALOG if rng.random() < 0.7 else None
        screws.append((entry, target, diameter, margin, tip_rule, catalog))
    return screws


def _assert_same(py, js, what):
    assert js["out_of_region"] is False, what
    assert js["warning_codes"] == py.warning_codes, what
    assert js["length_mm"] == pytest.approx(py.length_mm, abs=1e-9), what
    for key in ("start_xyz", "tip_xyz", "exit_xyz"):
        a, b = getattr(py, key), js[key]
        assert (a is None) == (b is None), (what, key)
        if a is not None:
            assert np.allclose(a, b, rtol=0, atol=1e-9), (what, key)
    for key in ("entry_handle_offset_mm", "entry_zone_mm", "exit_zone_mm", "protrusion_mm"):
        a, b = getattr(py, key), js[key]
        assert (a is None) == (b is None), (what, key)
        if a is not None:
            assert b == pytest.approx(a, abs=1e-9), (what, key)
    for key in ("entry_angle_deg", "exit_angle_deg"):
        a, b = getattr(py, key), js[key]
        assert (a is None) == (b is None), (what, key)
        if a is not None:
            assert b == pytest.approx(a, abs=1e-6), (what, key)
    # The rounded-down field can only make the viewer stricter, by < 0.1 mm.
    assert js["min_clearance_mm"] <= py.min_clearance_mm + 1e-6, what
    assert js["min_clearance_mm"] >= py.min_clearance_mm - VIEWER_EDT_SCALE_MM - 1e-6, what
    if py.breach:
        assert js["breach"] is True, f"{what}: viewer called safe a screw validate.py calls a breach"


@needs_node
def test_viewer_screw_check_matches_validate_py(tmp_path):
    edt, labels, mask = _bone()
    rng = np.random.default_rng(7)
    screws = _random_screws(edt, mask, rng, 260)
    expected = [
        validate_screw(e, t, d, m, edt_volume=edt, labels_volume=labels, tip_rule=rule, catalog_lengths_mm=cat)
        for e, t, d, m, rule, cat in screws
    ]
    cases = [_case(edt, *s) for s in screws]
    results = _run_node(tmp_path, {"volume": _volume_payload(edt), "screws": cases})["screws"]

    assert len(results) == len(expected)
    for i, (py, js) in enumerate(zip(expected, results)):
        _assert_same(py, js, f"screw {i}")

    # The cases exercised every part of the rule.
    codes = [c for v in expected for c in v.warning_codes]
    for code in ("no_bone", "handle_off_cortex", "entry_oblique", "exit_not_found", "no_catalog_length",
                 "entry_not_outer", "exit_not_outer", "entry_cortex_not_found"):
        assert code in codes, code
    assert any(v.exit_xyz is not None and v.protrusion_mm > 0 for v in expected)
    assert 0 < sum(v.breach for v in expected) < len(expected)


@needs_node
def test_viewer_follows_dragged_handles_or_refuses(tmp_path):
    """Handles dragged after export: the viewer either checks the screw
    exactly as validate.py would, or says it cannot (out of region), never
    'safe' without checking."""
    spacing, origin = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)
    zz, yy, xx = np.mgrid[0:70, 0:80, 0:260]
    # A long bar-shaped bone, so crops are much smaller than the CT.
    bar = (np.abs(yy - 40) <= 15) & (np.abs(zz - 35) <= 15) & (xx >= 10) & (xx <= 250)
    edt = Volume(bone_edt_mm(bar, spacing), spacing, origin)
    labels = Volume(bar.astype(np.uint8), spacing, origin)
    rng = np.random.default_rng(11)
    cases, expected, moved_far = [], [], []
    for _ in range(80):
        entry = np.array([rng.uniform(0.0, 9.0), rng.uniform(32.0, 48.0), rng.uniform(28.0, 42.0)])
        target = entry + np.array([rng.uniform(40.0, 80.0), rng.normal(0, 3), rng.normal(0, 3)])
        d, m = float(rng.choice([4.5, 6.5, 7.3])), 2.0
        rule = str(rng.choice(["inside", "through"]))
        far = bool(rng.random() < 0.5)
        shift = np.array([rng.uniform(80.0, 140.0), 0.0, 0.0]) if far else rng.normal(size=3) * 3.0
        new_entry, new_target = entry + shift, target + shift
        expected.append(validate_screw(new_entry, new_target, d, m, edt_volume=edt, labels_volume=labels, tip_rule=rule, catalog_lengths_mm=CATALOG))
        cases.append(_case(edt, new_entry, new_target, d, m, rule, CATALOG, crop_for=(entry, target)))
        moved_far.append(far)
    results = _run_node(tmp_path, {"volume": _volume_payload(edt), "screws": cases})["screws"]

    n_refused = 0
    for i, (py, js, far) in enumerate(zip(expected, results, moved_far)):
        if js["out_of_region"]:
            n_refused += 1
            assert js["breach"] is None and js["min_clearance_mm"] is None
            assert far, f"screw {i}: refused after a small drag"
        else:
            _assert_same(py, js, f"screw {i}")
    # Far drags mostly leave the exported region (some still fit, and were
    # then checked exactly); small ones never do.
    assert n_refused >= 0.8 * sum(moved_far)


@needs_node
def test_viewer_distance_transform_is_exact(tmp_path):
    rng = np.random.default_rng(5)
    cases, expected = [], []
    for shape, spacing in (((17, 23, 29), (0.8, 0.9, 1.25)), ((31, 12, 9), (0.5, 1.5, 0.7)), ((9, 9, 40), (1.0, 1.0, 1.0))):
        solid = rng.random(shape) < 0.93
        solid[rng.random(shape) < 0.002] = False
        expected.append(distance_transform_edt(solid, sampling=spacing[::-1]))
        cases.append({"shape": list(shape), "spacing": list(spacing), "solid_b64": base64.b64encode(solid.astype(np.uint8).tobytes()).decode("ascii")})
    results = _run_node(tmp_path, {"edts": cases})["edts"]
    for want, got in zip(expected, results):
        assert np.allclose(np.array(got).reshape(want.shape), want, rtol=1e-12, atol=1e-12)


@needs_node
def test_viewer_rule_constants_match_python():
    from corridor_engine import validate

    script = "import('" + (ROOT / "viewer" / "clearance.js").as_uri() + "').then(m => console.log(JSON.stringify(m)))"
    run = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    js = json.loads(run.stdout)
    assert js["CROSSING_STEP_MM"] == cortex.CROSSING_STEP_MM
    assert js["MAX_SEARCH_MM"] == cortex.MAX_SEARCH_MM
    assert js["NORMAL_RADIUS_MM"] == cortex.NORMAL_RADIUS_MM
    assert js["COS_OBLIQUE"] == cortex.COS_OBLIQUE
    assert js["CORTEX_DEPTH_TOLERANCE_MM"] == cortex.CORTEX_DEPTH_TOLERANCE_MM
    assert js["MAX_PROTRUSION_MM"] == cortex.MAX_PROTRUSION_MM
    assert js["HANDLE_OFF_CORTEX_WARN_MM"] == validate.HANDLE_OFF_CORTEX_WARN_MM
    assert js["UNCHECKED_ENTRY_CODES"] == list(validate.UNCHECKED_ENTRY_CODES)
