"""The sacral canal and the sacral foramina, as structures a screw keeps the
full margin from (DECISIONS.md 7.4, 7.9, 7.15, 7.16; the surgeon,
2026-10-04).

The segmentation leaves both as empty space inside the sacrum, so the one
breach rule already keeps the margin from them. They are found explicitly
so that nothing else can count them as bone: neither the sacroiliac bridge
(DECISIONS.md 2) nor a marked fracture's gap (7.14), which in a Denis zone
II fracture runs straight through the foramina. Making them non-bone only
ever makes the check stricter.

Found from the sacrum's own label:
* the canal is the hole the sacrum encloses on an axial slice (the
  posterior arch closes it), within CANAL_HALF_WIDTH_MM of the midline when
  the midline is known (a hole enclosed between fracture fragments away
  from the midline is not the canal);
* the foramina are the channels through it, about a centimetre across: the
  empty space a closing of FORAMEN_CLOSING_MM bridges, kept only where
  thicker than 2 x MIN_THICKNESS_MM (a foramen is a round channel 8-10 mm
  across, a fracture gap a thin sheet).

Where a zone II fracture runs through the foramina the two are one hole,
and the shape alone cannot tell foramen from fracture: on CLINIC_0060 the
'foramina' followed the whole fracture line (7.16). So when the surgeon
says one side of the sacrum is fractured and the other is not, the
foramina of the fractured side are taken from the intact side, mirrored
across the sacral midline and widened by MIRROR_MARGIN_MM for left-right
asymmetry; what the shape found on the fractured side is not used. Which
side is intact is his call, not the shape's: the shape of the foramina
does not tell an intact side from a fractured one (on the pilot cases the
intact left of CLINIC_0023 looked more like a sheet than the fractured
left of CLINIC_0025), and mirroring a fractured side copies its fracture
and drops the real foramina. If the side he calls intact shows less than
MIN_INTACT_FORAMINA_CM3 of foramina, nothing is mirrored. The fracture gap outside
the mirrored foramina can then be crossed (7.14), the foramina cannot.
With both sides fractured there is no intact side: everything the shape
found stays protected (the safe side, which may also block crossing the
fracture next to the foramina), and the notes say so.

The surgeon may also paint foramina himself (7.17), e.g. where both sides
are fractured and nothing can be mirrored. What he paints, on any slice, is
extended front to back through the sacrum (along the anterior pelvic
plane's normal, within USER_REACH_MM), and on each side he painted, the
tool's own foramina that touch a marked fracture gap are replaced by his;
the tool's foramina away from the fracture keep their protection.

Space within NEAR_HIP_MM of a hip bone is left out: that is the sacroiliac
joint, not a foramen. Taking sacrum-labelled voxels darker than fat as well
(in case the segmentation painted into a foramen) was tried on CLINIC_0012
and dropped: it took in cancellous bone and fracture haematoma. A foramen
the segmentation filled is therefore not found on an intact side; the
panel shows what is protected so the surgeon can see that.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage as ndi

from .volume import Volume

FORAMEN_CLOSING_MM = 7.0
NEAR_HIP_MM = 8.0
MIN_THICKNESS_MM = 2.5  # an opening of this radius: sheets thinner than 5 mm drop out
CANAL_HALF_WIDTH_MM = 20.0  # the sacral canal lies within this of the midline
MIRROR_MARGIN_MM = 2.0  # a mirrored foramen is widened by this much
MIN_INTACT_FORAMINA_CM3 = 1.0  # less than this on the intact side: nothing to mirror
USER_REACH_MM = 40.0  # a painted foramen is extended this far in front and behind


def _parts(labels: Volume, sacrum_label: int, hip_labels, midline):
    """Work in a box around the sacrum, padded with empty space beyond the
    scan's edge (a distance transform does not treat the edge of the array
    as a surface: without the padding the closing invented openings along
    the edge of the scan). Returns the box's start index (it may be
    negative), its shape, the crop that puts it back on the scan, and in it:
    the sacrum, the canal, the foramina as the shape finds them, where the
    sacrum's envelope is, and the signed distance from the midline."""
    arr = labels.array
    sacrum = arr == sacrum_label
    sampling = np.array([labels.spacing[2], labels.spacing[1], labels.spacing[0]], dtype=float)
    idx = np.argwhere(sacrum)
    pad = np.ceil((FORAMEN_CLOSING_MM + NEAR_HIP_MM + MIRROR_MARGIN_MM) / sampling).astype(int) + 2
    start = idx.min(axis=0) - pad
    stop = idx.max(axis=0) + pad + 1
    lo = np.maximum(start, 0)
    hi = np.minimum(stop, arr.shape)
    widths = [(int(a), int(b)) for a, b in zip(lo - start, stop - hi)]
    box = tuple(slice(a, b) for a, b in zip(lo, hi))
    labels_box = np.pad(arr[box], widths, constant_values=0)
    crop = tuple(slice(w[0], w[0] + (b - a)) for w, a, b in zip(widths, lo, hi))
    s = labels_box == sacrum_label
    enclosed = np.zeros_like(s)
    for z in range(s.shape[0]):
        if s[z].any():
            enclosed[z] = ndi.binary_fill_holes(s[z])
    near = ndi.distance_transform_edt(~s, sampling=sampling) <= FORAMEN_CLOSING_MM
    closed = ndi.distance_transform_edt(near, sampling=sampling) > FORAMEN_CLOSING_MM
    empty = ~s & (labels_box == 0)
    holes = enclosed & empty
    if midline is not None:
        signed = _signed_distance(labels, start, s.shape, midline)
        canal = holes & (np.abs(signed) <= CANAL_HALF_WIDTH_MM)
    else:
        signed = None
        canal = holes
    foramina = ((closed & empty) | holes) & ~canal
    hips = np.isin(labels_box, list(hip_labels)) if len(hip_labels) else np.zeros_like(s)
    away = (ndi.distance_transform_edt(~hips, sampling=sampling) > NEAR_HIP_MM) if hips.any() else np.ones_like(s)
    canal &= away
    foramina &= away
    if foramina.any():
        # Opening by a ball of MIN_THICKNESS_MM, by distance transforms; the
        # canal beside it counts as room, so a foramen opening into the
        # canal keeps its mouth.
        room = foramina | canal
        core = (ndi.distance_transform_edt(room, sampling=sampling) > MIN_THICKNESS_MM) & room
        foramina &= ndi.distance_transform_edt(~core, sampling=sampling) <= MIN_THICKNESS_MM + max(labels.spacing)
    envelope = (closed | s) & away & ((labels_box == 0) | s)
    return box, crop, start, sampling, s, canal, foramina, envelope, signed, widths


