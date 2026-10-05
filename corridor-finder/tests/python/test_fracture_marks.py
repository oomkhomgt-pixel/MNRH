import json

import numpy as np
import pytest

from corridor_engine.fracture_marks import SCHEMA, FractureMarks, file_name, load, save


def _sets():
    return [FractureMarks("sacrum right", "sacrum", "right", [[30.0, 10.0, 100.0], [31.0, 12.0, 90.0], [32.0, 5.0, 80.0]]),
            FractureMarks("hip right", "hip_right", "right", [[60.0, 40.0, 20.0], [62.0, 42.0, 25.0], [65.0, 38.0, 30.0]])]


def test_the_marks_come_back_as_they_went_out(tmp_path):
    path = save(str(tmp_path / file_name("pilot-CLINIC_0012")), "pilot-CLINIC_0012", _sets())
    case, sets = load(path)
    assert case == "pilot-CLINIC_0012"
    assert [s.name for s in sets] == ["sacrum right", "hip right"]
    assert np.allclose(sets[0].points_ras_mm, _sets()[0].points_ras_mm)
    data = json.load(open(path, encoding="utf-8"))
    assert data["schema"] == SCHEMA and data["coordinate_system"] == "RAS" and data["units"] == "mm"


def test_a_file_in_another_frame_is_refused(tmp_path):
    path = tmp_path / "x.fracture_marks.json"
    data = json.load(open(save(str(path), "c", _sets()), encoding="utf-8"))
    data["coordinate_system"] = "LPS"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="RAS"):
        load(str(path))


def test_unknown_bones_and_sides_are_refused():
    with pytest.raises(ValueError):
        FractureMarks("x", "ilium", "right", [])
    with pytest.raises(ValueError):
        FractureMarks("x", "sacrum", "centre", [])


def test_a_case_alias_becomes_a_safe_file_name():
    assert file_name("pilot-CLINIC_0012") == "pilot-CLINIC_0012.fracture_marks.json"
    assert file_name("a/b c") == "a_b_c.fracture_marks.json"
