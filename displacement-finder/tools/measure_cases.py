"""Run slice 1 over the real CTPelvic1K cases on this workstation.

    python displacement-finder/tools/measure_cases.py            # the four CLINIC cases
    python displacement-finder/tools/measure_cases.py --normals 5  # and the null test on normal pelvises

**The four CLINIC fracture cases.** For each: load the CT and labels
(corridor_engine.ctpelvic1k, sides from geometry, metal refused), fit the
mirror plane both ways (corridor_engine.mirror), and compare the
pre-selection with the surgeon's reading (displacement-finder DECISIONS
7b), which is written below as the expected answer. The reference is then
confirmed *with his reading*, since that is what the confirmation is, and
the fragments of the injured hemipelvis are found against the mirrored
intact one (corridor_engine.fragments). CLINIC_0060 is bilateral, so it is
refused a transform home (DECISIONS 2.4).

**The null test on real anatomy** (``--normals N``). The first N label
files of each normal-anatomy subset (ABDOMEN, MSD Task 10, KITS19, CERVIX),
each hemipelvis against the other one mirrored. No fracture is there, so
anything found beyond the main body is invented. Labels only: these CTs
are not on the workstation.

Everything is printed; nothing is written. The CTs are read-only and stay
where they are, and what this prints goes into the README as prose, never
as committed data (DECISIONS 8.1).
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

try:
    import corridor_engine  # noqa: F401
except ImportError:  # run from a checkout without the engine installed
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "corridor-finder"))

from corridor_engine import ctpelvic1k, fragments, mirror  # noqa: E402
from corridor_engine.register import rotation_deg  # noqa: E402

DATA = r"C:\Users\oom\CorridorFinderData\ctpelvic1k"
CLINIC_LABELS = os.path.join(DATA, "labels", "ipcai2021_dataset6_Anonymized", "dataset6_CLINIC_{}_mask_4label.nii.gz")
CLINIC_IMAGES = os.path.join(DATA, "images", "dataset6_CLINIC_{}_data.nii.gz")
NORMAL_SUBSETS = {
    "ABDOMEN": "CTPelvic1K_dataset1_mask_mappingback",
    "MSD_T10": "CTPelvic1K_dataset3_mask_mappingback",
    "KITS19": "CTPelvic1K_dataset4_mask_mappingback",
    "CERVIX": "CTPelvic1K_dataset5_mask_mappingback",
}

# The surgeon's reading of the four cases (DECISIONS 7b, 2026-09-27, as
# corrected that day). "mirror_side" is the hemipelvis mirrored as the
# reference: the side without the sacral fracture. Only 0012's is fully
# intact; 0023's has a pubic body fracture and 0025's an acetabular
# fracture, so on those two the reference carries a fracture of its own.
EXPECTED = {
    "0012": {"sacral_fracture": "right", "acetabulum": None, "intact_side": "left", "mirror_intact": True},
    "0023": {"sacral_fracture": "right", "acetabulum": None, "intact_side": "left", "mirror_intact": False},
    "0025": {"sacral_fracture": "left", "acetabulum": "right", "intact_side": "right", "mirror_intact": False},
    "0060": {"sacral_fracture": "both", "acetabulum": None, "intact_side": None, "mirror_intact": False},
}


def _injured(intact_side):
    return {"left": "right", "right": "left", None: "both"}[intact_side]


def _fits(ref: mirror.MirrorReference) -> str:
    return "\n".join(
        f"    {name:<22} cost {f.cost_mm:.2f} mm, self-symmetry p50/p90 {f.self_symmetry_p50_mm:.2f}/"
        f"{f.self_symmetry_p90_mm:.2f} mm, tilt {f.tilt_deg:.1f} deg"
        + (f"  REFUSED: {f.refused}" if f.refused else "")
        for name, f in ref.fits.items())


def _fragment_lines(found: fragments.FragmentSet) -> str:
    if found.refused:
        return f"    refused: {found.refused}"
    lines = [f"    floor {found.residual_floor_mm:.2f} mm, inlier {found.inlier_mm:.2f} mm, "
             f"plane uncertainty {found.plane_uncertainty_mm:.2f} mm ({found.reference}, {found.reference_choice})"]
    for f in found.fragments:
        lines.append(
            f"    body {f.index}: {f.volume_cm3:.1f} cm3, travel home {f.travel_mm:.1f} mm "
            f"(rotation {rotation_deg(f.to_reference):.1f} deg), off its parent {f.relative_travel_mm:.1f} mm, "
            f"residual p90 {f.residual_mm:.2f} mm{', below floor' if f.below_floor else ''}"
            f"{', at the articular surface' if f.articular else ''}")
    for c in found.rejected:
        lines.append(f"    not promoted ({c.volume_cm3:.1f} cm3, {c.relative_travel_mm:.1f} mm off): {'; '.join(c.reasons)}")
    lines += [f"    warning: {w}" for w in found.warnings]
    if found.to_reference_unvalidated:
        lines.append(f"    no virtual reduction: {found.to_reference_unvalidated}")
    return "\n".join(lines)


def clinic(case: str) -> str:
    start = time.time()
    expected = EXPECTED[case]
    try:
        loaded = ctpelvic1k.load_case(CLINIC_LABELS.format(case), CLINIC_IMAGES.format(case))
    except ctpelvic1k.CaseRefused as refused:
        return f"CLINIC_{case}: refused at load: {refused}"
    ref = mirror.fit_reference(loaded.labels)
    fractured = expected["sacral_fracture"] is not None
    agrees = ref.sacrum_fractured_preselected == fractured
    out = [f"CLINIC_{case}  ({loaded.note})",
           _fits(ref),
           f"    {ref.preselection_sentence()}",
           f"    surgeon: sacral fracture {expected['sacral_fracture'] or 'none'} -> pre-selection "
           f"{'AGREES' if agrees else 'DISAGREES'}; reference spread over the hemipelvis "
           f"{ref.disagreement_mm:.2f} mm (p90)"]
    out += [f"    warning: {w}" for w in ref.warnings]
    try:
        confirmed = mirror.confirm(ref, sacrum_fractured=fractured)
    except mirror.MirrorRefused as refused:
        out.append(f"    confirmation refused: {refused}")
        return "\n".join(out)
    out.append(f"    confirmed with the surgeon's reading: {confirmed.sentence()}")
    injured = _injured(expected["intact_side"])
    # The CTPelvic1K labels have no femur. The CT heuristic femur is not
    # validated, so it is not used: the ring minimum applies everywhere and
    # the result says so (fragments.articular_surface).
    articular = None if injured == "both" else fragments.articular_surface(loaded.labels, injured)
    try:
        found = fragments.find_fragments(loaded.labels, confirmed, injured, articular)
    except ValueError as failed:
        out.append(f"    {injured} hemipelvis: fragments not measured ({failed})")
        return "\n".join(out)
    out.append(f"    {injured} hemipelvis against the mirrored {expected['intact_side'] or '(none)'} side "
               f"(surgeon: acetabulum {expected['acetabulum'] or 'no'}; articular surface "
               f"{'located' if articular is not None else 'not located'}):")
    if expected["intact_side"] is not None and not expected["mirror_intact"]:
        out.append(f"    note: the surgeon read a fracture in the mirrored {expected['intact_side']} side as well, so the "
                   "reference is not an intact hemipelvis here")
    out.append(_fragment_lines(found))
    out.append(f"    ({time.time() - start:.0f} s)")
    return "\n".join(out)


def normal(path: str) -> str:
    name = os.path.basename(path).replace("_mask_4label.nii.gz", "")
    try:
        loaded = ctpelvic1k.load_case(path)
        ref = mirror.fit_reference(loaded.labels)
    except (ctpelvic1k.CaseRefused, mirror.MirrorRefused, ValueError) as refused:
        return f"{name}: not measured ({refused})"
    # A normal pelvis: the surgeon has not read these, so the pre-selection
    # stands in for his confirmation, and the reference used is recorded.
    fractured = ref.sacrum_fractured_preselected
    try:
        confirmed = mirror.confirm(ref, sacrum_fractured=fractured, reference=ref.reference_preselected)
    except mirror.MirrorRefused as refused:
        return f"{name}: no reference ({refused})"
    rows = []
    for side in ("right", "left"):
        try:
            found = fragments.find_fragments(loaded.labels, confirmed, side)
        except ValueError as failed:
            rows.append(f"{name} {side}: NOT MEASURED ({failed})")
            continue
        bodies = len(found.fragments)
        rows.append(f"{name} {side}: {'ONE BODY' if bodies == 1 else f'{bodies} BODIES'}; floor "
                    f"{found.residual_floor_mm:.2f} mm, main body travels {found.fragments[0].travel_mm:.1f} mm, "
                    f"plane uncertainty {found.plane_uncertainty_mm:.1f} mm, {confirmed.reference}; "
                    f"{len(found.rejected)} not promoted; {found.unexplained_cm3:.1f} cm3 carried home by no body "
                    f"({100 * found.unexplained_share:.0f}% of the surface unexplained)"
                    + "".join(f"\n      extra body {f.index}: {f.volume_cm3:.1f} cm3, {f.relative_travel_mm:.1f} mm off"
                              for f in found.fragments[1:]))
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--normals", type=int, default=0, help="null test on the first N label files of each normal subset")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cases", default=",".join(EXPECTED), help="CLINIC case numbers, comma-separated")
    args = parser.parse_args()

    cases = [c for c in args.cases.split(",") if c]
    normals = []
    for folder in NORMAL_SUBSETS.values():
        normals += sorted(glob.glob(os.path.join(DATA, "labels", folder, "*.nii.gz")))[: args.normals]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        clinic_jobs = [pool.submit(clinic, c) for c in cases]
        normal_jobs = [pool.submit(normal, p) for p in normals]
        for job in clinic_jobs:
            print(job.result(), flush=True)
            print()
        if normal_jobs:
            print("NULL TEST: normal pelvises, each hemipelvis against the other mirrored")
            results = [job.result() for job in normal_jobs]
            for r in results:
                print("  " + r.replace("\n", "\n  "))
            lines = [line for r in results for line in r.split("\n") if line.startswith(("dataset",))]
            one = sum("ONE BODY" in line for line in lines)
            measured = sum(("ONE BODY" in line or "BODIES" in line) for line in lines)
            failed = sum("NOT MEASURED" in line for line in lines)
            print(f"  one body in {one} of {measured} hemipelvises measured; {failed} could not be measured")


if __name__ == "__main__":
    main()
