"""The symphyseal gap on normal pelvises: the reduction fit's target (DECISIONS 7c.7).

    python displacement-finder/tools/symphysis_gap.py --workers 4

The congruence fit closes a reduced symphysis to the **median symphyseal
gap measured on the 274 normal CTPelvic1K pelvises**, reported with its
range (7c.7; rejected: a textbook 4 mm). This measures it, on the label
files of the four normal-anatomy subsets (ABDOMEN, MSD Task 10, KITS19,
CERVIX), labels only.

**How the gap is measured** (corridor_engine.congruence.symphysis_gap, which
the congruence fit also measures a reduced symphysis with, so the target and
the reduced joint are read the same way), as si_joint.py measures an SI
joint:

- where the joint is: empty voxels where the nearest right hip and the
  nearest left hip lie on opposite sides (si_joint.facing), each within
  REACH_MM (si_joint's AURICULAR_MAX_MM, which keeps the space behind and
  below a joint out). Only the symphysis has the two hip bones that close;
- the gap at each of those voxels is the distance to one bone plus the
  distance to the other (si_joint's gap field, centre to centre);
- per axial level through the joint, the median gap over its voxels; the
  pelvis's gap is the **median over its levels** (the joint's typical
  width, which a fit that closes the whole joint surface aims at), with the
  90th percentile over levels alongside (si_joint's coverage percentile).

Sides are taken from geometry file by file (ctpelvic1k.load_case), since
the subsets disagree on which id is which hip. Everything is printed;
nothing is written (DECISIONS 8.1).
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

try:
    import corridor_engine  # noqa: F401
except ImportError:  # run from a checkout without the engine installed
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "corridor-finder"))

from corridor_engine import ctpelvic1k  # noqa: E402
from corridor_engine import segmentation as seg  # noqa: E402
from corridor_engine.congruence import SYMPHYSIS_REACH_MM as REACH_MM  # noqa: E402
from corridor_engine.congruence import symphysis_gap  # noqa: E402

DATA = r"C:\Users\oom\CorridorFinderData\ctpelvic1k"
NORMAL_SUBSETS = {
    "ABDOMEN": "CTPelvic1K_dataset1_mask_mappingback",
    "MSD_T10": "CTPelvic1K_dataset3_mask_mappingback",
    "KITS19": "CTPelvic1K_dataset4_mask_mappingback",
    "CERVIX": "CTPelvic1K_dataset5_mask_mappingback",
}


def measure(path: str):
    name = os.path.basename(path).replace("_mask_4label.nii.gz", "").replace(".nii.gz", "")
    try:
        loaded = ctpelvic1k.load_case(path)
    except ctpelvic1k.CaseRefused as refused:
        return name, None, f"not measured ({refused})"
    median, p90, levels = symphysis_gap(loaded.labels)
    spacing = "x".join(f"{s:.2f}" for s in loaded.labels.spacing)
    if not np.isfinite(median):
        # Arrays run from the lowest slice up (volume.py), so slice 0 is the bottom of the scan.
        lowest = loaded.labels.array[0]
        cut_off = bool(np.isin(lowest, (seg.HIP_R, seg.HIP_L)).any())
        why = ("the scan stops above it: the hip bones run off its lowest slice" if cut_off
               else f"the hip bones never come within {2 * REACH_MM:.0f} mm of each other")
        return name, None, f"no symphysis found ({why}; {levels} levels; spacing {spacing} mm)"
    return name, median, f"gap {median:.2f} mm (p90 over levels {p90:.2f}), {levels} levels, spacing {spacing} mm"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--first", type=int, default=0, help="only the first N files of each subset (0: all)")
    args = parser.parse_args()
    jobs = []
    for subset, folder in NORMAL_SUBSETS.items():
        files = sorted(glob.glob(os.path.join(DATA, "labels", folder, "*.nii.gz")))
        jobs += [(subset, f) for f in (files[: args.first] if args.first else files)]
    gaps = {subset: [] for subset in NORMAL_SUBSETS}
    unmeasured = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for (subset, _), (name, median, line) in zip(jobs, pool.map(measure, [f for _, f in jobs])):
            print(f"{subset:<8} {name}: {line}", flush=True)
            if median is None:
                unmeasured += 1
            else:
                gaps[subset].append(median)
    every = [g for values in gaps.values() for g in values]
    print()
    for subset, values in gaps.items():
        if values:
            print(f"{subset:<8} n {len(values)}: median {np.median(values):.2f} mm, range {min(values):.2f}-"
                  f"{max(values):.2f}, 5th-95th percentile {np.percentile(values, 5):.2f}-{np.percentile(values, 95):.2f}")
    if every:
        print(f"ALL      n {len(every)} of {len(jobs)} files ({unmeasured} not measured): median {np.median(every):.2f} mm, "
              f"range {min(every):.2f}-{max(every):.2f}, 5th-95th percentile {np.percentile(every, 5):.2f}-"
              f"{np.percentile(every, 95):.2f}")


if __name__ == "__main__":
    main()