def _signed_distance(labels: Volume, lo, shape, midline) -> np.ndarray:
    """Signed distance (mm) of every voxel in the box from the midline plane,
    positive on the side the normal points to (the patient's right)."""
    point, normal = (np.asarray(v, dtype=float) for v in midline)
    sx, sy, sz = labels.spacing
    ox, oy, oz = labels.origin
    z = oz + (lo[0] + np.arange(shape[0])) * sz
    y = oy + (lo[1] + np.arange(shape[1])) * sy
    x = ox + (lo[2] + np.arange(shape[2])) * sx
    return ((z[:, None, None] - point[2]) * normal[2] + (y[None, :, None] - point[1]) * normal[1]
            + (x[None, None, :] - point[0]) * normal[0])


def _mirrored(labels: Volume, lo, shape, sampling, source: np.ndarray, midline) -> np.ndarray:  # lo: the box's start
    """``source`` (a mask in the box) reflected across the midline plane,
    on the same grid, widened by MIRROR_MARGIN_MM."""
    out = np.zeros(shape, dtype=bool)
    idx = np.argwhere(source)
    if not len(idx):
        return out
    point, normal = (np.asarray(v, dtype=float) for v in midline)
    sx, sy, sz = labels.spacing
    ox, oy, oz = labels.origin
    xyz = np.stack([ox + (idx[:, 2] + lo[2]) * sx, oy + (idx[:, 1] + lo[1]) * sy, oz + (idx[:, 0] + lo[0]) * sz], axis=1)
    reflected = xyz - 2.0 * ((xyz - point) @ normal)[:, None] * normal
    k = np.rint((reflected[:, 2] - oz) / sz).astype(int) - lo[0]
    j = np.rint((reflected[:, 1] - oy) / sy).astype(int) - lo[1]
    i = np.rint((reflected[:, 0] - ox) / sx).astype(int) - lo[2]
    ok = (k >= 0) & (k < shape[0]) & (j >= 0) & (j < shape[1]) & (i >= 0) & (i < shape[2])
    out[k[ok], j[ok], i[ok]] = True
    # Close the holes nearest-neighbour rounding leaves, then widen.
    return ndi.distance_transform_edt(~out, sampling=sampling) <= MIRROR_MARGIN_MM + 0.5 * max(labels.spacing)


