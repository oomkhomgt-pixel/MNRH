"""How much room there is around a planned entry point.

A percutaneous entry is found by hand, under fluoroscopy, so one point is
not enough to act on: a corridor that tolerates 1 mm of drift is a very
different operation from one that tolerates 6 mm. This slides the whole
screw sideways, keeping its direction, over a grid in the plane across the
screw, and asks at each offset the same question the plan asks.

Every offset reported safe is one validate.validate_screw accepted: no
breach, and none of the warnings that say the screw could not be placed as
the corridor intends. A cheap pass over the plain distance field rules out
the offsets that cannot pass, so only plausible ones are checked in full.
It only ever rules offsets out, so the area is never larger than the rule
allows, though it can be smaller by about a grid step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import cortex
from .validate import choose_implant_length, validate_screw
from .volume import Volume

# Warnings that mean the screw is not placeable at that offset, so it is not
# part of the safe area even where its clearance is fine (validate.py already
# calls the two entry ones a breach).
BLOCKING_WARNINGS = {"no_bone", "entry_cortex_not_found", "entry_not_outer", "exit_not_found", "exit_not_outer", "no_catalog_length"}


@dataclass
class EntryArea:
    """Where a planned screw's entry may sit, as a grid across the screw."""

    entry_xyz: Tuple[float, float, float]  # the planned entry handle, the grid's centre
    direction: Tuple[float, float, float]  # the screw's direction, unchanged
    axis_1: Tuple[float, float, float]  # in-plane grid axis (world)
    axis_2: Tuple[float, float, float]
    axis_1_words: Tuple[str, str]  # what + and - along axis_1 mean anatomically
    axis_2_words: Tuple[str, str]
    step_mm: float
    half_extent_mm: float
    safe: np.ndarray  # bool grid [axis_2, axis_1], True where the screw passes
    entry_points_xyz: np.ndarray  # (N, 3) cortex crossings of the safe screws
    room_mm: float  # radius of the largest circle of safe entries around the plan
    room_is_at_least: bool  # True when the grid ran out before any unsafe offset
    extents_mm: Dict[str, float] = field(default_factory=dict)  # word -> how far that way
    planned_is_safe: bool = True

    def sentence(self) -> str:
        """The room in words. "Moving" slides the whole screw with the entry,
        keeping its direction, so the tip moves too and must stay safe."""
        if not self.planned_is_safe:
            return "the planned entry itself does not pass the check"
        parts = ", ".join(f"{mm:.0f} mm {word}" for word, mm in self.extents_mm.items())
        if self.room_is_at_least:
            circle = f"a safe circle of at least {self.room_mm:.0f} mm around it (as far as this was measured)"
        elif self.room_mm >= self.step_mm:
            circle = f"a safe circle of {self.room_mm:.1f} mm around it"
        else:
            circle = "no room in every direction"
        return f"{circle}; sliding the screw parallel, the entry can move {parts}"


