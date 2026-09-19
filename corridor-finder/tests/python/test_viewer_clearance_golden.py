"""Golden test: the exported viewer's clearance check (viewer/clearance.js,
run under Node) against corridor_engine/validate.py on identical screws.

The viewer gets each screw's distance field cropped and rounded down to
0.1 mm (export_viewer.py), so its clearance must be at most validate.py's
and at least that minus 0.1 mm, and it must never report "safe" for a screw
validate.py reports as a breach. Skipped when Node is not installed.
"""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from corridor_engine.edt import VIEWER_EDT_SCALE_MM, bone_edt_mm, quantize_edt_floor
from corridor_engine.export_viewer import crop_edt_for_screw
from corridor_engine.validate import validate_screw
from corridor_engine.volume import Volume

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "node" / "clearance_golden.mjs"


def _bone():
    """An anisotropic, off-origin ellipsoidal 'bone' with a tunnel through
    it, so screws see a range of clearances including breaches."""
    spacing = (0.8, 0.9, 1.25)
    origin = (-40.0, 12.5, 101.0)
    nz, ny, nx = 60, 70, 110
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    x = xx * spacing[0]
    y = yy * spacing[1]
    z = zz * spacing[2]
    mask = ((x - 44) / 40) ** 2 + ((y - 31) / 22) ** 2 + ((z - 37) / 26) ** 2 <= 1.0
    mask &= ~(((y - 31) ** 2 + (z - 37) ** 2) <= 5.0 ** 2)  # tunnel along x
    edt = Volume(bone_edt_mm(mask, spacing), spacing, origin)
    labels = Volume(mask.astype(np.uint8), spacing, origin)
    return edt, labels


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_viewer_clearance_matches_validate_py(tmp_path):
    edt, labels = _bone()
    rng = np.random.default_rng(7)
    lo = np.array(edt.origin) + 5.0
    hi = np.array(edt.ijk_to_world(np.array(edt.array.shape[::-1]) - 1)) - 5.0
    cases, expected = [], []
    for _ in range(300):
        entry = rng.uniform(lo, hi)
        target = entry + rng.normal(size=3) * rng.uniform(5.0, 45.0)
        diameter = float(rng.choice([3.5, 4.5, 6.5, 7.0, 7.3]))
        margin = float(rng.choice([0.0, 1.0, 2.0, 3.0]))
        v = validate_screw(entry, target, diameter, margin, edt_volume=edt, labels_volume=labels)
        crop = crop_edt_for_screw(edt, entry, target)
        data = quantize_edt_floor(crop.array, VIEWER_EDT_SCALE_MM)
        cases.append(
            {
                "entry": entry.tolist(),
                "target": target.tolist(),
                "diameter_mm": diameter,
                "margin_mm": margin,
                "edt": {
                    "shape": list(crop.array.shape),
                    "spacing": list(crop.spacing),
                    "origin": list(crop.origin),
                    "scale_mm": VIEWER_EDT_SCALE_MM,
                    "data_b64": base64.b64encode(data.tobytes(order="C")).decode("ascii"),
                },
            }
        )
        expected.append((v.min_clearance_mm, v.breach))

    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    run = subprocess.run(["node", str(RUNNER), str(cases_path)], capture_output=True, text=True, check=True)
    results = json.loads(run.stdout)

    assert len(results) == len(expected)
    n_breach = 0
    for (py_clearance, py_breach), js in zip(expected, results):
        n_breach += py_breach
        assert js["clearance_mm"] <= py_clearance + 1e-6
        assert js["clearance_mm"] >= py_clearance - VIEWER_EDT_SCALE_MM - 1e-6
        if py_breach:
            assert js["breach"], "viewer called safe a screw validate.py calls a breach"
    assert 0 < n_breach < len(expected)  # both outcomes were exercised
