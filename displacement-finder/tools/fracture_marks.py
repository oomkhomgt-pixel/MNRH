"""Turn the surgeon's fracture marks, as Corridor Finder saves them per
case, into one plane per marked fracture (displacement-finder DECISIONS
7e.1: for now a sacral fracture comes from his marks, which become the
fracture surface, labelled as marks).

The file is read by the shared engine's reader,
``corridor_engine.fracture_marks.load`` (one reader for both projects,
corridor-finder DECISIONS 8.4). It refuses rather than guesses: another
schema, coordinates that are not RAS (Slicer's own markups default to LPS,
which would put every mark on the wrong side), units that are not mm, an
unknown bone or side. What this adds is only what the measurement needs:
the file for a case whatever alias it was saved under, and each fracture
fitted as its own plane (``corridor_engine.fracture.fit_plane``), so a
sacral and a ramus fracture on the same side are never fitted as one; a set
too small or too nearly on one line to define a plane is reported, never
fitted.

The marks stay on the workstation, outside the repo (DECISIONS 8.1).
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import corridor_engine  # noqa: F401
except ImportError:  # run from a checkout without the engine installed
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "corridor-finder"))

from corridor_engine import fracture  # noqa: E402
from corridor_engine import fracture_marks as shared  # noqa: E402

SCHEMA = shared.SCHEMA
MARKS_DIR = os.path.join(os.path.expanduser("~"), "CorridorFinderData", "marks")


class MarksRefused(ValueError):
    """The marks file was refused by the shared reader, or is ambiguous."""


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
    """The case alias and its marked fractures, each with its plane. Raises
    MarksRefused when the shared reader refuses the file."""
    try:
        case, sets = shared.load(path)
    except (ValueError, KeyError) as refused:
        raise MarksRefused(f"{os.path.basename(path)} refused: {refused}") from refused
    out = []
    for s in sets:
        points = s.points_ras_mm
        plane = fracture.fit_plane(points) if len(points) >= fracture.MIN_POINTS else None
        # The reason in the same words Corridor Finder's panel shows him
        # (fracture.why_no_plane), so the two never disagree.
        why = fracture.why_no_plane(points) if plane is None else None
        note = "" if plane is not None else f"{why or 'its points do not define a plane'}: not used"
        out.append(MarkedFracture(s.name, s.bone, s.side, plane, len(points), note))
    return case, out
