"""The surgeon's fracture marks, one named set per fracture, as a file.

Corridor Finder keeps the points the surgeon clicks on each fracture as a
separate set (one markups node per fracture), because a plane can only be
fitted to the marks of ONE fracture: a right sacral fracture and a right
ramus fracture fitted together give a plane through neither. The sets are
written, on every change, to

    <CorridorFinderData>/marks/<case alias>.fracture_marks.json

outside the repository, so the displacement measurement can read them
without Slicer (displacement-finder DECISIONS 7e.1: until its own detector
finds sacral fractures, his marks are the sacral fracture surface).

The file states its coordinate system: RAS, millimetres (3D Slicer's world
frame, x toward the patient's right, y anterior, z superior), never LPS.
It carries the case alias only: no name or identifier of the patient.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Sequence, Tuple

import numpy as np

SCHEMA = "corridor-finder-fracture-marks/1"
BONES = ("sacrum", "hip_right", "hip_left", "femur_right", "femur_left", "unknown")
SIDES = ("right", "left", "midline")


@dataclass
class FractureMarks:
    name: str  # e.g. "sacrum right"; the surgeon may rename it
    bone: str  # one of BONES: the bone within 5 mm of most of its points
    side: str  # one of SIDES, relative to the sacral midline
    points_ras_mm: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))

    def __post_init__(self):
        self.points_ras_mm = np.asarray(self.points_ras_mm, dtype=float).reshape(-1, 3)
        if self.bone not in BONES:
            raise ValueError(f"{self.name}: bone {self.bone!r} is not one of {BONES}")
        if self.side not in SIDES:
            raise ValueError(f"{self.name}: side {self.side!r} is not one of {SIDES}")


def to_dict(case: str, fractures: Sequence[FractureMarks]) -> dict:
    return {
        "schema": SCHEMA,
        "coordinate_system": "RAS",
        "units": "mm",
        "case": case,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "source": "surgeon marks",
        "fractures": [{"name": f.name, "bone": f.bone, "side": f.side,
                       "points_ras_mm": [[float(v) for v in p] for p in f.points_ras_mm]} for f in fractures],
    }


def save(path: str, case: str, fractures: Sequence[FractureMarks]) -> str:
    """Write the file whole or not at all (a reader never sees half of it)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = json.dumps(to_dict(case, fractures), indent=1)
    handle, tmp = tempfile.mkstemp(prefix=".marks-", suffix=".json", dir=os.path.dirname(os.path.abspath(path)))
    with os.fdopen(handle, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


def load(path: str) -> Tuple[str, List[FractureMarks]]:
    """The case alias and the fracture sets. Refuses a file that is not this
    schema or not in RAS millimetres, rather than guess."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{path}: schema {data.get('schema')!r}, expected {SCHEMA!r}")
    if data.get("coordinate_system") != "RAS" or data.get("units") != "mm":
        raise ValueError(f"{path}: points are in {data.get('coordinate_system')!r} {data.get('units')!r}, "
                         "expected RAS mm")
    return data.get("case", ""), [FractureMarks(name=d["name"], bone=d["bone"], side=d["side"],
                                                points_ras_mm=d["points_ras_mm"]) for d in data.get("fractures", [])]


def file_name(case: str) -> str:
    """<case alias>.fracture_marks.json, with anything unsafe in a file name
    replaced."""
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in case.strip()) or "case"
    return f"{safe}.fracture_marks.json"
