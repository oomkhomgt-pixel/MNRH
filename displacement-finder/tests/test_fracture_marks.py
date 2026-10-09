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
    # Reported in the words Corridor Finder's panel uses (fracture.why_no_plane).
    from corridor_engine import fracture

    assert short.plane is None and short.note.startswith(fracture.why_no_plane([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]))


@pytest.mark.parametrize("field, value, says", [
    ("schema", "corridor-finder-fracture-marks/2", "schema"),
    ("coordinate_system", "LPS", "expected RAS mm"),
    ("units", "cm", "expected RAS mm"),
])
def test_anything_but_the_agreed_format_is_refused(tmp_path, field, value, says):
    """Refused by the shared reader (corridor_engine.fracture_marks.load),
    the one reader both projects use."""
    bad = dict(GOOD, **{field: value})
    with pytest.raises(fm.MarksRefused, match=says):
        fm.read_marks(_write(tmp_path, bad))


def test_an_unknown_bone_is_refused(tmp_path):
    bad = dict(GOOD, fractures=[dict(GOOD["fractures"][0], bone="femur")])
    with pytest.raises(fm.MarksRefused, match="bone"):
        fm.read_marks(_write(tmp_path, bad))


def test_the_harness_sample_corridor_finder_wrote_reads(tmp_path):
    """A file written by Corridor Finder's own save(), not by this test."""
    from corridor_engine import fracture_marks as shared

    path = shared.save(str(tmp_path / shared.file_name("SAMPLE-harness")), "SAMPLE-harness", [
        shared.FractureMarks("sacrum right", "sacrum", "right",
                             [[28.0, -2.0, 105.0], [31.5, 4.0, 92.0], [33.0, -6.0, 80.0], [35.5, 1.0, 68.0]]),
        shared.FractureMarks("hip right", "hip_right", "right", [[18.0, 62.0, 10.0], [22.0, 55.0, 4.0], [26.0, 60.0, -3.0]]),
    ])
    case, fractures = fm.read_marks(path)
    assert case == "SAMPLE-harness"
    assert [(f.name, f.n_points) for f in fractures] == [("sacrum right", 4), ("hip right", 3)]
    # Each set gets a plane exactly when the shared rule (fracture.fit_plane)
    # gives one, and is reported otherwise. The sample's three hip points
    # are too close to one line for it, so they are reported, not fitted.
    from corridor_engine import fracture

    for f, (_, sets) in zip(fractures, [shared.load(path)] * len(fractures)):
        mine = next(s for s in sets if s.name == f.name)
        assert (f.plane is None) == (fracture.fit_plane(mine.points_ras_mm) is None)
        assert (f.plane is None) == bool(f.note)
    assert fractures[0].plane is not None and fractures[1].plane is None


def test_the_file_is_found_by_case_whatever_its_alias_and_two_are_refused(tmp_path):
    assert fm.find_marks_file("CLINIC_0012", str(tmp_path)) is None
    path = _write(tmp_path, GOOD)
    assert fm.find_marks_file("CLINIC_0012", str(tmp_path)) == path
    assert fm.find_marks_file("CLINIC_0023", str(tmp_path)) is None
    _write(tmp_path, GOOD, name="other-CLINIC_0012.fracture_marks.json")
    with pytest.raises(fm.MarksRefused, match="2 marks files"):
        fm.find_marks_file("CLINIC_0012", str(tmp_path))
