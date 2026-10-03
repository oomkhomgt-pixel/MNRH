"""Planned screws as a DICOM Segmentation (SEG) on the patient's own CT, for
navigation systems to import (Brainlab Elements and Spine & Trauma read DICOM
SEG; DECISIONS.md 8.3).

Each screw is one segment: the cylinder of its diameter from where it
crosses the entry cortex to its tip, as validate.py placed it, rasterised on
the original CT series' own pixel grid. The SEG references every slice of
that series and shares its patient, study and frame of reference, which is
what lets the receiving system put it back on the same images. Nothing here
decides whether a screw is safe: that was decided before export.

Coordinates: Corridor Finder works in Slicer's RAS (x right, y anterior);
DICOM is LPS (x left, y posterior), so x and y change sign on the way out.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

SOFTWARE = "Corridor Finder"


@dataclass
class ScrewObject:
    label: str  # shown in the navigation system, e.g. "LC-2 right 7.3 x 120 mm"
    start_ras: Sequence[float]  # where it crosses the entry cortex
    tip_ras: Sequence[float]
    diameter_mm: float


def _ras_to_lps(p) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    return np.array([-p[0], -p[1], p[2]])


def _sorted_series(datasets) -> Tuple[list, np.ndarray, np.ndarray, np.ndarray]:
    """The slices of one CT series in order along their normal, with the
    row and column directions and the normal."""
    first = datasets[0]
    iop = np.asarray(first.ImageOrientationPatient, dtype=float)
    row, col = iop[:3], iop[3:]
    normal = np.cross(row, col)
    for ds in datasets:
        if not np.allclose(np.asarray(ds.ImageOrientationPatient, dtype=float), iop, atol=1e-4):
            raise ValueError("the CT series' slices are not all in one orientation")
        if ds.FrameOfReferenceUID != first.FrameOfReferenceUID or ds.SeriesInstanceUID != first.SeriesInstanceUID:
            raise ValueError("the slices given are not one CT series")
    ordered = sorted(datasets, key=lambda ds: float(np.dot(np.asarray(ds.ImagePositionPatient, dtype=float), normal)))
    return ordered, row, col, normal


def rasterise(datasets, screws: Sequence[ScrewObject]) -> Tuple[list, np.ndarray]:
    """The ordered slices and a (slices, rows, columns, screws) boolean mask:
    a pixel is in a screw when its centre is within the screw's radius of
    the screw's axis, between its start and its tip."""
    ordered, row, col, normal = _sorted_series(datasets)
    rows, cols = int(ordered[0].Rows), int(ordered[0].Columns)
    dr, dc = (float(v) for v in ordered[0].PixelSpacing)  # between rows, between columns
    mask = np.zeros((len(ordered), rows, cols, len(screws)), dtype=bool)
    rr, cc = np.mgrid[0:rows, 0:cols]
    for k, screw in enumerate(screws):
        a, b = _ras_to_lps(screw.start_ras), _ras_to_lps(screw.tip_ras)
        ab = b - a
        length2 = float(ab @ ab)
        if length2 <= 0:
            raise ValueError(f"{screw.label}: the screw has no length")
        r = float(screw.diameter_mm) / 2.0
        lo, hi = sorted((float(a @ normal), float(b @ normal)))
        for z, ds in enumerate(ordered):
            ipp = np.asarray(ds.ImagePositionPatient, dtype=float)
            depth = float(ipp @ normal)
            if depth < lo - r - 1e-6 or depth > hi + r + 1e-6:
                continue
            centres = (ipp[None, None, :] + cc[..., None] * dc * row[None, None, :]
                       + rr[..., None] * dr * col[None, None, :])
            t = np.clip(((centres - a) @ ab) / length2, 0.0, 1.0)
            closest = a + t[..., None] * ab
            inside = np.linalg.norm(centres - closest, axis=-1) <= r
            # Between the start and the tip, not rounded over their ends.
            along = (centres - a) @ ab / length2
            mask[z, :, :, k] = inside & (along >= 0.0) & (along <= 1.0)
    return ordered, mask


def write_screws_seg(datasets, screws: Sequence[ScrewObject], path: str, *, software_version: str = "0.1.0",
                     colours_lab: Optional[Sequence[Tuple[float, float, float]]] = None) -> dict:
    """Write the screws as one DICOM SEG referencing ``datasets`` (the CT
    series as pydicom datasets, every slice). Returns a summary: the
    series and frame of reference it references and the voxels per screw."""
    import highdicom as hd
    from pydicom.sr.codedict import codes

    if not screws:
        raise ValueError("no screws to export")
    ordered, mask = rasterise(datasets, screws)
    if int(ordered[0].Columns) % 8:
        # Brainlab's conformance statement: a BINARY segmentation whose
        # Columns is not a multiple of 8 is not read.
        raise ValueError(f"the CT has {ordered[0].Columns} columns, not a multiple of 8, which Brainlab refuses "
                         "for a binary segmentation")
    empty = [s.label for k, s in enumerate(screws) if not mask[..., k].any()]
    if empty:
        raise ValueError(f"these screws fall outside the CT: {empty}")
    # Suggested by the software, chosen and adjusted by the surgeon.
    algorithm = hd.AlgorithmIdentificationSequence(
        name=SOFTWARE, version=software_version, family=codes.cid7162.ManualProcessing)
    descriptions = []
    for k, screw in enumerate(screws):
        kw = dict(
            segment_number=k + 1,
            segment_label=screw.label[:64],
            segmented_property_category=codes.SCT.PhysicalObject,
            segmented_property_type=codes.SCT.Screw,
            algorithm_type=hd.seg.SegmentAlgorithmTypeValues.SEMIAUTOMATIC,
            algorithm_identification=algorithm,
        )
        if colours_lab is not None:
            kw["display_color"] = hd.color.CIELabColor(*colours_lab[k])
        descriptions.append(hd.seg.SegmentDescription(**kw))
    seg = hd.seg.Segmentation(
        source_images=ordered,
        pixel_array=mask,
        segmentation_type=hd.seg.SegmentationTypeValues.BINARY,
        segment_descriptions=descriptions,
        series_instance_uid=hd.UID(),
        series_number=9001,
        sop_instance_uid=hd.UID(),
        instance_number=1,
        manufacturer=SOFTWARE,
        manufacturer_model_name=SOFTWARE,
        software_versions=software_version,
        device_serial_number="none",
        content_label="SCREWS",
        content_description="Planned screws (Corridor Finder), entry cortex to tip",
        content_creator_name="Corridor^Finder",
    )
    seg.save_as(path)
    return {
        "path": path,
        "series_referenced": str(ordered[0].SeriesInstanceUID),
        "frame_of_reference": str(ordered[0].FrameOfReferenceUID),
        "voxels": {s.label: int(mask[..., k].sum()) for k, s in enumerate(screws)},
    }