def _in_plane_axes(u: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Two perpendicular axes across the screw. The first is the most
    cephalad direction across it, or the most anterior one when the screw
    itself runs up the patient."""
    reference = np.array([0.0, 0.0, 1.0]) if abs(float(u[2])) < 0.9 else np.array([0.0, 1.0, 0.0])
    axis_1 = reference - float(np.dot(reference, u)) * u
    axis_1 = axis_1 / np.linalg.norm(axis_1)
    axis_2 = np.cross(u, axis_1)
    return axis_1, axis_2 / np.linalg.norm(axis_2)


_AXIS_WORDS = (
    ("toward the patient's right", "toward the patient's left"),
    ("anterior", "posterior"),
    ("toward the head", "toward the feet"),
)


def _words(v: np.ndarray) -> Tuple[str, str]:
    """What moving along +v and -v means anatomically (RAS world). A
    direction between two anatomical axes is named by both."""
    order = np.argsort(np.abs(v))[::-1]
    names = []
    for axis in order[:2]:
        if abs(v[axis]) < 0.4 * abs(v[order[0]]):
            break
        forward, backward = _AXIS_WORDS[axis]
        names.append((forward, backward) if v[axis] > 0 else (backward, forward))
    return tuple(_join(n[i] for n in names) for i in (0, 1))


def _join(words) -> str:
    """"toward the head" and "toward the patient's left" read better joined
    as "toward the head and the patient's left"."""
    first, *rest = words
    joined = first
    for word in rest:
        joined += " and " + (word[len("toward the "):] if first.startswith("toward the ") and word.startswith("toward the ") else word)
    return joined


def safe_entry_area(
    entry,
    target,
    diameter_mm: float,
    margin_mm: float,
    edt_volume: Volume,
    labels_volume: Optional[Volume],
    *,
    tip_rule: str = "inside",
    catalog_lengths_mm: Optional[Sequence[float]] = None,
    step_mm: float = 1.0,
    half_extent_mm: float = 10.0,
) -> EntryArea:
    """Slide the planned screw sideways over a grid and report where it still
    passes validate_screw. The arguments are the screw's, as the plan holds
    it. The room reported is conservative by one step, since the grid only
    knows what it sampled."""
    entry = np.asarray(entry, dtype=float)
    target = np.asarray(target, dtype=float)
    u = cortex.unit3(target - entry)
    axis_1, axis_2 = _in_plane_axes(u)
    radius = diameter_mm / 2.0
    # The stretch next to the entry cortex where the exemption applies, at
    # its longest: the cheap pass must not judge the screw there.
    zone = 2.0 * (radius + margin_mm + cortex.CORTEX_DEPTH_TOLERANCE_MM)

    n = int(np.floor(half_extent_mm / step_mm + 1e-9))
    coords = np.arange(-n, n + 1) * step_mm
    safe = np.zeros((len(coords), len(coords)), dtype=bool)
    points: List[np.ndarray] = []

    for i2, c2 in enumerate(coords):
        for i1, c1 in enumerate(coords):
            shift = c1 * axis_1 + c2 * axis_2
            if not _could_pass(entry + shift, target + shift, radius, margin_mm, edt_volume, u, zone, tip_rule, catalog_lengths_mm):
                continue
            v = validate_screw(
                entry + shift, target + shift, diameter_mm, margin_mm, edt_volume, labels_volume,
                tip_rule=tip_rule, catalog_lengths_mm=catalog_lengths_mm,
            )
            if v.breach or BLOCKING_WARNINGS & set(v.warning_codes):
                continue
            safe[i2, i1] = True
            points.append(np.asarray(v.start_xyz, dtype=float))

    grid_1, grid_2 = np.meshgrid(coords, coords)
    unsafe_distances = np.hypot(grid_1, grid_2)[~safe]
    axis_1_words, axis_2_words = _words(axis_1), _words(axis_2)
    extents: Dict[str, float] = {}
    for axis, words in ((1, axis_1_words), (2, axis_2_words)):
        for sign, word in ((1, words[0]), (-1, words[1])):
            extents[word] = _reach(safe, step_mm, axis, sign)
    return EntryArea(
        entry_xyz=tuple(float(v) for v in entry),
        direction=tuple(float(v) for v in u),
        axis_1=tuple(float(v) for v in axis_1),
        axis_2=tuple(float(v) for v in axis_2),
        axis_1_words=axis_1_words,
        axis_2_words=axis_2_words,
        step_mm=step_mm,
        half_extent_mm=float(coords[-1]),
        safe=safe,
        entry_points_xyz=np.array(points) if points else np.zeros((0, 3)),
        room_mm=float(max(unsafe_distances.min() - step_mm, 0.0)) if unsafe_distances.size else float(coords[-1]),
        room_is_at_least=not unsafe_distances.size,
        extents_mm=extents,
        planned_is_safe=bool(safe[n, n]),
    )


def _could_pass(entry, target, radius, margin_mm, edt_volume, u, zone, tip_rule, catalog_lengths_mm) -> bool:
    """Cheap necessary condition: away from a crossed cortex the plain
    distance field alone decides, so an offset that fails there cannot pass
    the full check. Everything within an exemption zone is left to it."""
    start, _offset, problem = cortex.entry_crossing(edt_volume, entry, target)
    if problem is not None:
        return False
    to_target = float(np.sqrt(cortex.dot3(target - start, target - start)))
    if tip_rule == "through":
        end = to_target - zone  # the far cortex, and its zone, lie around the target
    elif catalog_lengths_mm is None:
        end = to_target
    else:
        chosen = choose_implant_length(to_target, "inside", catalog_lengths_mm)
        if chosen is None:
            return False  # no screw of this diameter ends before the target
        end = chosen
    if end <= zone:
        return True  # all of it is in an exemption zone; the full check decides
    s = np.arange(zone, end + 1e-9, 1.0)
    values = edt_volume.sample_trilinear(start + s[:, None] * u, order=1)
    return bool((values - radius).min() >= margin_mm)


def _reach(safe: np.ndarray, step_mm: float, axis: int, sign: int) -> float:
    """How far the entry can move along one grid direction before the first
    offset that does not pass."""
    centre = safe.shape[0] // 2
    reach = 0.0
    for k in range(1, centre + 1):
        i1, i2 = (centre + sign * k, centre) if axis == 1 else (centre, centre + sign * k)
        if not safe[i2, i1]:
            break
        reach = k * step_mm
    return reach
