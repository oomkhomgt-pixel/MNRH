"""Read the surgeon's fracture marks that Corridor Finder saves per case
(displacement-finder DECISIONS 7e.1: for now a sacral fracture comes from
his marks, which become the fracture surface, labelled as marks).

The format is the one agreed with the Corridor Finder session on
2026-10-04, schema "corridor-finder-fracture-marks/1": one file per case,
<marks directory>/<case alias>.fracture_marks.json, with one named set of
points per fracture, in RAS millimetres:

    {"schema": "corridor-finder-fracture-marks/1", "coordinate_system": "RAS",
     "units": "mm", "case": "pilot-CLINIC_0012", "source": "surgeon marks",
     "fractures": [{"name": "sacrum right", "bone": "sacrum", "side": "right",
                    "points_ras_mm": [[x, y, z], ...]}, ...]}

Anything else is refused, not guessed: another schema, coordinates that are
not RAS (Slicer's own markups files default to LPS, which would put every
mark on the wrong side), units that are not mm. Each fracture is fitted as
its own plane, so a sacral and a ramus fracture on the same side are never
fitted as one. A set too small or too nearly on one line to define a plane
is reported, never fitted.

The marks stay on the workstation, outside the repo (DECISIONS 8.1).
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import corridor_engine  # noqa: F401
except ImportError:  # run from a checkout without the engine installed
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "corridor-finder"))

from corridor_engine import fracture  # noqa: E402

SCHEMA = "corridor-finder-fracture-marks/1"
MARKS_DIR = os.path.join(os.path.expanduser("~"), "CorridorFinderData", "marks")


class MarksRefused(ValueError):
    """The marks file is not in the agreed format."""


@dataclass
class MarkedFracture:
    name: str  # "sacrum right", as the surgeon left it
    bone: str  # "sacrum", "hip_right", ...: the label most of its points lie on
    side: str  # "right", "left" or "midline", relative to the sacral midline
    plane: Optional[fracture.FracturePlane]  # None when its points define no plane
    n_points: int
    note: str = ""


def find_marks_file(case: str, marks_dir: str = MARKS_DIR) -> Optional[str]:
    """The marks file for a case such as "CLINIC_0012", whatever alias it was
    saved under ("pilot-CLINIC_0012"). None when there is none; more than
    one is refused, since which to use is not ours to guess."""
    found = sorted(glob.glob(os.path.join(marks_dir, f"*{case}*.fracture_marks.json")))
    if len(found) > 1:
        raise MarksRefused(f"{len(found)} marks files match {case}: {', '.join(os.path.basename(f) for f in found)}")
    return found[0] if found else None


def read_marks(path: str) -> Tuple[str, List[MarkedFracture]]:
    """The case alias and its marked fractures. Raises MarksRefused when the
    file is not in the agreed format."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema") != SCHEMA:
        raise MarksRefused(f"{os.path.basename(path)}: schema {data.get('schema')!r}, expected {SCHEMA!r}")
    if data.get("coordinate_system") != "RAS":
        raise MarksRefused(f"{os.path.basename(path)}: coordinate_system {data.get('coordinate_system')!r}, "
                           "expected 'RAS' (an LPS file would put every mark on the wrong side)")
    if data.get("units") != "mm":
        raise MarksRefused(f"{os.path.basename(path)}: units {data.get('units')!r}, expected 'mm'")
    out = []
    for i, f in enumerate(data.get("fractures", [])):
        name = str(f.get("name") or f"fracture {i + 1}")
        points = f.get("points_ras_mm") or []
        plane = fracture.fit_plane(points) if len(points) >= fracture.MIN_POINTS else None
        note = "" if plane is not None else (
            f"{len(points)} points do not define a plane (at least {fracture.MIN_POINTS}, spread at least "
            f"{fracture.MIN_SPREAD_MM:.0f} mm): not used")
        out.append(MarkedFracture(name, str(f.get("bone", "unknown")), str(f.get("side", "unknown")), plane,
                                  len(points), note))
    return str(data.get("case", "")), out
