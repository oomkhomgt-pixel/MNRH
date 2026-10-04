"""Measure the error bound of the congruence fit per displacement, on phantoms (DECISIONS 7d.2).

    python displacement-finder/tools/phantom_bound.py --workers 3

Runs the family of recovery phantoms behind congruence.PHANTOM_BOUND_TABLE_MM
(1.5 mm voxels, the phantom's own joint widths as targets, as the tests use):

- slice 1b's family: each sacral fracture (right, left, both) hinged 2-3
  degrees and slid 1-1.5 mm, 6 mm up, back or forward, or 4 mm down; the
  iliac wing moved 5 mm, or opened 2-3 mm and slid 4-6 mm along its
  fracture; the crushed sacral fracture (cancellous bone, or rim and all);
- the same fractures displaced 5, 10, 15, 20, 25 and 30 mm, with rotation:
  each sacral fracture hinged 3 degrees and slid up or back, both sides at
  once (right up, left back), and the iliac wing opened 2 mm, turned 3
  degrees about its fracture's normal and slid laterally or forward;
- the impacted sacral fractures (4 and 6 mm, the band twice
  fracture_surface.IMPACTION_MARGIN_HU), found from the CT;

each unilateral one from the exact start and from a mirror start 5 mm and 3
degrees off. For every region that reports a number it prints how far it
was displaced (RegionFit.displacement_mm) and where it lands (the tests'
own landing: the worst distance, before rounding onto the grid, between
where the fit puts a point of one side and where it belongs once the other
side is put where it belongs). Then, per kind of region, at each
displacement of congruence.PHANTOM_DISPLACEMENTS_MM, the worst landing of a
region displaced between the displacements either side of it (with the one
landing slice 1b measured and kept, KEPT), the table that follows from it
(rounded up to half a millimetre, a displacement with none given the next
one's, never smaller than at a smaller displacement, the SI joint the
largest of all kinds), and the travel limit: the furthest displacement at
which a region of each kind reported a number, rounded up to half a
millimetre. Nothing is written; the table goes into congruence.py and the
README by hand.

The landing a region reports does not depend on the table: whether a region
reports a number depends on its own reasons and on PHANTOM_TRAVEL_MM, not on
the bound's value, so the table can be measured with any table in place.
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "corridor-finder")
try:
    import corridor_engine  # noqa: F401
except ImportError:  # run from a checkout without the engine installed
    sys.path.insert(0, ENGINE)

import numpy as np  # noqa: E402

from corridor_engine import congruence as cg  # noqa: E402
from corridor_engine import fracture_surface as fsm  # noqa: E402
from corridor_engine import mirror, si_joint  # noqa: E402
from corridor_engine import phantoms as ph  # noqa: E402
from corridor_engine import segmentation as seg  # noqa: E402
from corridor_engine.landmarks import detect_landmarks  # noqa: E402
from corridor_engine.volume import Volume  # noqa: E402

WIDER_MM = (5.0, 10.0, 15.0, 20.0, 25.0, 30.0)
KINDS = ("fracture", "symphysis", "si")
# Landings measured before and kept: slice 1b kept the symphysis at the
# 6.26 mm an earlier fit measured on the half-crushed rim (the right sacral
# fracture hinged 3 degrees and slid 1.5 mm), which the present fit no longer
# reads a number at. Kept at 4.9 mm, the displacement the same phantom's
# fracture reads uncrushed, so the bound is not lowered below it.
KEPT = [("slice 1b, an earlier fit on the half-crushed rim (kept)", "symphysis", 4.9, 6.26)]


def _tests():
    """The congruence tests' own helpers (landing, truth, starts), so the
    bound is measured exactly as the tests check it."""
    path = os.path.join(ENGINE, "tests", "python", "test_congruence.py")
    spec = importlib.util.spec_from_file_location("congruence_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _own_targets():
    phantom = ph.fractured_pelvis()
    vol = Volume(phantom.intact_labels, phantom.spacing, phantom.origin)
    widths = si_joint.measure_joint_widths(vol, detect_landmarks(vol))
    return {"si_target_mm": {"right": widths["left"].measured_mm, "left": widths["right"].measured_mm},
            "symphysis_target_mm": cg.symphysis_gap(vol)[0]}


def family():
    """(case name, kind, arguments) for every phantom of the family."""
    cases = []
    sacral_1b = [("right", 3.0, (0.0, 1.5, 0.0)), ("left", 3.0, (0.0, -1.0, 1.0))]
    for side in ("right", "left"):
        sacral_1b += [(side, 3.0, (0.0, 0.0, 6.0)), (side, 3.0, (0.0, 6.0, 0.0)), (side, 3.0, (0.0, -6.0, 0.0)),
                      (side, 3.0, (0.0, 0.0, -4.0)), (side, 2.0, (0.0, 1.5, 0.0))]
    wider = [(side, 3.0, move) for d in WIDER_MM for side in ("right", "left")
             for move in ((0.0, 0.0, d), (0.0, -d, 0.0))]
    for side, hinge, move in sacral_1b + wider:
        for start in ("exact", "wrong"):
            cases.append((f"sacral {side} hinge {hinge:.0f} slid {move} from the {start} start", "sacral",
                          (side, hinge, move, start)))
    bilateral = [((3.0, 2.0), ((0.0, 1.5, 0.0), (0.0, -1.0, 1.0))), ((3.0, 2.0), ((0.0, 0.0, 6.0), (0.0, 6.0, 0.0))),
                 ((3.0, 2.0), ((0.0, -6.0, 0.0), (0.0, 0.0, 4.0)))]
    bilateral += [((3.0, 2.0), ((0.0, 0.0, d), (0.0, -d, 0.0))) for d in WIDER_MM]
    for hinge, moves in bilateral:
        cases.append((f"bilateral hinged {hinge} slid {moves}", "bilateral", (hinge, moves)))
    normal = np.array([0.2, 0.3, 1.0]) / np.linalg.norm([0.2, 0.3, 1.0])
    medial = np.cross(normal, [0.0, 1.0, 0.0])
    medial /= np.linalg.norm(medial)
    forward = np.cross(normal, -medial)
    forward /= np.linalg.norm(forward)
    iliac = [((2.0, 1.5, 4.3), 0.0), (tuple(3.0 * normal + 6.0 * medial), 0.0), (tuple(2.0 * normal + 4.0 * medial), 0.0)]
    iliac += [(tuple(2.0 * normal + d * direction), 3.0) for d in WIDER_MM for direction in (-medial, forward)]
    for move, turn in iliac:
        for start in ("exact", "wrong"):
            cases.append((f"iliac moved {tuple(round(float(v), 2) for v in move)} turned {turn:.0f} deg from the "
                          f"{start} start", "iliac", (move, turn, start)))
    for kind in ("cancellous", "rim"):
        cases.append((f"sacral right crushed ({kind}) from the wrong start", "crushed", (kind,)))
    for depth in (4.0, 6.0):
        for start in ("exact", "wrong"):
            cases.append((f"impacted sacral {depth:.0f} mm from the {start} start", "impacted", (depth, start)))
    return cases


def run(case):
    name, kind, args = case
    tc = _tests()
    own = _own_targets()
    started = time.time()
    if kind == "sacral":
        side, hinge, move, start = args
        phantom = ph.sacral_fractured_pelvis(side=side, hinge_deg=hinge, translate_mm=move)
        vol = Volume(phantom.labels, phantom.spacing, phantom.origin)
        found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
        truth = np.linalg.inv(phantom.moved_by)
        hip = phantom.labels == (seg.HIP_R if side == "right" else seg.HIP_L)
        femur = phantom.labels == (seg.FEMUR_R if side == "right" else seg.FEMUR_L)
        begin = truth if start == "exact" else tc._wrong(vol.mask_voxel_centers_world(hip)) @ truth
        fit = cg.fit_reduction(vol, side, found, tc._fragment_set(side, [tc._body(0, None, hip, begin)]),
                               fsm.split_sacrum(vol, found), **own)
        truth_of = tc._truth(vol, [(hip | phantom.lateral_fragment | femur, truth)])
    elif kind == "bilateral":
        hinge, moves = args
        phantom = ph.bilateral_sacral_fractured_pelvis(hinge_deg=hinge, translate_mm=moves)
        vol = Volume(phantom.labels, phantom.spacing, phantom.origin)
        found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
        fit = cg.fit_reduction(vol, "both", found, None, fsm.split_sacrum(vol, found), **own)
        moving = []
        for side, hip_id, femur_id in (("right", seg.HIP_R, seg.FEMUR_R), ("left", seg.HIP_L, seg.FEMUR_L)):
            mask = (phantom.labels == hip_id) | phantom.lateral_fragments[side] | (phantom.labels == femur_id)
            moving.append((mask, np.linalg.inv(phantom.moved_by[side])))
        truth_of = tc._truth(vol, moving)
    elif kind == "iliac":
        move, turn, start = args
        normal = np.array([0.2, 0.3, 1.0]) / np.linalg.norm([0.2, 0.3, 1.0])
        phantom = ph.fractured_pelvis(translate_mm=move, rotate_deg=turn, rotate_axis=tuple(normal))
        vol = Volume(phantom.labels, phantom.spacing, phantom.origin)
        main = (phantom.labels == seg.HIP_R) & ~phantom.fragment
        begin = (phantom.to_reference if start == "exact"
                 else tc._wrong(vol.mask_voxel_centers_world(phantom.fragment)) @ phantom.to_reference)
        bodies = tc._fragment_set("right", [tc._body(0, None, main, np.eye(4)), tc._body(1, 0, phantom.fragment, begin)])
        found = fsm.find_fracture_surfaces(vol, bones=(seg.HIP_R,), fragment_sets=[bodies])
        fit = cg.fit_reduction(vol, "right", found, bodies, {}, **own)
        truth_of = tc._truth(vol, [(phantom.fragment, phantom.to_reference)])
    elif kind == "crushed":
        phantom, vol, truth, _ = tc._comminuted(args[0])
        found = fsm.find_fracture_surfaces(vol, bones=(seg.SACRUM,))
        hip = vol.array == seg.HIP_R
        begin = tc._wrong(vol.mask_voxel_centers_world(hip)) @ truth
        fit = cg.fit_reduction(vol, "right", found, tc._fragment_set("right", [tc._body(0, None, hip, begin)]),
                               fsm.split_sacrum(vol, found), **own)
        moving = hip | (phantom.lateral_fragment & (vol.array > 0)) | (vol.array == seg.FEMUR_R)
        truth_of = tc._truth(vol, [(moving, truth)])
    else:
        depth, start = args
        reference = ph.fractured_pelvis()
        confirmed = mirror.confirm(mirror.fit_reference(Volume(reference.labels, reference.spacing, reference.origin)),
                                   sacrum_fractured=True)
        impacted = ph.impacted_sacral_pelvis(depth_mm=depth, band_excess_hu=2.0 * fsm.IMPACTION_MARGIN_HU)
        vol = Volume(impacted.labels, impacted.spacing, impacted.origin)
        found = fsm.find_fracture_surfaces(vol, mirror=confirmed, ct=Volume(impacted.ct, impacted.spacing, impacted.origin),
                                           bones=(seg.SACRUM,), injured="right")
        phantom = impacted.sacral
        truth = np.linalg.inv(phantom.moved_by)
        hip = phantom.labels == seg.HIP_R
        begin = truth if start == "exact" else tc._wrong(vol.mask_voxel_centers_world(hip)) @ truth
        fit = cg.fit_reduction(vol, "right", found, tc._fragment_set("right", [tc._body(0, None, hip, begin)]),
                               fsm.split_sacrum(vol, found, confirmed), **own)
        truth_of = tc._truth(vol, [(hip | phantom.lateral_fragment | (phantom.labels == seg.FEMUR_R), truth)])
    landing = tc._landing(fit, truth_of)
    rows = [(r.name, r.kind, bool(np.isfinite(r.residual_mm)), float(r.displacement_mm), float(r.travel_mm),
             float(landing[k]), float(r.residual_mm), r.unconstrained[:90]) for k, r in fit.regions.items()]
    return name, rows, time.time() - started


def table(samples):
    """Per kind, (measured worst per displacement with its case, the table,
    and the furthest displacement at which a region of that kind reported a
    number, rounded up to half a millimetre: the travel limit)."""
    nodes = cg.PHANTOM_DISPLACEMENTS_MM
    measured, tables = {}, {}
    for kind in KINDS:
        worst = []
        for k, d in enumerate(nodes):
            lo = nodes[max(k - 1, 0)]
            hi = nodes[min(k + 1, len(nodes) - 1)]
            here = [(landing, case) for case, kind_, disp, landing in samples if kind_ == kind and lo <= disp <= hi]
            worst.append(max(here) if here else (float("nan"), ""))
        measured[kind] = worst
    for kind in KINDS:
        values = [w[0] for w in measured[kind]]
        if kind == "si":  # never measured where it pins a hip: the largest of all kinds
            values = [np.nanmax([measured[k][i][0] for k in KINDS]) if any(np.isfinite(measured[k][i][0])
                                                                        for k in KINDS) else float("nan")
                      for i in range(len(nodes))]
        rounded = [math.ceil(v * 2.0) / 2.0 if np.isfinite(v) else float("nan") for v in values]
        for i in range(len(rounded) - 2, -1, -1):  # a displacement with none measured takes the next one's
            if not np.isfinite(rounded[i]):
                rounded[i] = rounded[i + 1]
        for i in range(1, len(rounded)):
            if not np.isfinite(rounded[i]):
                rounded[i] = rounded[i - 1]
        tables[kind] = tuple(float(np.maximum.accumulate(rounded)[i]) for i in range(len(rounded)))
    furthest = {kind: max([disp for _, kind_, disp, _ in samples if kind_ == kind], default=float("nan"))
                for kind in KINDS}
    # The SI joint is never measured where it pins a hip (its regions here
    # have both sides on one unit and land 0): the largest of the others.
    furthest["si"] = max(furthest["fracture"], furthest["symphysis"])
    travel = {kind: min(math.ceil(furthest[kind] * 2.0) / 2.0, cg.PHANTOM_DISPLACEMENTS_MM[-1]) for kind in KINDS}
    return measured, tables, furthest, travel


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    cases = family()
    samples = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for name, rows, seconds in pool.map(run, cases):
            print(f"{name} ({seconds:.0f} s)")
            for region, kind, finite, disp, travel, landing, residual, why in rows:
                if finite:
                    print(f"  {region} ({kind}): displaced {disp:.2f} mm (moved {travel:.2f}), lands {landing:.2f} mm, "
                          f"reports {residual:.2f} mm")
                    if kind in KINDS:
                        samples.append((name, kind, disp, landing))
                else:
                    print(f"  {region} ({kind}): inf ({why}...); lands {landing:.2f} mm")
            sys.stdout.flush()
    samples += KEPT
    measured, tables, furthest, travel = table(samples)
    print("\nWorst landing per displacement (the regions displaced between the displacements either side):")
    for kind in KINDS:
        print(f"  {kind}:")
        for d, (value, case) in zip(cg.PHANTOM_DISPLACEMENTS_MM, measured[kind]):
            print(f"    {d:4.0f} mm: {value:.2f} mm" + (f" ({case})" if case else " (none)"))
    print("\nPHANTOM_BOUND_MEASURED_MM = {"
          + ", ".join(f'"{k}": ({", ".join("np.nan" if not np.isfinite(v) else f"{v:.2f}" for v, _ in measured[k])})'
                      for k in KINDS) + "}")
    print("PHANTOM_BOUND_TABLE_MM = {" + ", ".join(f'"{k}": {tables[k]}' for k in KINDS) + "}")
    print("furthest displacement at which a region reported a number: "
          + ", ".join(f"{k} {furthest[k]:.2f} mm" for k in KINDS))
    print("PHANTOM_TRAVEL_MM = {" + ", ".join(f'"{k}": {travel[k]}' for k in KINDS) + "}")
    print(f"{len(samples)} region landings from {len(cases)} fits")


if __name__ == "__main__":
    main()
