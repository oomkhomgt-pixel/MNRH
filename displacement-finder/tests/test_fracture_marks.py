"""The marks reader takes exactly the format agreed with Corridor Finder
and refuses everything else (displacement-finder DECISIONS 7e.1)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import fracture_marks as fm  # noqa: E402

GOOD = {
    "schema": fm.SCHEMA, "coordinate_system": "RAS", "units": "mm", "case": "pilot-CLINIC_0012",
    "source": "surgeon marks",
    "fractures": [
        {"name": "sacrum right", "bone": "sacrum", "side": "right",
         "points_ras_mm": [[20.0, 0.0, 0.0], [22.0, 10.0, 5.0], [21.0, -5.0, 20.0], [23.0, 5.0, 30.0]]},
        {"name": "hip right", "bone": "hip_right", "side": "right",
         "points_ras_mm": [[60.0, 40.0, -50.0], [62.0, 30.0, -60.0], [58.0, 45.0, -70.0]]},
        {"name": "too few", "bone": "sacrum", "side": "left", "points_ras_mm": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]},
    ],
}


def _write(tmp_path, data, name="pilot-CLINIC_0012.fracture_marks.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_each_fracture_is_its_own_plane_and_a_short_set_is_reported_not_fitted(tmp_path):
    case, fractures = fm.read_marks(_write(tmp_path, GOOD))
    assert case == "pilot-CLINIC_0012"
    assert [f.name for f in fractures] == ["sacrum right", "hip right", "too few"]
    sacral, hip, short = fractures
    assert sacral.plane is not None and hip.plane is not None
    # Two fractures on one side are two planes, not one.
    assert abs(float(sacral.plane.normal @ hip.plane.normal)) < 0.99
    assert short.plane is None and "do not define a plane" in short.note


@pytest.mark.parametrize("field, value, says", [
    ("schema", "corridor-finder-fracture-marks/2", "schema"),
    ("coordinate_system", "LPS", "wrong side"),
    ("units", "cm", "units"),
])
def test_anything_but_the_agreed_format_is_refused(tmp_path, field, value, says):
    bad = dict(GOOD, **{field: value})
    with pytest.raises(fm.MarksRefused, match=says):
        fm.read_marks(_write(tmp_path, bad))


def test_the_file_is_found_by_case_whatever_its_alias_and_two_are_refused(tmp_path):
    assert fm.find_marks_file("CLINIC_0012", str(tmp_path)) is None
    path = _write(tmp_path, GOOD)
    assert fm.find_marks_file("CLINIC_0012", str(tmp_path)) == path
    assert fm.find_marks_file("CLINIC_0023", str(tmp_path)) is None
    _write(tmp_path, GOOD, name="other-CLINIC_0012.fracture_marks.json")
    with pytest.raises(fm.MarksRefused, match="2 marks files"):
        fm.find_marks_file("CLINIC_0012", str(tmp_path))