def protected_spaces(labels: Volume, sacrum_label: int, hip_labels=(), midline=None,
                     fractured_sides: Sequence[str] = (), user_foramina: Optional[np.ndarray] = None,
                     fracture_gap: Optional[np.ndarray] = None, ap_axis=None) -> Tuple[np.ndarray, List[str]]:
    """The sacral canal and foramina (boolean mask on the labels' grid), and
    notes saying how the foramina of each side were found. ``midline`` is
    (a point on the sacral midline plane, its unit normal pointing to the
    patient's right); ``fractured_sides`` the sides the surgeon says are
    fractured; ``user_foramina`` what he painted (labels' grid),
    ``fracture_gap`` the marked fracture gap in the sacrum, and ``ap_axis``
    the front-to-back direction his paint is extended along."""
    arr = labels.array
    out = np.zeros(arr.shape, dtype=bool)
    notes: List[str] = []
    if not (arr == sacrum_label).any():
        return out, notes
    box, crop, start, sampling, s, canal, foramina, envelope, signed, widths = _parts(
        labels, sacrum_label, tuple(hip_labels), midline)
    fractured = set(fractured_sides) if midline is not None else set()
    chosen = foramina
    if midline is not None and fractured:
        right, left = signed > 0, signed <= 0
        if fractured >= {"right", "left"}:
            notes.append("Both sides of the sacrum are fractured, so there is no intact side to take the "
                         "foramina from: everything shaped like a foramen stays protected, which may include "
                         "fracture gap next to the foramina (no screw is offered across it), unless you paint the "
                         "foramina yourself.")
        else:
            broken = "right" if "right" in fractured else "left"
            intact_name = "left" if broken == "right" else "right"
            on_broken, on_intact = (right, left) if broken == "right" else (left, right)
            voxel_cm3 = float(np.prod(labels.spacing)) / 1000.0
            if float((foramina & on_intact).sum()) * voxel_cm3 < MIN_INTACT_FORAMINA_CM3:
                notes.append(f"The {broken} sacrum is fractured, but the {intact_name} side shows almost no "
                             "foramina to mirror (check the segmentation there): everything shaped like a foramen "
                             "stays protected.")
            else:
                mirrored = _mirrored(labels, start, s.shape, sampling, foramina & on_intact, midline) & on_broken & envelope
                chosen = (foramina & on_intact) | mirrored
                notes.append(f"The {broken} sacrum is fractured: its foramina are the {intact_name} side's, mirrored "
                             f"across the midline and widened by {MIRROR_MARGIN_MM:.0f} mm; a marked fracture gap "
                             "outside them may be crossed.")
    if user_foramina is not None and user_foramina.any():
        painted = np.pad(user_foramina[box], widths, constant_values=False)
        painted = _extend_front_to_back(labels, start, painted, envelope, ap_axis) if ap_axis is not None else painted
        painted &= envelope
        gap = np.pad(fracture_gap[box], widths, constant_values=False) if fracture_gap is not None else None
        sides = ((signed > 0, "right"), (signed <= 0, "left")) if signed is not None else ((np.ones_like(s), "both"),)
        for on_side, name in sides:
            mine = painted & on_side
            if not mine.any():
                continue
            if gap is not None and gap.any():
                pieces, _n = ndi.label(chosen & on_side)
                touching = np.unique(pieces[ndi.binary_dilation(gap) & (pieces > 0)])
                chosen = chosen & ~np.isin(pieces, touching[touching > 0])
            chosen = chosen | mine
            notes.append(f"Your painted foramina are used on the {name} side, in place of the tool's where those "
                         "touch the marked fracture.")
    out[box] = (canal | chosen)[crop]
    return out, notes


def _extend_front_to_back(labels: Volume, start, painted: np.ndarray, envelope: np.ndarray, ap_axis) -> np.ndarray:
    """What the surgeon painted, carried front to back along ``ap_axis`` (a
    unit vector) within USER_REACH_MM, inside the sacrum's envelope: a
    foramen painted on one slice becomes the channel it is."""
    out = painted.copy()
    idx = np.argwhere(painted)
    if not len(idx):
        return out
    ap = np.asarray(ap_axis, dtype=float)
    ap = ap / np.linalg.norm(ap)
    sx, sy, sz = labels.spacing
    ox, oy, oz = labels.origin
    xyz = np.stack([ox + (idx[:, 2] + start[2]) * sx, oy + (idx[:, 1] + start[1]) * sy,
                    oz + (idx[:, 0] + start[0]) * sz], axis=1)
    step = 0.5 * float(min(labels.spacing))
    shape = np.array(painted.shape)
    for t in np.arange(-USER_REACH_MM, USER_REACH_MM + step, step):
        p = xyz + t * ap
        k = np.rint((p[:, 2] - oz) / sz).astype(int) - start[0]
        j = np.rint((p[:, 1] - oy) / sy).astype(int) - start[1]
        i = np.rint((p[:, 0] - ox) / sx).astype(int) - start[2]
        ok = (k >= 0) & (k < shape[0]) & (j >= 0) & (j < shape[1]) & (i >= 0) & (i < shape[2])
        out[k[ok], j[ok], i[ok]] = True
    return out & envelope


def canal_mask(labels: Volume, sacrum_label: int, hip_labels=()) -> np.ndarray:
    """Every hole the sacrum encloses on an axial slice, with no midline
    known yet (the canal among them; anatomical_frame.canal_centres picks
    it out behind each sacral body)."""
    arr = labels.array
    out = np.zeros(arr.shape, dtype=bool)
    if not (arr == sacrum_label).any():
        return out
    box, crop, *_rest, widths = _parts(labels, sacrum_label, tuple(hip_labels), None)
    canal = _rest[3]
    out[box] = canal[crop]
    return out


def canal_and_foramina(labels: Volume, sacrum_label: int, hip_labels=()) -> np.ndarray:
    """The canal and foramina as the shape finds them, with no midline and
    no fracture known."""
    return protected_spaces(labels, sacrum_label, hip_labels)[0]
